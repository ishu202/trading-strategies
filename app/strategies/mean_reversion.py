import numpy as np
import pandas as pd

from app.strategies.base import BaseStrategy
from app.strategies import register_strategy


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


@register_strategy
class MeanReversionStrategy(BaseStrategy):
    """RSI-based mean reversion with optional Bollinger Band confirmation."""

    name = "Mean Reversion"
    description = (
        "Trades mean reversion using RSI oversold/overbought levels, "
        "optionally confirmed by Bollinger Band touches."
    )

    def __init__(self):
        self.rsi_period: int = 14
        self.rsi_oversold: int = 30
        self.rsi_overbought: int = 70
        self.use_bollinger: bool = True
        self.bb_period: int = 20
        self.bb_std: float = 2.0

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    def get_parameters(self) -> dict:
        return {
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "use_bollinger": self.use_bollinger,
            "bb_period": self.bb_period,
            "bb_std": self.bb_std,
        }

    def set_parameters(self, params: dict) -> None:
        current = self.get_parameters()
        for key, value in params.items():
            if key not in current or not hasattr(self, key):
                continue
            expected_type = type(current[key])
            if expected_type is bool:
                if isinstance(value, str):
                    setattr(self, key, value.lower() in ("true", "1", "yes"))
                else:
                    setattr(self, key, bool(value))
            else:
                setattr(self, key, expected_type(value))

    def get_overlay_columns(self) -> dict:
        cols: dict = {"rsi": ["rsi"]}
        if self.use_bollinger:
            cols["bollinger"] = ["bb_upper", "bb_middle", "bb_lower"]
        return cols

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # --- RSI ---
        df["rsi"] = _rsi(df["close"], self.rsi_period)

        # --- Bollinger Bands (always compute for overlay even if not used
        #     for confirmation) ---
        df["bb_middle"] = df["close"].rolling(self.bb_period).mean()
        rolling_std = df["close"].rolling(self.bb_period).std()
        df["bb_upper"] = df["bb_middle"] + self.bb_std * rolling_std
        df["bb_lower"] = df["bb_middle"] - self.bb_std * rolling_std

        # --- Signals ---
        df["signal"] = 0

        buy_cond = df["rsi"] < self.rsi_oversold
        sell_cond = df["rsi"] > self.rsi_overbought

        if self.use_bollinger:
            buy_cond = buy_cond & (df["close"] <= df["bb_lower"])
            sell_cond = sell_cond & (df["close"] >= df["bb_upper"])

        df.loc[buy_cond, "signal"] = 1
        df.loc[sell_cond, "signal"] = -1

        return df
