from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "Base Strategy"
    description: str = ""

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add a 'signal' column to the dataframe.

        Values: 1 = BUY, -1 = SELL, 0 = HOLD.
        May also add overlay columns (e.g. Bollinger Bands) that the
        frontend can render on the chart.
        """
        pass

    @abstractmethod
    def get_parameters(self) -> dict:
        """Return configurable parameters with their current values."""
        pass

    def set_parameters(self, params: dict) -> None:
        """Update strategy parameters from a dict."""
        current = self.get_parameters()
        for key, value in params.items():
            if key in current and hasattr(self, key):
                expected_type = type(current[key])
                setattr(self, key, expected_type(value))

    def get_overlay_columns(self) -> dict:
        """Return a mapping of overlay names to column lists.

        Example::

            {
                "bollinger": ["bb_upper", "bb_middle", "bb_lower"],
                "rsi": ["rsi"],
            }

        The frontend uses this to decide what to draw on the chart.
        """
        return {}
