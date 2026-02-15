"""
Wrapper sobre alpaca-py SDK.
Implementa BrokerInterface para que el engine pueda operar con Alpaca
sin acoplarse directamente al SDK.

Uso:
    from backend.broker.alpaca_client import AlpacaClient
    client = AlpacaClient()          # usa config de settings
    account = await client.get_account()
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
    TrailingStopOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import (
    OrderSide as AlpacaOrderSide,
    OrderType as AlpacaOrderType,
    TimeInForce as AlpacaTimeInForce,
    OrderClass as AlpacaOrderClass,
    QueryOrderStatus,
)
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestTradeRequest,
    CryptoBarsRequest,
    CryptoLatestQuoteRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from backend.config import settings
from backend.broker.broker_interface import (
    AccountInfo,
    BrokerInterface,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TimeInForce,
)


# ── Mapeos entre nuestros enums y los de alpaca-py ───────────────

_SIDE_MAP = {
    OrderSide.BUY: AlpacaOrderSide.BUY,
    OrderSide.SELL: AlpacaOrderSide.SELL,
}

_TIF_MAP = {
    TimeInForce.DAY: AlpacaTimeInForce.DAY,
    TimeInForce.GTC: AlpacaTimeInForce.GTC,
    TimeInForce.OPG: AlpacaTimeInForce.OPG,
    TimeInForce.CLS: AlpacaTimeInForce.CLS,
    TimeInForce.IOC: AlpacaTimeInForce.IOC,
    TimeInForce.FOK: AlpacaTimeInForce.FOK,
}

_TIMEFRAME_MAP: dict[str, TimeFrame] = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "30Min": TimeFrame(30, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "4Hour": TimeFrame(4, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
    "1Week": TimeFrame(1, TimeFrameUnit.Week),
    "1Month": TimeFrame(1, TimeFrameUnit.Month),
}


def _run_sync(func, *args, **kwargs):
    """
    Ejecuta una funcion sincrona en un thread pool para no bloquear asyncio.
    alpaca-py es sincrono, asi que necesitamos esto.
    """
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, lambda: func(*args, **kwargs))


class AlpacaClient(BrokerInterface):
    """
    Adaptador de Alpaca que implementa BrokerInterface.
    Envuelve el SDK alpaca-py y normaliza los datos a nuestros modelos.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: Optional[bool] = None,
    ) -> None:
        _api_key = api_key or settings.ALPACA_API_KEY
        _secret_key = secret_key or settings.ALPACA_SECRET_KEY
        _paper = paper if paper is not None else settings.is_paper

        # Cliente de trading (ordenes, posiciones, cuenta)
        self._trading = TradingClient(
            api_key=_api_key,
            secret_key=_secret_key,
            paper=_paper,
        )

        # Cliente de datos historicos (stocks)
        self._data = StockHistoricalDataClient(
            api_key=_api_key,
            secret_key=_secret_key,
        )

        # Cliente de datos historicos (crypto) — no requiere auth
        self._crypto_data = CryptoHistoricalDataClient()

        mode = "PAPER" if _paper else "LIVE"
        logger.info(f"AlpacaClient inicializado en modo {mode}")

    # ── Cuenta ───────────────────────────────────────────────────

    async def get_account(self) -> AccountInfo:
        """Obtiene la informacion de la cuenta de Alpaca."""
        acct = await _run_sync(self._trading.get_account)
        return AccountInfo(
            account_id=str(acct.id),
            equity=float(acct.equity),
            cash=float(acct.cash),
            buying_power=float(acct.buying_power),
            portfolio_value=float(acct.portfolio_value),
            currency=acct.currency or "USD",
            status=str(acct.status),
        )

    # ── Ordenes ──────────────────────────────────────────────────

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
        Envia una orden a Alpaca.

        Si se proveen take_profit_price y/o stop_loss_price, se crea una
        orden bracket (OCO) que automaticamente coloca SL/TP al ejecutarse.

        Args:
            symbol: Ticker (e.g. "AAPL", "BTC/USD").
            qty: Cantidad a operar.
            side: Lado de la orden (BUY/SELL).
            order_type: Tipo de orden (MARKET, LIMIT, etc.)
            time_in_force: Vigencia de la orden.
            limit_price: Precio limite (para LIMIT/STOP_LIMIT).
            stop_price: Precio stop (para STOP/STOP_LIMIT).
            take_profit_price: Precio de take profit (crea bracket order).
            stop_loss_price: Precio de stop loss (crea bracket order).

        Returns:
            Orden creada.
        """
        alpaca_side = _SIDE_MAP[side]
        alpaca_tif = _TIF_MAP[time_in_force]

        # Si hay SL/TP, crear bracket order
        if take_profit_price is not None or stop_loss_price is not None:
            order_request = self._build_bracket_order_request(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                time_in_force=alpaca_tif,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
            )
            logger.info(
                f"Enviando bracket order: {side.value} {qty} {symbol} | "
                f"TP={take_profit_price} | SL={stop_loss_price}"
            )
        else:
            order_request = self._build_order_request(
                symbol=symbol,
                qty=qty,
                side=alpaca_side,
                order_type=order_type,
                time_in_force=alpaca_tif,
                limit_price=limit_price,
                stop_price=stop_price,
            )
            logger.info(
                f"Enviando orden: {side.value} {qty} {symbol} ({order_type.value})"
            )

        raw_order = await _run_sync(self._trading.submit_order, order_request)
        order = self._parse_order(raw_order)

        logger.info(
            f"Orden creada: {order.order_id} | {order.symbol} | {order.status.value}"
        )
        return order

    async def get_order(self, order_id: str) -> Order:
        """Obtiene una orden por su ID."""
        raw = await _run_sync(self._trading.get_order_by_id, order_id)
        return self._parse_order(raw)

    async def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[Order]:
        """Lista ordenes, opcionalmente filtradas por status."""
        filter_params = GetOrdersRequest(
            status=QueryOrderStatus(status) if status else None,
            limit=limit,
        )
        raw_orders = await _run_sync(self._trading.get_orders, filter_params)
        return [self._parse_order(o) for o in raw_orders]

    async def cancel_order(self, order_id: str) -> None:
        """Cancela una orden abierta."""
        await _run_sync(self._trading.cancel_order_by_id, order_id)
        logger.info(f"Orden cancelada: {order_id}")

    async def cancel_all_orders(self) -> None:
        """Cancela todas las ordenes abiertas."""
        await _run_sync(self._trading.cancel_orders)
        logger.info("Todas las ordenes abiertas canceladas")

    # ── Posiciones ───────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        """Retorna todas las posiciones abiertas."""
        raw_positions = await _run_sync(self._trading.get_all_positions)
        return [self._parse_position(p) for p in raw_positions]

    async def get_position(self, symbol: str) -> Optional[Position]:
        """Retorna la posicion de un simbolo, o None si no existe."""
        try:
            raw = await _run_sync(self._trading.get_open_position, symbol)
            return self._parse_position(raw)
        except Exception:
            # Alpaca lanza excepcion si no hay posicion para el simbolo
            return None

    async def close_position(self, symbol: str) -> Order:
        """Cierra la posicion completa de un simbolo."""
        logger.info(f"Cerrando posicion: {symbol}")
        raw = await _run_sync(self._trading.close_position, symbol)
        return self._parse_order(raw)

    async def close_all_positions(self) -> list[Order]:
        """Cierra todas las posiciones abiertas."""
        logger.info("Cerrando todas las posiciones")
        raw_responses = await _run_sync(self._trading.close_all_positions, cancel_orders=True)
        orders: list[Order] = []
        for resp in raw_responses:
            if hasattr(resp, "body") and resp.body:
                orders.append(self._parse_order(resp.body))
        return orders

    # ── Datos de mercado ─────────────────────────────────────────

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Obtiene barras OHLCV historicas de Alpaca.

        Detecta automaticamente si el simbolo es crypto (contiene "/")
        y usa el cliente de datos adecuado (stock vs crypto).

        Args:
            symbol: Ticker (e.g. "AAPL", "BTC/USD").
            timeframe: Clave del timeframe - "1Min", "5Min", "15Min",
                       "1Hour", "1Day", etc.
            start: Inicio del rango temporal.
            end: Fin del rango temporal.
            limit: Numero maximo de barras.

        Returns:
            DataFrame con columnas: open, high, low, close, volume, timestamp.
        """
        tf = _TIMEFRAME_MAP.get(timeframe)
        if tf is None:
            valid = ", ".join(_TIMEFRAME_MAP.keys())
            raise ValueError(
                f"Timeframe '{timeframe}' no valido. Opciones: {valid}"
            )

        is_crypto = self._is_crypto(symbol)

        if is_crypto:
            request_params = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
            )
            logger.debug(
                f"Obteniendo barras crypto: {symbol} | {timeframe} | limit={limit}"
            )
            bars = await _run_sync(
                self._crypto_data.get_crypto_bars, request_params
            )
        else:
            request_params = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
            )
            logger.debug(
                f"Obteniendo barras: {symbol} | {timeframe} | limit={limit}"
            )
            bars = await _run_sync(self._data.get_stock_bars, request_params)

        # Convertir a DataFrame
        df = bars.df

        # Si el resultado tiene MultiIndex (symbol, timestamp), resetear
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index()
            # Filtrar solo el simbolo pedido si hay varios
            if "symbol" in df.columns:
                df = df[df["symbol"] == symbol].drop(columns=["symbol"])

        # Renombrar timestamp si hace falta
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")

        df.index.name = "timestamp"
        return df

    async def get_latest_price(self, symbol: str) -> float:
        """Retorna el ultimo precio de un simbolo via latest trade/quote."""
        if self._is_crypto(symbol):
            return await self._get_latest_crypto_price(symbol)

        request_params = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trades = await _run_sync(self._data.get_stock_latest_trade, request_params)

        # El resultado es un dict {symbol: Trade} o un solo Trade
        if isinstance(trades, dict):
            trade = trades.get(symbol)
            if trade is None:
                raise ValueError(f"No se encontro trade reciente para {symbol}")
            return float(trade.price)
        return float(trades.price)

    async def _get_latest_crypto_price(self, symbol: str) -> float:
        """Obtiene el ultimo precio de un par crypto via latest quote (bid/ask mid)."""
        request_params = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = await _run_sync(
            self._crypto_data.get_crypto_latest_quote, request_params
        )

        if isinstance(quotes, dict):
            quote = quotes.get(symbol)
            if quote is None:
                raise ValueError(f"No se encontro quote reciente para {symbol}")
        else:
            quote = quotes

        bid = float(quote.bid_price) if quote.bid_price else 0.0
        ask = float(quote.ask_price) if quote.ask_price else 0.0

        if bid > 0 and ask > 0:
            return (bid + ask) / 2.0  # Mid price
        if bid > 0:
            return bid
        if ask > 0:
            return ask
        raise ValueError(f"Quote invalido para {symbol}: bid={bid}, ask={ask}")

    # ── Utilidades ───────────────────────────────────────────────

    async def is_market_open(self) -> bool:
        """Consulta si el mercado esta abierto ahora mismo."""
        clock = await _run_sync(self._trading.get_clock)
        return clock.is_open

    # ── Helpers privados ─────────────────────────────────────────

    @staticmethod
    def _is_crypto(symbol: str) -> bool:
        """Detecta si un simbolo es crypto (contiene '/')."""
        return "/" in symbol

    @staticmethod
    def _build_bracket_order_request(
        symbol: str,
        qty: float,
        side: AlpacaOrderSide,
        time_in_force: AlpacaTimeInForce,
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ):
        """
        Construye una orden bracket (OCO) con SL/TP integrados.

        La orden principal es MARKET, y al ejecutarse automaticamente
        crea las ordenes hijas de take profit (LIMIT) y stop loss (STOP).
        """
        kwargs = dict(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=time_in_force,
            order_class=AlpacaOrderClass.BRACKET,
        )

        if take_profit_price is not None:
            kwargs["take_profit"] = TakeProfitRequest(
                limit_price=round(take_profit_price, 2)
            )

        if stop_loss_price is not None:
            kwargs["stop_loss"] = StopLossRequest(
                stop_price=round(stop_loss_price, 2)
            )

        return MarketOrderRequest(**kwargs)

    @staticmethod
    def _build_order_request(
        symbol: str,
        qty: float,
        side: AlpacaOrderSide,
        order_type: OrderType,
        time_in_force: AlpacaTimeInForce,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ):
        """Construye el request object adecuado segun el tipo de orden."""
        common = dict(
            symbol=symbol,
            qty=qty,
            side=side,
            time_in_force=time_in_force,
        )

        if order_type == OrderType.MARKET:
            return MarketOrderRequest(**common)

        if order_type == OrderType.LIMIT:
            if limit_price is None:
                raise ValueError("limit_price es requerido para ordenes LIMIT")
            return LimitOrderRequest(**common, limit_price=limit_price)

        if order_type == OrderType.STOP:
            if stop_price is None:
                raise ValueError("stop_price es requerido para ordenes STOP")
            return StopOrderRequest(**common, stop_price=stop_price)

        if order_type == OrderType.STOP_LIMIT:
            if limit_price is None or stop_price is None:
                raise ValueError(
                    "limit_price y stop_price son requeridos para ordenes STOP_LIMIT"
                )
            return StopLimitOrderRequest(
                **common, limit_price=limit_price, stop_price=stop_price
            )

        if order_type == OrderType.TRAILING_STOP:
            return TrailingStopOrderRequest(**common, trail_price=stop_price)

        raise ValueError(f"Tipo de orden no soportado: {order_type}")

    @staticmethod
    def _parse_order(raw) -> Order:
        """Convierte un objeto Order de alpaca-py a nuestro modelo Order."""
        return Order(
            order_id=str(raw.id),
            symbol=raw.symbol,
            side=OrderSide(raw.side.value),
            order_type=OrderType(raw.type.value),
            qty=float(raw.qty) if raw.qty else 0.0,
            time_in_force=TimeInForce(raw.time_in_force.value),
            status=OrderStatus(raw.status.value),
            filled_qty=float(raw.filled_qty) if raw.filled_qty else 0.0,
            filled_avg_price=(
                float(raw.filled_avg_price) if raw.filled_avg_price else None
            ),
            limit_price=(
                float(raw.limit_price) if raw.limit_price else None
            ),
            stop_price=(
                float(raw.stop_price) if raw.stop_price else None
            ),
            created_at=raw.created_at,
            filled_at=raw.filled_at,
        )

    @staticmethod
    def _parse_position(raw) -> Position:
        """Convierte un objeto Position de alpaca-py a nuestro modelo Position."""
        return Position(
            symbol=raw.symbol,
            qty=float(raw.qty),
            side=raw.side,
            market_value=float(raw.market_value),
            avg_entry_price=float(raw.avg_entry_price),
            current_price=float(raw.current_price),
            unrealized_pl=float(raw.unrealized_pl),
            unrealized_plpc=float(raw.unrealized_plpc),
        )
