import numpy as np
import pandas as pd

from app.strategies.base import BaseStrategy
from app.strategies import register_strategy


@register_strategy
class VolatilityContractionStrategy(BaseStrategy):
    """Squeeze-based breakout strategy.

    Detects periods where both Bollinger Band width and ATR are at
    historically low percentiles, then enters on a breakout beyond the bands.
    """

    name = "Volatility Contraction"
    description = (
        "Detects volatility squeezes using Bollinger Band width and ATR "
        "compression, then trades breakouts from the squeeze."
    )

    def __init__(self):
        self.bb_period: int = 20
        self.bb_std: float = 2.0
        self.atr_period: int = 14
        self.squeeze_percentile: int = 20
        self.atr_percentile: int = 25
        self.lookback: int = 50

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    def get_parameters(self) -> dict:
        return {
            "bb_period": self.bb_period,
            "bb_std": self.bb_std,
            "atr_period": self.atr_period,
            "squeeze_percentile": self.squeeze_percentile,
            "atr_percentile": self.atr_percentile,
            "lookback": self.lookback,
        }

    def get_overlay_columns(self) -> dict:
        return {
            "bollinger": ["bb_upper", "bb_middle", "bb_lower"],
        }

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # --- Bollinger Bands ---
        df["bb_middle"] = df["close"].rolling(self.bb_period).mean()
        rolling_std = df["close"].rolling(self.bb_period).std()
        df["bb_upper"] = df["bb_middle"] + self.bb_std * rolling_std
        df["bb_lower"] = df["bb_middle"] - self.bb_std * rolling_std
        df["bb_width"] = df["bb_upper"] - df["bb_lower"]

        # --- ATR ---
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(self.atr_period).mean()

        # --- Squeeze detection ---
        bb_width_pct = df["bb_width"].rolling(self.lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
        )
        atr_pct = df["atr"].rolling(self.lookback).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
        )

        df["squeeze"] = (
            (bb_width_pct <= self.squeeze_percentile)
            & (atr_pct <= self.atr_percentile)
        ).astype(int)

        # --- Signals ---
        # Look for breakout bar right after a squeeze period.
        df["signal"] = 0
        in_squeeze = False
        for i in range(1, len(df)):
            if df["squeeze"].iloc[i - 1] == 1:
                in_squeeze = True
            if in_squeeze and df["squeeze"].iloc[i] == 0:
                # Squeeze just released – check breakout direction
                if df["close"].iloc[i] > df["bb_upper"].iloc[i]:
                    df.iloc[i, df.columns.get_loc("signal")] = 1  # BUY
                    in_squeeze = False
                elif df["close"].iloc[i] < df["bb_lower"].iloc[i]:
                    df.iloc[i, df.columns.get_loc("signal")] = -1  # SELL
                    in_squeeze = False

        return df
