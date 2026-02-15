"""
Rutas API para metricas y rendimiento.
P&L, Sharpe ratio, win rate, drawdown, equity curve.

Endpoints:
    GET /api/performance                         - Metricas globales
    GET /api/performance/strategy/{name}         - Metricas de una estrategia
    GET /api/performance/equity-curve            - Equity curve global
    GET /api/performance/equity-curve/{name}     - Equity curve de una estrategia
    GET /api/performance/strategy-runs           - Historial de ejecuciones
    GET /api/performance/strategy-runs/{name}    - Historial de ejecuciones de una estrategia
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.api.dependencies import get_engine
from backend.core.engine import TradingEngine
from backend.models.database import get_db
from backend.models.performance import PerformanceSnapshot
from backend.models.strategy_state import StrategyRun
from backend.models.trade import Trade

router = APIRouter(prefix="/api/performance", tags=["performance"])


# ── Schemas ───────────────────────────────────────────────────────


class PerformanceMetrics(BaseModel):
    """Metricas de rendimiento."""
    total_pnl: float
    daily_pnl: float
    unrealized_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_drawdown_usd: Optional[float] = None
    equity: Optional[float] = None
    cash: Optional[float] = None
    buying_power: Optional[float] = None


class EquityCurvePoint(BaseModel):
    """Un punto en la equity curve."""
    timestamp: str
    equity: Optional[float] = None
    total_pnl: float
    daily_pnl: float


class EquityCurveResponse(BaseModel):
    """Respuesta con la equity curve."""
    strategy_name: Optional[str] = None
    points: list[EquityCurvePoint]
    total_points: int


class StrategyRunResponse(BaseModel):
    """Informacion de una ejecucion de estrategia."""
    id: int
    strategy_name: str
    status: str
    symbols: list[str]
    timeframe: Optional[str] = None
    parameters: Optional[str] = None
    last_signal: Optional[str] = None
    error_message: Optional[str] = None
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    win_rate: Optional[float] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    created_at: Optional[str] = None


class EngineStatusResponse(BaseModel):
    """Estado completo del engine."""
    engine_status: str
    started_at: Optional[str] = None
    active_strategies: list[str]
    total_strategies_available: int
    total_cycles: int
    total_orders_submitted: int
    risk_manager: dict[str, Any]
    websocket_connections: int


# ── Helpers ───────────────────────────────────────────────────────


def _compute_metrics_from_trades(
    trades: list[Trade],
) -> dict[str, Any]:
    """Calcula metricas de rendimiento a partir de una lista de trades."""
    filled = [t for t in trades if t.status == "filled"]
    total = len(filled)

    winners = [t for t in filled if (t.realized_pnl or 0) > 0]
    losers = [t for t in filled if (t.realized_pnl or 0) < 0]

    total_pnl = sum(t.realized_pnl or 0.0 for t in filled)

    win_rate = None
    if total > 0:
        win_rate = round(len(winners) / total * 100, 2)

    return {
        "total_pnl": round(total_pnl, 2),
        "total_trades": total,
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate": win_rate,
    }


def _run_to_dict(run: StrategyRun) -> dict[str, Any]:
    """Convierte un StrategyRun a diccionario."""
    return {
        "id": run.id,
        "strategy_name": run.strategy_name,
        "status": run.status,
        "symbols": run.symbols_list,
        "timeframe": run.timeframe,
        "parameters": run.parameters,
        "last_signal": run.last_signal,
        "error_message": run.error_message,
        "total_trades": run.total_trades,
        "winning_trades": run.winning_trades,
        "losing_trades": run.losing_trades,
        "total_pnl": run.total_pnl,
        "win_rate": run.win_rate,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "stopped_at": run.stopped_at.isoformat() if run.stopped_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PerformanceMetrics,
    summary="Metricas globales",
    description="Retorna metricas de rendimiento globales del portfolio.",
)
async def get_global_performance(
    engine: TradingEngine = Depends(get_engine),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene metricas globales de rendimiento."""
    try:
        # Metricas desde trades en DB
        trades = db.query(Trade).all()
        metrics = _compute_metrics_from_trades(trades)

        # Ultimo snapshot global para datos de cuenta
        latest_snapshot = (
            db.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.strategy_name.is_(None))
            .order_by(desc(PerformanceSnapshot.timestamp))
            .first()
        )

        # Datos del engine/risk manager
        engine_status = engine.get_status()
        risk_data = engine_status.get("risk_manager", {})
        account_data = risk_data.get("account", {})

        return {
            "total_pnl": metrics["total_pnl"],
            "daily_pnl": (
                latest_snapshot.daily_pnl if latest_snapshot else 0.0
            ),
            "unrealized_pnl": (
                latest_snapshot.unrealized_pnl if latest_snapshot else 0.0
            ),
            "total_trades": metrics["total_trades"],
            "winning_trades": metrics["winning_trades"],
            "losing_trades": metrics["losing_trades"],
            "win_rate": metrics["win_rate"],
            "sharpe_ratio": (
                latest_snapshot.sharpe_ratio if latest_snapshot else None
            ),
            "max_drawdown": (
                latest_snapshot.max_drawdown if latest_snapshot else None
            ),
            "max_drawdown_usd": (
                latest_snapshot.max_drawdown_usd if latest_snapshot else None
            ),
            "equity": account_data.get("equity"),
            "cash": account_data.get("cash"),
            "buying_power": account_data.get("buying_power"),
        }

    except Exception as e:
        logger.error(f"Error obteniendo metricas globales: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/engine-status",
    response_model=EngineStatusResponse,
    summary="Estado del engine",
    description="Retorna el estado completo del motor de trading.",
)
async def get_engine_status(
    engine: TradingEngine = Depends(get_engine),
) -> dict[str, Any]:
    """Obtiene estado completo del engine."""
    from backend.api.websocket import ws_manager

    status = engine.get_status()
    status["websocket_connections"] = ws_manager.connection_count
    return status


