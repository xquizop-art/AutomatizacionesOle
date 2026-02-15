"""
Sistema de estrategias de trading.

Exporta la clase base, el registro, y las estrategias incluidas.
"""

from backend.strategies.base_strategy import BaseStrategy, Signal
from backend.strategies.registry import StrategyRegistry

__all__ = ["BaseStrategy", "Signal", "StrategyRegistry"]
