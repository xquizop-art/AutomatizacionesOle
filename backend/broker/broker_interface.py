"""
Interfaz abstracta para brokers.
Permite intercambiar brokers sin cambiar el motor de trading.

Cualquier broker (Alpaca, Interactive Brokers, etc.) debe implementar
esta interfaz para ser compatible con el engine.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd


# ── Enums ────────────────────────────────────────────────────────


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"           # Good 'til canceled
    OPG = "opg"           # Market on open
    CLS = "cls"           # Market on close
    IOC = "ioc"           # Immediate or cancel
    FOK = "fok"           # Fill or kill


class OrderStatus(str, Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_NEW = "pending_new"
    ACCEPTED = "accepted"
    PENDING_CANCEL = "pending_cancel"
    STOPPED = "stopped"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"


# ── Data classes ─────────────────────────────────────────────────


@dataclass
class AccountInfo:
    """Informacion resumida de la cuenta del broker."""
    account_id: str
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    currency: str = "USD"
    status: str = "ACTIVE"


@dataclass
class Position:
    """Posicion abierta en el broker."""
    symbol: str
    qty: float
    side: str               # "long" o "short"
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float  # porcentaje


@dataclass
class Order:
    """Orden enviada al broker."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    qty: float
    time_in_force: TimeInForce
    status: OrderStatus
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    created_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None


# ── Interfaz abstracta ──────────────────────────────────────────


class BrokerInterface(ABC):
    """
    Contrato que todo broker debe cumplir.
    El engine solo habla con esta interfaz, nunca directamente con un SDK.
    """

    # ── Cuenta ───────────────────────────────────────────────

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Retorna informacion de la cuenta (equity, cash, buying power, etc.)."""
        ...

    # ── Ordenes ──────────────────────────────────────────────

    @abstractmethod
    async def submit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> Order:
        """
        Envia una orden al broker y retorna la orden creada.

        Si take_profit_price y/o stop_loss_price son provistos,
        se crea una orden bracket (OCO) con SL/TP automaticos.
        """
        ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order:
        """Obtiene el estado actual de una orden por su ID."""
        ...

    @abstractmethod
    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Order]:
        """Lista ordenes. Filtrable por status ('open', 'closed', 'all')."""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None:
        """Cancela una orden abierta."""
        ...

    @abstractmethod
    async def cancel_all_orders(self) -> None:
        """Cancela todas las ordenes abiertas."""
        ...

    # ── Posiciones ───────────────────────────────────────────

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Retorna todas las posiciones abiertas."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Retorna la posicion abierta de un simbolo especifico, o None."""
        ...

    @abstractmethod
    async def close_position(self, symbol: str) -> Order:
        """Cierra la posicion completa de un simbolo."""
        ...

    @abstractmethod
    async def close_all_positions(self) -> list[Order]:
        """Cierra todas las posiciones abiertas."""
        ...

    # ── Datos de mercado ─────────────────────────────────────

    @abstractmethod
    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Obtiene barras (OHLCV) historicas.

        Args:
            symbol: Ticker (e.g. "AAPL").
            timeframe: Intervalo - "1Min", "5Min", "15Min", "1Hour", "1Day".
            start: Fecha/hora de inicio.
            end: Fecha/hora de fin.
            limit: Numero maximo de barras.

        Returns:
            DataFrame con columnas: open, high, low, close, volume, timestamp.
        """
        ...

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        """Retorna el ultimo precio disponible de un simbolo."""
        ...

    # ── Utilidades ───────────────────────────────────────────

    @abstractmethod
    async def is_market_open(self) -> bool:
        """Indica si el mercado esta abierto en este momento."""
        ...
