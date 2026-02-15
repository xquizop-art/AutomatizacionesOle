"""
Rutas API para historial de operaciones.
Listado con filtros por estrategia, fecha, simbolo, resultado.

Endpoints:
    GET /api/trades          - Historial de trades con filtros
    GET /api/trades/{id}     - Detalle de un trade
    GET /api/trades/summary  - Resumen estadistico de trades
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.trade import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


# ── Schemas ───────────────────────────────────────────────────────


class TradeResponse(BaseModel):
    """Respuesta con informacion de un trade."""
    id: int
    strategy_name: str
    symbol: str
    side: str
    qty: float
    order_type: str
    time_in_force: str
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    filled_avg_price: Optional[float] = None
    filled_qty: Optional[float] = None
    status: str
    alpaca_order_id: Optional[str] = None
    signal: Optional[str] = None
    realized_pnl: Optional[float] = None
    commission: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
    submitted_at: Optional[str] = None
    filled_at: Optional[str] = None
    total_value: Optional[float] = None

    model_config = {"from_attributes": True}


class TradeSummaryResponse(BaseModel):
    """Resumen estadistico de trades."""
    total_trades: int
    filled_trades: int
    rejected_trades: int
    error_trades: int
    total_buy: int
    total_sell: int
    total_realized_pnl: float
    winning_trades: int
    losing_trades: int
    win_rate: Optional[float] = None
    avg_pnl_per_trade: Optional[float] = None
    best_trade_pnl: Optional[float] = None
    worst_trade_pnl: Optional[float] = None
    by_strategy: dict[str, Any] = {}
    by_symbol: dict[str, Any] = {}


class TradeListResponse(BaseModel):
    """Respuesta paginada de lista de trades."""
    trades: list[TradeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Helpers ───────────────────────────────────────────────────────


def _trade_to_dict(trade: Trade) -> dict[str, Any]:
    """Convierte un modelo Trade a diccionario para la respuesta."""
    return {
        "id": trade.id,
        "strategy_name": trade.strategy_name,
        "symbol": trade.symbol,
        "side": trade.side,
        "qty": trade.qty,
        "order_type": trade.order_type,
        "time_in_force": trade.time_in_force,
        "limit_price": trade.limit_price,
        "stop_price": trade.stop_price,
        "filled_avg_price": trade.filled_avg_price,
        "filled_qty": trade.filled_qty,
        "status": trade.status,
        "alpaca_order_id": trade.alpaca_order_id,
        "signal": trade.signal,
        "realized_pnl": trade.realized_pnl,
        "commission": trade.commission,
        "notes": trade.notes,
        "created_at": trade.created_at.isoformat() if trade.created_at else None,
        "submitted_at": trade.submitted_at.isoformat() if trade.submitted_at else None,
        "filled_at": trade.filled_at.isoformat() if trade.filled_at else None,
        "total_value": trade.total_value,
    }


# ── Endpoints ─────────────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=TradeSummaryResponse,
    summary="Resumen de trades",
    description="Retorna estadisticas agregadas de todas las operaciones.",
)
async def get_trades_summary(
    strategy: Optional[str] = Query(None, description="Filtrar por estrategia"),
    symbol: Optional[str] = Query(None, description="Filtrar por simbolo"),
    since: Optional[str] = Query(None, description="Desde fecha (ISO 8601)"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene resumen estadistico de trades."""
    try:
        query = db.query(Trade)

        # Aplicar filtros
        if strategy:
            query = query.filter(Trade.strategy_name == strategy)
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
                query = query.filter(Trade.created_at >= since_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato de fecha invalido: {since}. Usa ISO 8601.",
                )

        trades = query.all()
        total = len(trades)

        filled = [t for t in trades if t.status == "filled"]
        rejected = [t for t in trades if t.status == "rejected"]
        errors = [t for t in trades if t.status == "error"]
        buys = [t for t in trades if t.side == "buy"]
        sells = [t for t in trades if t.side == "sell"]

        # P&L
        total_pnl = sum(t.realized_pnl or 0.0 for t in trades)
        winners = [t for t in trades if (t.realized_pnl or 0) > 0]
        losers = [t for t in trades if (t.realized_pnl or 0) < 0]

        pnl_values = [t.realized_pnl for t in trades if t.realized_pnl is not None and t.realized_pnl != 0]

        # Por estrategia
        by_strategy: dict[str, Any] = {}
        for t in trades:
            name = t.strategy_name
            if name not in by_strategy:
                by_strategy[name] = {"total": 0, "filled": 0, "pnl": 0.0}
            by_strategy[name]["total"] += 1
            if t.status == "filled":
                by_strategy[name]["filled"] += 1
            by_strategy[name]["pnl"] += t.realized_pnl or 0.0

        # Por simbolo
        by_symbol: dict[str, Any] = {}
        for t in trades:
            sym = t.symbol
            if sym not in by_symbol:
                by_symbol[sym] = {"total": 0, "filled": 0, "pnl": 0.0}
            by_symbol[sym]["total"] += 1
            if t.status == "filled":
                by_symbol[sym]["filled"] += 1
            by_symbol[sym]["pnl"] += t.realized_pnl or 0.0

        filled_count = len(filled)
        win_rate = (len(winners) / filled_count * 100) if filled_count > 0 else None

        return {
            "total_trades": total,
            "filled_trades": filled_count,
            "rejected_trades": len(rejected),
            "error_trades": len(errors),
            "total_buy": len(buys),
            "total_sell": len(sells),
            "total_realized_pnl": round(total_pnl, 2),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": round(win_rate, 2) if win_rate is not None else None,
            "avg_pnl_per_trade": (
                round(total_pnl / filled_count, 2) if filled_count > 0 else None
            ),
            "best_trade_pnl": max(pnl_values) if pnl_values else None,
            "worst_trade_pnl": min(pnl_values) if pnl_values else None,
            "by_strategy": by_strategy,
            "by_symbol": by_symbol,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo resumen de trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{trade_id}",
    response_model=TradeResponse,
    summary="Detalle de trade",
    description="Retorna informacion completa de un trade especifico.",
)
async def get_trade(
    trade_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene un trade por su ID."""
    trade = db.query(Trade).filter(Trade.id == trade_id).first()

    if not trade:
        raise HTTPException(
            status_code=404,
            detail=f"Trade con id={trade_id} no encontrado.",
        )

    return _trade_to_dict(trade)


@router.get(
    "",
    response_model=TradeListResponse,
    summary="Listar trades",
    description=(
        "Retorna historial de operaciones con filtros opcionales "
        "y paginacion."
    ),
)
async def list_trades(
    strategy: Optional[str] = Query(None, description="Filtrar por nombre de estrategia"),
    symbol: Optional[str] = Query(None, description="Filtrar por simbolo (ticker)"),
    side: Optional[str] = Query(None, description="Filtrar por lado: buy o sell"),
    status: Optional[str] = Query(None, description="Filtrar por estado: filled, rejected, error, pending"),
    since: Optional[str] = Query(None, description="Desde fecha (ISO 8601, ej: 2025-01-01T00:00:00)"),
    until: Optional[str] = Query(None, description="Hasta fecha (ISO 8601)"),
    page: int = Query(1, ge=1, description="Numero de pagina"),
    page_size: int = Query(50, ge=1, le=500, description="Trades por pagina"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Lista trades con filtros opcionales y paginacion.

    Ordenados por fecha de creacion descendente (mas recientes primero).
    """
    try:
        query = db.query(Trade)

        # ── Aplicar filtros ──────────────────────────────────
        if strategy:
            query = query.filter(Trade.strategy_name == strategy)
        if symbol:
            query = query.filter(Trade.symbol == symbol.upper())
        if side:
            query = query.filter(Trade.side == side.lower())
        if status:
            query = query.filter(Trade.status == status.lower())
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
                query = query.filter(Trade.created_at >= since_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato de fecha 'since' invalido: {since}",
                )
        if until:
            try:
                until_dt = datetime.fromisoformat(until)
                query = query.filter(Trade.created_at <= until_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato de fecha 'until' invalido: {until}",
                )

        # ── Total y paginacion ───────────────────────────────
        total = query.count()
        total_pages = max(1, (total + page_size - 1) // page_size)

        offset = (page - 1) * page_size
        trades = (
            query
            .order_by(desc(Trade.created_at))
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return {
            "trades": [_trade_to_dict(t) for t in trades],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listando trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))
