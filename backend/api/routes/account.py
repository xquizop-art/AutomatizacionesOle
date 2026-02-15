"""
Rutas API para informacion de la cuenta Alpaca.
Balance, equity, buying power, posiciones.

Endpoints:
    GET /api/account            - Resumen de la cuenta (equity, cash, posiciones)
    GET /api/account/positions  - Posiciones abiertas
    GET /api/account/orders     - Ordenes recientes en el broker
    GET /api/account/market     - Estado del mercado
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from backend.api.dependencies import get_engine
from backend.core.engine import TradingEngine

router = APIRouter(prefix="/api/account", tags=["account"])


# ── Schemas ───────────────────────────────────────────────────────


class PositionResponse(BaseModel):
    """Informacion de una posicion abierta."""
    symbol: str
    qty: float
    side: str
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float


class AccountResponse(BaseModel):
    """Resumen completo de la cuenta."""
    account_id: str
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    status: str
    open_positions: int
    positions: list[PositionResponse]
    is_paper: bool


class OrderResponse(BaseModel):
    """Orden en el broker."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    qty: float
    time_in_force: str
    status: str
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    created_at: Optional[str] = None
    filled_at: Optional[str] = None


class MarketStatusResponse(BaseModel):
    """Estado del mercado."""
    is_open: bool
    message: str


# ── Endpoints ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=AccountResponse,
    summary="Resumen de cuenta",
    description=(
        "Retorna informacion completa de la cuenta Alpaca: "
        "equity, cash, buying power y posiciones abiertas."
    ),
)
async def get_account(
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Obtiene resumen de la cuenta del broker."""
    try:
        summary = await engine.get_account_summary()

        if "error" in summary:
            raise HTTPException(
                status_code=502,
                detail=f"Error del broker: {summary['error']}",
            )

        from backend.config import settings
        summary["is_paper"] = settings.is_paper

        return summary

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo cuenta: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/positions",
    response_model=list[PositionResponse],
    summary="Posiciones abiertas",
    description="Retorna todas las posiciones abiertas en el broker.",
)
async def get_positions(
    engine: TradingEngine = Depends(get_engine),
) -> list[dict[str, Any]]:
    """Obtiene posiciones abiertas."""
    try:
        positions = await engine.broker.get_positions()
        return [
            {
                "symbol": p.symbol,
                "qty": p.qty,
                "side": p.side,
                "market_value": p.market_value,
                "avg_entry_price": p.avg_entry_price,
                "current_price": p.current_price,
                "unrealized_pl": p.unrealized_pl,
                "unrealized_plpc": p.unrealized_plpc,
            }
            for p in positions
        ]
    except Exception as e:
        logger.error(f"Error obteniendo posiciones: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/orders",
    response_model=list[OrderResponse],
    summary="Ordenes del broker",
    description="Retorna ordenes recientes directamente del broker Alpaca.",
)
async def get_orders(
    status: Optional[str] = Query(
        "all",
        description="Filtrar por estado: open, closed, all",
    ),
    limit: int = Query(50, ge=1, le=500, description="Maximo de ordenes"),
    engine: TradingEngine = Depends(get_engine),
) -> list[dict[str, Any]]:
    """Obtiene ordenes del broker."""
    try:
        orders = await engine.broker.get_orders(status=status, limit=limit)
        return [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side.value if hasattr(o.side, "value") else str(o.side),
                "order_type": o.order_type.value if hasattr(o.order_type, "value") else str(o.order_type),
                "qty": o.qty,
                "time_in_force": o.time_in_force.value if hasattr(o.time_in_force, "value") else str(o.time_in_force),
                "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                "filled_qty": o.filled_qty,
                "filled_avg_price": o.filled_avg_price,
                "limit_price": o.limit_price,
                "stop_price": o.stop_price,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            }
            for o in orders
        ]
    except Exception as e:
        logger.error(f"Error obteniendo ordenes del broker: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/market",
    response_model=MarketStatusResponse,
    summary="Estado del mercado",
    description="Indica si el mercado esta abierto o cerrado.",
)
async def get_market_status(
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Obtiene el estado del mercado."""
    try:
        is_open = await engine.broker.is_market_open()
        return {
            "is_open": is_open,
            "message": "Mercado abierto" if is_open else "Mercado cerrado",
        }
    except Exception as e:
        logger.error(f"Error verificando estado del mercado: {e}")
        raise HTTPException(status_code=500, detail=str(e))
