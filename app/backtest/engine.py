"""Backtesting engine with spread modelling and ATR-based SL/TP."""

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_idx: int
    entry_price: float
    direction: int  # 1 = long, -1 = short
    stop_loss: float
    take_profit: float
    exit_idx: int = -1
    exit_price: float = 0.0
    pnl: float = 0.0
    closed: bool = False


@dataclass
class BacktestResult:
    trades: List[dict] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    win_rate: float = 0.0
    total_trades: int = 0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def run_backtest(
    df: pd.DataFrame,
    spread_pips: float = 1.5,
    sl_atr_mult: float = 1.5,
    tp_atr_mult: float = 2.0,
    risk_pct: float = 0.01,
    initial_capital: float = 10_000.0,
) -> BacktestResult:
    """Run a backtest on a DataFrame that already contains a 'signal' column.

    Parameters
    ----------
    df : DataFrame with columns: time, open, high, low, close, signal, and
         optionally atr.
    spread_pips : Spread in pips for the instrument.
    sl_atr_mult : ATR multiplier for stop-loss distance.
    tp_atr_mult : ATR multiplier for take-profit distance.
    risk_pct : Fraction of equity risked per trade.
    initial_capital : Starting equity.
    """

    if "atr" not in df.columns:
        df = df.copy()
        df["atr"] = _compute_atr(df)

    # Convert spread from pips to price.  Assume 4-digit pairs (e.g. EUR/USD
    # where 1 pip = 0.0001).  For JPY pairs this would need adjustment, but
    # it's a reasonable default.
    spread = spread_pips * 0.0001

    capital = initial_capital
    equity_curve = [capital]
    trades: List[Trade] = []
    open_trade: Trade | None = None

    for i in range(1, len(df)):
        atr = df["atr"].iloc[i]
        if pd.isna(atr) or atr == 0:
            equity_curve.append(capital)
            continue

        close = df["close"].iloc[i]
        high = df["high"].iloc[i]
        low = df["low"].iloc[i]

        # --- Check open trade for SL/TP ---
        if open_trade is not None:
            hit_tp = False
            hit_sl = False
            if open_trade.direction == 1:  # long
                if low <= open_trade.stop_loss:
                    hit_sl = True
                    exit_price = open_trade.stop_loss - spread / 2
                elif high >= open_trade.take_profit:
                    hit_tp = True
                    exit_price = open_trade.take_profit - spread / 2
            else:  # short
                if high >= open_trade.stop_loss:
                    hit_sl = True
                    exit_price = open_trade.stop_loss + spread / 2
                elif low <= open_trade.take_profit:
                    hit_tp = True
                    exit_price = open_trade.take_profit + spread / 2

            if hit_sl or hit_tp:
                open_trade.exit_idx = i
                open_trade.exit_price = exit_price
                pnl = (exit_price - open_trade.entry_price) * open_trade.direction
                # Scale pnl to capital via position sizing
                risk_amount = risk_pct * capital
                sl_dist = abs(open_trade.entry_price - open_trade.stop_loss)
                if sl_dist > 0:
                    position_size = risk_amount / sl_dist
                    open_trade.pnl = pnl * position_size
                else:
                    open_trade.pnl = 0.0
                open_trade.closed = True
                capital += open_trade.pnl
                trades.append(open_trade)
                open_trade = None

        # --- Open new trade on signal (only if flat) ---
        signal = df["signal"].iloc[i]
        if open_trade is None and signal != 0:
            direction = int(signal)
            sl_dist = atr * sl_atr_mult
            tp_dist = atr * tp_atr_mult

            if direction == 1:
                entry_price = close + spread / 2
                stop_loss = entry_price - sl_dist
                take_profit = entry_price + tp_dist
            else:
                entry_price = close - spread / 2
                stop_loss = entry_price + sl_dist
                take_profit = entry_price - tp_dist

            open_trade = Trade(
                entry_idx=i,
                entry_price=entry_price,
                direction=direction,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )

        equity_curve.append(capital)

    # --- Close any remaining open trade at last close ---
    if open_trade is not None:
        last_close = df["close"].iloc[-1]
        open_trade.exit_idx = len(df) - 1
        open_trade.exit_price = last_close
        pnl = (last_close - open_trade.entry_price) * open_trade.direction
        risk_amount = risk_pct * capital
        sl_dist = abs(open_trade.entry_price - open_trade.stop_loss)
        if sl_dist > 0:
            position_size = risk_amount / sl_dist
            open_trade.pnl = pnl * position_size
        else:
            open_trade.pnl = 0.0
        open_trade.closed = True
        capital += open_trade.pnl
        trades.append(open_trade)

    # --- Compute metrics ---
    result = BacktestResult()
    result.total_trades = len(trades)
    result.equity_curve = equity_curve

    if trades:
        wins = sum(1 for t in trades if t.pnl > 0)
        result.win_rate = wins / len(trades) if trades else 0.0
        result.total_pnl = sum(t.pnl for t in trades)

        # Sharpe ratio (annualised, assuming ~252 trading days)
        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        if len(returns) > 1 and np.std(returns) > 0:
            result.sharpe_ratio = float(
                np.mean(returns) / np.std(returns) * np.sqrt(252)
            )

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0.0
        for val in equity_curve:
            if val > peak:
                peak = val
            dd = (peak - val) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        result.max_drawdown = max_dd

        result.trades = [
            {
                "entry_idx": t.entry_idx,
                "entry_price": round(t.entry_price, 5),
                "exit_idx": t.exit_idx,
                "exit_price": round(t.exit_price, 5),
                "direction": "LONG" if t.direction == 1 else "SHORT",
                "pnl": round(t.pnl, 2),
                "stop_loss": round(t.stop_loss, 5),
                "take_profit": round(t.take_profit, 5),
            }
            for t in trades
        ]

    return result
