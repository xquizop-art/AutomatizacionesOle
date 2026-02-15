"""
Modelo SQLAlchemy para snapshots de metricas de rendimiento.

Captura periodicamente el estado de rendimiento del portfolio
y de cada estrategia individual. Esto permite construir la
equity curve y analizar metricas historicas.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base


class PerformanceSnapshot(Base):
    """
    Modelo para snapshots periodicos de rendimiento.

    Se toman snapshots a intervalos regulares (ej: cada hora,
    cada dia) para cada estrategia y para el portfolio global.
    Cuando strategy_name es NULL, representa metricas globales.

    Tabla: performance_snapshots
    """

    __tablename__ = "performance_snapshots"

    # ── Primary Key ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Referencia a la estrategia ───────────────────────────
    strategy_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Nombre de la estrategia. NULL = metricas globales del portfolio",
    )

    # ── Timestamp del snapshot ───────────────────────────────
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Momento en que se tomo el snapshot",
    )

    # ── Metricas de cuenta/portfolio ─────────────────────────
    equity: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Equity total de la cuenta en este momento",
    )
    cash: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Cash disponible en la cuenta",
    )
    buying_power: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Poder de compra disponible",
    )

    # ── Metricas de P&L ─────────────────────────────────────
    total_pnl: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="P&L total acumulado (en USD)",
    )
    daily_pnl: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="P&L del dia (en USD)",
    )
    unrealized_pnl: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=0.0,
        comment="P&L no realizado (posiciones abiertas)",
    )

    # ── Metricas de trading ──────────────────────────────────
    total_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Numero total de trades realizados",
    )
    winning_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Numero de trades ganadores",
    )
    losing_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Numero de trades perdedores",
    )

    # ── Metricas de rendimiento ──────────────────────────────
    win_rate: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Porcentaje de trades ganadores (0-100)",
    )
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Sharpe ratio (retorno ajustado por riesgo)",
    )
    max_drawdown: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Maximo drawdown (caida maxima desde el pico, en porcentaje)",
    )
    max_drawdown_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Maximo drawdown en USD",
    )

    # ── Indices compuestos ───────────────────────────────────
    __table_args__ = (
        Index("ix_perf_strategy_timestamp", "strategy_name", "timestamp"),
    )

    def __repr__(self) -> str:
        scope = self.strategy_name or "GLOBAL"
        return (
            f"<PerformanceSnapshot(id={self.id}, scope={scope}, "
            f"equity={self.equity}, pnl={self.total_pnl}, "
            f"win_rate={self.win_rate})>"
        )

    @property
    def is_global(self) -> bool:
        """Indica si este snapshot es del portfolio global."""
        return self.strategy_name is None

    @property
    def net_pnl(self) -> float:
        """P&L neto (realizado + no realizado)."""
        return self.total_pnl + (self.unrealized_pnl or 0.0)