@router.get(
    "/strategy/{name}",
    response_model=PerformanceMetrics,
    summary="Metricas de estrategia",
    description="Retorna metricas de rendimiento de una estrategia especifica.",
)
async def get_strategy_performance(
    name: str,
    engine: TradingEngine = Depends(get_engine),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene metricas de rendimiento de una estrategia."""
    registry = engine.registry
    if name not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{name}' no encontrada.",
        )

    try:
        # Trades de esta estrategia
        trades = (
            db.query(Trade)
            .filter(Trade.strategy_name == name)
            .all()
        )
        metrics = _compute_metrics_from_trades(trades)

        # Ultimo snapshot de esta estrategia
        latest_snapshot = (
            db.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.strategy_name == name)
            .order_by(desc(PerformanceSnapshot.timestamp))
            .first()
        )

        return {
            "total_pnl": metrics["total_pnl"],
            "daily_pnl": (
                latest_snapshot.daily_pnl if latest_snapshot else 0.0
            ),
            "unrealized_pnl": (
                latest_snapshot.unrealized_pnl if latest_snapshot else 0.0
            ),
            "total_trades": metrics["total_trades"],
            "winning_trades": metrics["winning_trades"],
            "losing_trades": metrics["losing_trades"],
            "win_rate": metrics["win_rate"],
            "sharpe_ratio": (
                latest_snapshot.sharpe_ratio if latest_snapshot else None
            ),
            "max_drawdown": (
                latest_snapshot.max_drawdown if latest_snapshot else None
            ),
            "max_drawdown_usd": (
                latest_snapshot.max_drawdown_usd if latest_snapshot else None
            ),
            "equity": None,
            "cash": None,
            "buying_power": None,
        }

    except Exception as e:
        logger.error(f"Error obteniendo metricas de '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/equity-curve",
    response_model=EquityCurveResponse,
    summary="Equity curve global",
    description="Retorna la equity curve del portfolio completo.",
)
async def get_equity_curve(
    since: Optional[str] = Query(None, description="Desde fecha (ISO 8601)"),
    limit: int = Query(500, ge=1, le=5000, description="Maximo de puntos"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene la equity curve global."""
    try:
        query = (
            db.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.strategy_name.is_(None))
        )

        if since:
            try:
                since_dt = datetime.fromisoformat(since)
                query = query.filter(PerformanceSnapshot.timestamp >= since_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato de fecha invalido: {since}",
                )

        snapshots = (
            query
            .order_by(PerformanceSnapshot.timestamp)
            .limit(limit)
            .all()
        )

        points = [
            {
                "timestamp": s.timestamp.isoformat(),
                "equity": s.equity,
                "total_pnl": s.total_pnl,
                "daily_pnl": s.daily_pnl,
            }
            for s in snapshots
        ]

        return {
            "strategy_name": None,
            "points": points,
            "total_points": len(points),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo equity curve: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/equity-curve/{name}",
    response_model=EquityCurveResponse,
    summary="Equity curve de estrategia",
    description="Retorna la equity curve de una estrategia especifica.",
)
async def get_strategy_equity_curve(
    name: str,
    since: Optional[str] = Query(None, description="Desde fecha (ISO 8601)"),
    limit: int = Query(500, ge=1, le=5000, description="Maximo de puntos"),
    engine: TradingEngine = Depends(get_engine),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Obtiene la equity curve de una estrategia."""
    registry = engine.registry
    if name not in registry:
        raise HTTPException(
            status_code=404,
            detail=f"Estrategia '{name}' no encontrada.",
        )

    try:
        query = (
            db.query(PerformanceSnapshot)
            .filter(PerformanceSnapshot.strategy_name == name)
        )

        if since:
            try:
                since_dt = datetime.fromisoformat(since)
                query = query.filter(PerformanceSnapshot.timestamp >= since_dt)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Formato de fecha invalido: {since}",
                )

        snapshots = (
            query
            .order_by(PerformanceSnapshot.timestamp)
            .limit(limit)
            .all()
        )

        points = [
            {
                "timestamp": s.timestamp.isoformat(),
                "equity": s.equity,
                "total_pnl": s.total_pnl,
                "daily_pnl": s.daily_pnl,
            }
            for s in snapshots
        ]

        return {
            "strategy_name": name,
            "points": points,
            "total_points": len(points),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo equity curve de '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/strategy-runs",
    response_model=list[StrategyRunResponse],
    summary="Historial de ejecuciones",
    description="Retorna el historial de todas las ejecuciones de estrategias.",
)
async def list_strategy_runs(
    status: Optional[str] = Query(None, description="Filtrar por estado: running, stopped, error"),
    limit: int = Query(50, ge=1, le=500, description="Maximo de registros"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Lista historial de ejecuciones de estrategias."""
    try:
        query = db.query(StrategyRun)

        if status:
            query = query.filter(StrategyRun.status == status.lower())

        runs = (
            query
            .order_by(desc(StrategyRun.created_at))
            .limit(limit)
            .all()
        )

        return [_run_to_dict(r) for r in runs]

    except Exception as e:
        logger.error(f"Error listando strategy runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/strategy-runs/{name}",
    response_model=list[StrategyRunResponse],
    summary="Ejecuciones de una estrategia",
    description="Retorna el historial de ejecuciones de una estrategia especifica.",
)
async def get_strategy_runs(
    name: str,
    limit: int = Query(20, ge=1, le=200, description="Maximo de registros"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Obtiene historial de ejecuciones de una estrategia."""
    try:
        runs = (
            db.query(StrategyRun)
            .filter(StrategyRun.strategy_name == name)
            .order_by(desc(StrategyRun.created_at))
            .limit(limit)
            .all()
        )

        if not runs:
            # Verificar si la estrategia existe antes de reportar 404
            # (puede existir pero no tener runs aun)
            return []

        return [_run_to_dict(r) for r in runs]

    except Exception as e:
        logger.error(f"Error obteniendo runs de '{name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))
