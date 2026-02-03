"""Strategy registry with auto-discovery."""

import importlib
import logging
import pkgutil
from typing import Dict, List, Type

from app.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

_registry: Dict[str, Type[BaseStrategy]] = {}


def register_strategy(cls: Type[BaseStrategy]) -> Type[BaseStrategy]:
    """Class decorator that registers a strategy in the global registry."""
    key = cls.name.lower().replace(" ", "_")
    _registry[key] = cls
    logger.info("Registered strategy: %s", key)
    return cls


def get_all_strategies() -> List[str]:
    """Return list of registered strategy keys."""
    _auto_discover()
    return list(_registry.keys())


def get_strategy(name: str) -> BaseStrategy:
    """Return a fresh instance of the named strategy."""
    _auto_discover()
    cls = _registry.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}")
    return cls()


def _auto_discover() -> None:
    """Import all modules in the strategies package so decorators execute."""
    package = importlib.import_module("app.strategies")
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name in ("base",):
            continue
        try:
            importlib.import_module(f"app.strategies.{module_name}")
        except Exception:
            logger.exception("Failed to import strategy module %s", module_name)
