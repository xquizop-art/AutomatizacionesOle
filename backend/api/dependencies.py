"""
Dependencias compartidas de la API.
Provee acceso al TradingEngine y a la sesion de base de datos
via inyeccion de dependencias de FastAPI.

Uso:
    from backend.api.dependencies import get_engine

    @router.get("/example")
    async def example(engine: TradingEngine = Depends(get_engine)):
        return engine.get_status()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException

if TYPE_CHECKING:
    from backend.core.engine import TradingEngine


# ── Engine singleton ──────────────────────────────────────────────

_engine_instance: Optional[TradingEngine] = None


def set_engine(engine: TradingEngine) -> None:
    """
    Registra la instancia global del TradingEngine.
    Se llama una vez al iniciar la aplicacion en main.py.
    """
    global _engine_instance
    _engine_instance = engine


def get_engine() -> TradingEngine:
    """
    Dependency de FastAPI para obtener el TradingEngine.

    Raises:
        HTTPException(503): Si el engine no ha sido inicializado.
    """
    if _engine_instance is None:
        raise HTTPException(
            status_code=503,
            detail="Trading engine no inicializado. El servidor esta arrancando.",
        )
    return _engine_instance
