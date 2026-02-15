"""
Rutas API para gestion de estrategias.
CRUD, start/stop de estrategias.

Endpoints:
    GET  /api/strategies              - Lista todas las estrategias disponibles
    GET  /api/strategies/{name}       - Detalle de una estrategia
    POST /api/strategies/{name}/start - Arranca una estrategia
    POST /api/strategies/{name}/stop  - Detiene una estrategia
    PUT  /api/strategies/{name}/params - Actualiza parametros
    GET  /api/strategies/active       - Estrategias activas
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.api.dependencies import get_engine
from backend.core.engine import TradingEngine

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ── Schemas ───────────────────────────────────────────────────────


class StrategyResponse(BaseModel):
    """Respuesta con informacion de una estrategia."""
    name: str
    description: str
    symbols: list[str]
    timeframe: str
    parameters: dict[str, Any]
    status: str
    last_run: Optional[str] = None
    total_signals: int = 0
    instantiated: bool = False


class StrategyActionResponse(BaseModel):
    """Respuesta de una accion sobre una estrategia (start/stop)."""
    name: str
    status: str
    message: str
    symbols: list[str] = []
    timeframe: str = ""
    run_id: Optional[int] = None


class UpdateParametersRequest(BaseModel):
    """Request para actualizar parametros de una estrategia."""
    parameters: dict[str, Any]


class UpdateParametersResponse(BaseModel):
    """Respuesta tras actualizar parametros."""
    name: str
    parameters: dict[str, Any]
    message: str


# ── Endpoints ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[StrategyResponse],
    summary="Listar estrategias",
    description="Retorna todas las estrategias registradas con su estado actual.",
)
async def list_strategies(
    engine: TradingEngine = Depends(get_engine),
) -> list[dict[str, Any]]:
    """Lista todas las estrategias disponibles."""
    try:
        registry = engine.registry
        strategies_info = registry.get_all_info()
        return strategies_info
    except Exception as e:
        logger.error(f"Error listando estrategias: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/active",
    response_model=list[str],
    summary="Estrategias activas",
    description="Retorna los nombres de las estrategias que estan corriendo actualmente.",
)
async def get_active_strategies(
    engine: TradingEngine = Depends(get_engine),
) -> list[str]:
    """Retorna estrategias activas (en ejecucion)."""
    return engine.get_active_strategies()


@router.get(
    "/{name}",
    response_model=StrategyResponse,
    summary="Detalle de estrategia",
    description="Retorna informacion detallada de una estrategia especifica.",
)
async def get_strategy(
    name: str,
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Obtiene detalle de una estrategia por nombre."""
    registry = engine.registry

    if name not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{name}' no encontrada. "
                   f"Disponibles: {registry.list_strategies()}",
        )

    try:
        strategy = registry.get_strategy(name)
        info = strategy.get_info()
        return {
            "name": info.name,
            "description": info.description,
            "symbols": info.symbols,
            "timeframe": info.timeframe,
            "parameters": info.parameters,
            "status": info.status.value,
            "last_run": info.last_run.isoformat() if info.last_run else None,
            "total_signals": info.total_signals,
            "instantiated": True,
        }
    except Exception as e:
        logger.error(f"Error obteniendo estrategia '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{name}/start",
    response_model=StrategyActionResponse,
    summary="Arrancar estrategia",
    description="Arranca una estrategia registrada. El engine debe estar inicializado.",
)
async def start_strategy(
    name: str,
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Arranca una estrategia por nombre."""
    if not engine.is_running:
        raise HTTPException(
            status_code=409,
            detail="Engine no esta corriendo. Inicializa el engine primero.",
        )

    registry = engine.registry
    if name not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{name}' no encontrada. "
                   f"Disponibles: {registry.list_strategies()}",
        )

    try:
        result = await engine.start_strategy(name)
        return {
            "name": result["name"],
            "status": result["status"],
            "message": f"Estrategia '{name}' arrancada exitosamente",
            "symbols": result.get("symbols", []),
            "timeframe": result.get("timeframe", ""),
            "run_id": result.get("run_id"),
        }
    except ValueError as e:
        # Estrategia ya corriendo
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error arrancando estrategia '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{name}/stop",
    response_model=StrategyActionResponse,
    summary="Detener estrategia",
    description="Detiene una estrategia que este corriendo.",
)
async def stop_strategy(
    name: str,
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Detiene una estrategia por nombre."""
    try:
        result = await engine.stop_strategy(name)
        return {
            "name": result["name"],
            "status": result["status"],
            "message": f"Estrategia '{name}' detenida exitosamente",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deteniendo estrategia '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/{name}/params",
    response_model=UpdateParametersResponse,
    summary="Actualizar parametros",
    description="Actualiza los parametros configurables de una estrategia en runtime.",
)
async def update_strategy_parameters(
    name: str,
    request: UpdateParametersRequest,
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Actualiza parametros de una estrategia."""
    registry = engine.registry

    if name not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{name}' no encontrada.",
        )

    try:
        strategy = registry.get_strategy(name)
        strategy.update_parameters(request.parameters)
        updated_params = strategy.get_parameters()

        return {
            "name": name,
            "parameters": updated_params,
            "message": f"Parametros de '{name}' actualizados",
        }
    except Exception as e:
        logger.error(f"Error actualizando parametros de '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
