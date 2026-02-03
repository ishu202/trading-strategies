import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    OANDA_API_KEY = os.environ.get("OANDA_API_KEY")
    OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID")
    OANDA_ENVIRONMENT = os.environ.get("OANDA_ENVIRONMENT", "practice")

    DEFAULT_INSTRUMENT = "EUR_USD"
    DEFAULT_INTERVAL = "1H"
    SPREADS = {
        "EUR_USD": 1.5,
        "GBP_USD": 2.0,
        "USD_JPY": 1.5,
    }

    INSTRUMENTS = ["EUR_USD", "GBP_USD", "USD_JPY"]

    INTERVALS = ["15M", "30M", "1H", "2H", "4H", "1D", "1W"]

    GRANULARITY_MAP = {
        "15M": "M15",
        "30M": "M30",
        "1H": "H1",
        "2H": "H2",
        "4H": "H4",
        "1D": "D",
        "1W": "W",
    }
