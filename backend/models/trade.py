"""
Modelo SQLAlchemy para trades (operaciones ejecutadas).

Cada registro representa una orden enviada al broker (Alpaca).
Almacena informacion completa de la operacion: simbolo, lado,
cantidad, precio, estado, P&L, y la estrategia que la genero.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base


class Trade(Base):
    """
    Modelo para operaciones ejecutadas.

    Tabla: trades
    """

    __tablename__ = "trades"

    # ── Primary Key ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Referencia a la estrategia ───────────────────────────
    strategy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Nombre de la estrategia que genero el trade",
    )

    # ── Datos de la operacion ────────────────────────────────
    symbol: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Ticker del activo (ej: AAPL, MSFT)",
    )
    side: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Lado de la operacion: buy o sell",
    )
    qty: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Cantidad de acciones/unidades",
    )
    order_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="market",
        comment="Tipo de orden: market, limit, stop, stop_limit",
    )
    time_in_force: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="day",
        comment="Vigencia de la orden: day, gtc, ioc, fok",
    )
    limit_price: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Precio limite (solo para ordenes limit/stop_limit)",
    )
    stop_price: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Precio stop (solo para ordenes stop/stop_limit)",
    )

    # ── Resultado de la ejecucion ────────────────────────────
    filled_avg_price: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Precio promedio de ejecucion",
    )
    filled_qty: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Cantidad realmente ejecutada",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="Estado: pending, submitted, filled, partially_filled, cancelled, rejected",
    )

    # ── IDs de Alpaca ────────────────────────────────────────
    alpaca_order_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        comment="ID de la orden en Alpaca",
    )

    # ── Senal y P&L ─────────────────────────────────────────
    signal: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Senal que genero el trade: BUY, SELL, HOLD",
    )
    realized_pnl: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=0.0,
        comment="P&L realizado de esta operacion (en USD)",
    )
    commission: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        default=0.0,
        comment="Comision pagada",
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Notas adicionales o razon del trade",
    )

    # ── Timestamps ───────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Fecha de creacion del registro",
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de envio al broker",
    )
    filled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fecha de ejecucion completa",
    )

    # ── Indices compuestos ───────────────────────────────────
    __table_args__ = (
        Index("ix_trades_strategy_created", "strategy_name", "created_at"),
        Index("ix_trades_symbol_created", "symbol", "created_at"),
        Index("ix_trades_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, strategy={self.strategy_name}, "
            f"symbol={self.symbol}, side={self.side}, qty={self.qty}, "
            f"status={self.status})>"
        )

    @property
    def is_filled(self) -> bool:
        """Indica si la orden fue completamente ejecutada."""
        return self.status == "filled"

    @property
    def is_buy(self) -> bool:
        """Indica si es una operacion de compra."""
        return self.side.lower() == "buy"

    @property
    def total_value(self) -> Optional[float]:
        """Valor total de la operacion (precio * cantidad ejecutada)."""
        if self.filled_avg_price and self.filled_qty:
            return self.filled_avg_price * self.filled_qty
        return None
