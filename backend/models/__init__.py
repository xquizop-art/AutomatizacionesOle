"""
Modelos SQLAlchemy para el bot de trading.

Exporta todos los modelos y utilidades de base de datos
para acceso conveniente:

    from backend.models import Base, get_db, Trade, StrategyRun, PerformanceSnapshot
"""

from backend.models.database import Base, SessionLocal, engine, get_db, init_db
from backend.models.performance import PerformanceSnapshot
from backend.models.strategy_state import StrategyRun
from backend.models.trade import Trade

__all__ = [
    "Base",
    "SessionLocal",
    "engine",
    "get_db",
    "init_db",
    "Trade",
    "StrategyRun",
    "PerformanceSnapshot",
]
