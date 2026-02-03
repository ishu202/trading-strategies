"""OANDA data fetcher with in-memory caching."""

import hashlib
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import requests

from config import Config

logger = logging.getLogger(__name__)

# Simple in-memory cache: key -> (timestamp, dataframe)
_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 300  # seconds


def _cache_key(instrument: str, granularity: str, from_date: str, to_date: str) -> str:
    raw = f"{instrument}|{granularity}|{from_date}|{to_date}"
    return hashlib.md5(raw.encode()).hexdigest()


def fetch_candles(
    instrument: str,
    interval: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    config: Optional[Config] = None,
) -> pd.DataFrame:
    """Fetch candlestick data from OANDA for a date range.

    Parameters
    ----------
    from_date : str | None
        Start date as ``YYYY-MM-DD``.  Defaults to 30 days ago.
    to_date : str | None
        End date as ``YYYY-MM-DD``.  Defaults to today.

    Returns a DataFrame with columns:
        time, open, high, low, close, volume
    """
    if config is None:
        config = Config()

    # Default dates
    if not to_date:
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
    if not from_date:
        from_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")

    granularity = Config.GRANULARITY_MAP.get(interval)
    if granularity is None:
        raise ValueError(f"Unsupported interval: {interval}")

    # Check cache
    key = _cache_key(instrument, granularity, from_date, to_date)
    if key in _cache:
        ts, cached_df = _cache[key]
        if time.time() - ts < _CACHE_TTL:
            logger.info("Cache hit for %s %s (%s to %s)", instrument, granularity, from_date, to_date)
            return cached_df.copy()

    api_key = Config.OANDA_API_KEY
    account_id = Config.OANDA_ACCOUNT_ID

    if not api_key or not account_id:
        logger.warning("OANDA credentials not set – returning synthetic data")
        return _synthetic_data(from_date, to_date)

    env = Config.OANDA_ENVIRONMENT
    if env == "live":
        base_url = "https://api-fxtrade.oanda.com"
    else:
        base_url = "https://api-fxpractice.oanda.com"

    url = f"{base_url}/v3/instruments/{instrument}/candles"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    params = {
        "granularity": granularity,
        "from": f"{from_date}T00:00:00Z",
        "to": f"{to_date}T00:00:00Z",
        "price": "M",  # mid prices
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        logger.exception("OANDA API request failed")
        raise

    candles = data.get("candles", [])
    rows = []
    for c in candles:
        if not c.get("complete", True):
            continue
        mid = c["mid"]
        rows.append(
            {
                "time": c["time"],
                "open": float(mid["o"]),
                "high": float(mid["h"]),
                "low": float(mid["l"]),
                "close": float(mid["c"]),
                "volume": int(c.get("volume", 0)),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])

    # Store in cache
    _cache[key] = (time.time(), df.copy())
    logger.info("Fetched %d candles for %s %s", len(df), instrument, granularity)
    return df


def _synthetic_data(from_date: str, to_date: str) -> pd.DataFrame:
    """Generate synthetic OHLCV data for development without API keys."""
    import numpy as np

    start = pd.Timestamp(from_date)
    end = pd.Timestamp(to_date)
    dates = pd.date_range(start=start, end=end, freq="h")
    count = len(dates)

    np.random.seed(42)
    close = 1.1000 + np.cumsum(np.random.randn(count) * 0.0005)
    high = close + np.abs(np.random.randn(count) * 0.0003)
    low = close - np.abs(np.random.randn(count) * 0.0003)
    open_ = close + np.random.randn(count) * 0.0002
    volume = np.random.randint(100, 5000, size=count)

    return pd.DataFrame(
        {
            "time": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
