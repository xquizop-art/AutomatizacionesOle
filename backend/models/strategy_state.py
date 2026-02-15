"""
Modelo SQLAlchemy para el estado persistente de cada estrategia.

Registra cada ejecucion (run) de una estrategia, incluyendo sus
parametros de configuracion, estado actual, metricas acumuladas
y errores.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base


class StrategyRun(Base):
    """
    Modelo para ejecuciones de estrategias.

    Cada vez que se inicia una estrategia, se crea un nuevo registro.
    Al detenerse, se actualiza con las metricas finales.

    Tabla: strategy_runs
    """

    __tablename__ = "strategy_runs"

    # ── Primary Key ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Identificacion de la estrategia ──────────────────────
    strategy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Nombre unico de la estrategia (ej: sma_crossover)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="stopped",
        index=True,
        comment="Estado actual: running, stopped, error",
    )

    # ── Configuracion de la estrategia ───────────────────────
    symbols: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Lista de simbolos separados por coma (ej: AAPL,MSFT,GOOG)",
    )
    timeframe: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Marco temporal: 1Min, 5Min, 15Min, 1Hour, 1Day",
    )
    parameters: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Parametros de la estrategia en formato JSON",
    )

    # ── Estado de ejecucion ──────────────────────────────────
    last_signal: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Ultima senal generada en formato JSON (ej: {'AAPL': 'BUY'})",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Mensaje de error si la estrategia fallo",
    )

    # ── Metricas acumuladas del run ──────────────────────────
    total_trades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Numero total de trades ejecutados en este run",
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
    total_pnl: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="P&L total acumulado en este run (en USD)",
    )

    # ── Timestamps ───────────────────────────────────────────
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha y hora de inicio de este run",
    )
    stopped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha y hora de detencion de este run",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Fecha de creacion del registro",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Fecha de ultima actualizacion",
    )

    def __repr__(self) -> str:
        return (
            f"<StrategyRun(id={self.id}, strategy={self.strategy_name}, "
            f"status={self.status}, trades={self.total_trades}, "
            f"pnl={self.total_pnl})>"
        )

    @property
    def is_running(self) -> bool:
        """Indica si la estrategia esta en ejecucion."""
        return self.status == "running"

    @property
    def win_rate(self) -> Optional[float]:
        """Calcula el win rate (porcentaje de trades ganadores)."""
        if self.total_trades == 0:
            return None
        return (self.winning_trades / self.total_trades) * 100

    @property
    def symbols_list(self) -> list[str]:
        """Retorna la lista de simbolos como una lista Python."""
        if not self.symbols:
            return []
        return [s.strip() for s in self.symbols.split(",") if s.strip()]
