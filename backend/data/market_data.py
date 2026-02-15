"""
Servicio de datos de mercado: tiempo real, historicos y backtesting.

Capa intermedia que unifica multiples fuentes de datos:
    1. Almacenamiento local (Parquet) — mas rapido, sin API calls.
    2. Yahoo Finance — historico largo y gratuito, ideal para backtesting.
    3. Alpaca API — datos recientes y ejecucion de trading.

Patron "smart fetch": busca primero en local, si no tiene los datos
suficientes los descarga de Yahoo/Alpaca y los persiste en local.

Uso (trading en vivo):
    from backend.data.market_data import MarketDataService

    mds = MarketDataService()
    data = await mds.get_bars_for_symbols(
        symbols=["AAPL", "MSFT"],
        timeframe="1Day",
        limit=100,
    )

Uso (preparar datos para backtest):
    mds = MarketDataService()
    data = mds.get_historical_data(
        symbols=["AAPL", "MSFT"],
        timeframe="1Day",
        start="2015-01-01",
        end="2025-01-01",
    )
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger

from backend.broker.alpaca_client import AlpacaClient
from backend.data.storage import LocalStorage
from backend.data.yahoo_provider import YahooDataProvider


class DataSource(str, Enum):
    """Fuentes de datos disponibles."""
    LOCAL = "local"         # Archivos Parquet locales
    YAHOO = "yahoo"         # Yahoo Finance (yfinance)
    ALPACA = "alpaca"       # Alpaca API
    AUTO = "auto"           # Smart fetch: local → yahoo → alpaca


class MarketDataService:
    """
    Servicio unificado de datos de mercado.

    Responsabilidades:
        - Obtener barras OHLCV historicas (single y multi-symbol).
        - Obtener precios actuales (via Alpaca).
        - Consultar estado del mercado.
        - Smart fetch: busca en local, descarga de Yahoo/Alpaca si necesario.
        - Descargar y persistir datos historicos para backtesting.
        - Cache en memoria para minimizar llamadas al API durante un ciclo.
    """

    def __init__(
        self,
        client: Optional[AlpacaClient] = None,
        storage: Optional[LocalStorage] = None,
        yahoo: Optional[YahooDataProvider] = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        """
        Args:
            client: Instancia de AlpacaClient. Si no se provee, se crea una nueva.
            storage: Instancia de LocalStorage para persistencia Parquet.
            yahoo: Instancia de YahooDataProvider para datos historicos.
            cache_ttl_seconds: Tiempo de vida del cache en memoria (segundos).
                               Poner 0 para desactivar.
        """
        self._client = client or AlpacaClient()
        self._storage = storage or LocalStorage()
        self._yahoo = yahoo or YahooDataProvider()
        self._cache_ttl = cache_ttl_seconds

        # Cache en memoria: {cache_key: (timestamp_epoch, DataFrame)}
        self._bars_cache: dict[str, tuple[float, pd.DataFrame]] = {}
        # Cache de precios: {symbol: (timestamp_epoch, price)}
        self._price_cache: dict[str, tuple[float, float]] = {}

        logger.info(
            f"MarketDataService inicializado (cache_ttl={cache_ttl_seconds}s)"
        )

    # ══════════════════════════════════════════════════════════════
    # ── Datos para trading en vivo (async, via Alpaca) ───────────
    # ══════════════════════════════════════════════════════════════

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        Obtiene barras OHLCV para un unico simbolo via Alpaca.

        Args:
            symbol: Ticker (e.g. "AAPL").
            timeframe: Clave del timeframe ("1Min", "5Min", "1Hour", "1Day", etc.)
            start: Inicio del rango temporal (opcional).
            end: Fin del rango temporal (opcional).
            limit: Numero maximo de barras (opcional).
            use_cache: Si True, busca en cache antes de llamar a Alpaca.

        Returns:
            DataFrame con columnas: open, high, low, close, volume.
            Indice: timestamp.
        """
        cache_key = self._build_cache_key(symbol, timeframe, start, end, limit)

        # Intentar cache en memoria
        if use_cache and self._cache_ttl > 0:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit para barras: {symbol} | {timeframe}")
                return cached

        # Llamar a Alpaca
        try:
            df = await self._client.get_bars(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
            )

            if df.empty:
                logger.warning(f"Sin datos para {symbol} | {timeframe}")
                return df

            if use_cache and self._cache_ttl > 0:
                self._put_in_cache(cache_key, df)

            logger.debug(
                f"Barras obtenidas: {symbol} | {timeframe} | {len(df)} barras"
            )
            return df

        except Exception as e:
            logger.error(f"Error obteniendo barras de {symbol}: {e}")
            return pd.DataFrame()

    async def get_bars_for_symbols(
        self,
        symbols: list[str],
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
        use_cache: bool = True,
    ) -> dict[str, pd.DataFrame]:
        """
        Obtiene barras OHLCV para multiples simbolos de forma concurrente
        via Alpaca.

        Este es el metodo principal que usa el engine para alimentar
        las estrategias en trading en vivo.

        Args:
            symbols: Lista de tickers.
            timeframe: Clave del timeframe.
            start: Inicio del rango temporal.
            end: Fin del rango temporal.
            limit: Numero maximo de barras por simbolo.
            use_cache: Si True, busca en cache.

        Returns:
            Diccionario {symbol: DataFrame} con datos OHLCV.
        """
        if not symbols:
            logger.warning("get_bars_for_symbols llamado con lista vacia")
            return {}

        logger.info(
            f"Obteniendo barras para {len(symbols)} simbolos: "
            f"{symbols} | {timeframe} | limit={limit}"
        )

        tasks = {
            symbol: self.get_bars(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=limit,
                use_cache=use_cache,
            )
            for symbol in symbols
        }

        results: dict[str, pd.DataFrame] = {}
        gathered = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        for symbol, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.error(f"Error obteniendo datos de {symbol}: {result}")
                continue
            if result is not None and not result.empty:
                results[symbol] = result
            else:
                logger.warning(f"Datos vacios para {symbol}, se omite")

        logger.info(
            f"Datos obtenidos para {len(results)}/{len(symbols)} simbolos"
        )
        return results

    # ══════════════════════════════════════════════════════════════
    # ── Datos historicos para backtest (sincrono, Yahoo + local) ─
    # ══════════════════════════════════════════════════════════════

    def get_historical_data(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        start: Optional[str | datetime] = None,
        end: Optional[str | datetime] = None,
        source: DataSource = DataSource.AUTO,
    ) -> dict[str, pd.DataFrame]:
        """
        Obtiene datos historicos para backtest.

        Metodo sincrono (no async) diseñado para preparar datos antes
        de ejecutar un backtest. Soporta smart fetch.

        Con source=AUTO:
            1. Busca en almacenamiento local (Parquet).
            2. Si no hay datos o el rango no cubre lo pedido,
               descarga de Yahoo Finance.
            3. Guarda los datos descargados en local para futuras consultas.

        Args:
            symbols: Lista de tickers.
            timeframe: Timeframe ("1Day", "1Hour", etc.)
            start: Fecha de inicio (string "YYYY-MM-DD" o datetime).
            end: Fecha de fin (default: hoy).
            source: Fuente de datos (AUTO, LOCAL, YAHOO).

        Returns:
            Diccionario {symbol: DataFrame} con datos OHLCV.
        """
        if not symbols:
            return {}

        logger.info(
            f"get_historical_data: {symbols} | {timeframe} | "
            f"{start} → {end} | source={source.value}"
        )

        results: dict[str, pd.DataFrame] = {}

        for symbol in symbols:
            df = self._fetch_historical_single(
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                source=source,
            )
            if not df.empty:
                results[symbol] = df
            else:
                logger.warning(f"Sin datos historicos para {symbol}")

        logger.info(
            f"Datos historicos: {len(results)}/{len(symbols)} simbolos cargados"
        )
        return results

    def download_and_store(
        self,
        symbols: list[str],
        timeframe: str = "1Day",
        start: Optional[str | datetime] = None,
        end: Optional[str | datetime] = None,
        period: Optional[str] = None,
    ) -> dict[str, int]:
        """
        Descarga datos de Yahoo Finance y los almacena localmente.

        Metodo explicito para pre-descargar datos masivos antes de
        ejecutar backtests.

        Args:
            symbols: Lista de tickers a descargar.
            timeframe: Timeframe.
            start: Fecha inicio.
            end: Fecha fin.
            period: Alternativa a start/end ("5y", "10y", "max", etc.)

        Returns:
            Diccionario {symbol: numero_de_barras_guardadas}.
        """
        logger.info(
            f"Descarga masiva: {symbols} | {timeframe} | "
            f"start={start} | end={end} | period={period}"
        )

        # Descargar todo de Yahoo en batch
        data = self._yahoo.download_multiple(
            symbols=symbols,
            start=start,
            end=end,
            timeframe=timeframe,
            period=period,
        )

        result: dict[str, int] = {}
        for symbol, df in data.items():
            if not df.empty:
                self._storage.save_bars(symbol, timeframe, df)
                result[symbol] = len(df)
                logger.info(f"Almacenado: {symbol}/{timeframe} | {len(df)} barras")
            else:
                result[symbol] = 0

        return result

    def _fetch_historical_single(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str | datetime],
        end: Optional[str | datetime],
        source: DataSource,
    ) -> pd.DataFrame:
        """Obtiene datos historicos de un unico simbolo segun la fuente."""

        if source == DataSource.LOCAL:
            return self._storage.load_bars(symbol, timeframe, start=start, end=end)

        if source == DataSource.YAHOO:
            df = self._yahoo.download_bars(
                symbol=symbol,
                start=start,
                end=end,
                timeframe=timeframe,
            )
            if not df.empty:
                self._storage.save_bars(symbol, timeframe, df)
            return df

        # source == AUTO: smart fetch
        # 1. Intentar local
        local_df = self._storage.load_bars(symbol, timeframe, start=start, end=end)

        if not local_df.empty:
            # Verificar si el rango local cubre lo pedido
            if self._range_covers(local_df, start, end):
                logger.debug(
                    f"Datos locales suficientes para {symbol}/{timeframe}"
                )
                return local_df

        # 2. Descargar de Yahoo
        logger.info(
            f"Descargando {symbol}/{timeframe} de Yahoo "
            f"(datos locales insuficientes)"
        )
        yahoo_df = self._yahoo.download_bars(
            symbol=symbol,
            start=start,
            end=end,
            timeframe=timeframe,
        )

        if not yahoo_df.empty:
            # 3. Guardar en local (merge con existentes)
            self._storage.update_bars(symbol, timeframe, yahoo_df)
            # Re-cargar con el rango exacto pedido
            return self._storage.load_bars(symbol, timeframe, start=start, end=end)

        # Fallback: retornar lo que tengamos en local (puede estar incompleto)
        return local_df

    @staticmethod
    def _range_covers(
        df: pd.DataFrame,
        start: Optional[str | datetime],
        end: Optional[str | datetime],
    ) -> bool:
        """Verifica si el DataFrame cubre el rango de fechas pedido."""
        if df.empty:
            return False

        data_start = df.index[0]
        data_end = df.index[-1]

        if start is not None:
            start_ts = pd.Timestamp(start)
            if hasattr(data_start, "tz") and data_start.tz is not None:
                if start_ts.tz is None:
                    start_ts = start_ts.tz_localize(data_start.tz)
            elif start_ts.tz is not None:
                start_ts = start_ts.tz_localize(None)
            # Tolerancia de 2 dias por fines de semana/festivos
            if data_start > start_ts + pd.Timedelta(days=2):
                return False

        if end is not None:
            end_ts = pd.Timestamp(end)
            if hasattr(data_end, "tz") and data_end.tz is not None:
                if end_ts.tz is None:
                    end_ts = end_ts.tz_localize(data_end.tz)
            elif end_ts.tz is not None:
                end_ts = end_ts.tz_localize(None)
            # Tolerancia de 5 dias por fines de semana/festivos
            if data_end < end_ts - pd.Timedelta(days=5):
                return False

        return True

    # ══════════════════════════════════════════════════════════════
    # ── Precios en tiempo real ───────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def get_latest_price(
        self,
        symbol: str,
        use_cache: bool = True,
    ) -> Optional[float]:
        """Obtiene el ultimo precio de un simbolo via Alpaca."""
        if use_cache and self._cache_ttl > 0:
            cached_entry = self._price_cache.get(symbol)
            if cached_entry is not None:
                ts, price = cached_entry
                if (time.time() - ts) < self._cache_ttl:
                    logger.debug(f"Cache hit para precio: {symbol}")
                    return price

        try:
            price = await self._client.get_latest_price(symbol)

            if use_cache and self._cache_ttl > 0:
                self._price_cache[symbol] = (time.time(), price)

            return price

        except Exception as e:
            logger.error(f"Error obteniendo precio de {symbol}: {e}")
            return None

    async def get_latest_prices(
        self,
        symbols: list[str],
        use_cache: bool = True,
    ) -> dict[str, float]:
        """Obtiene los ultimos precios de multiples simbolos concurrentemente."""
        if not symbols:
            return {}

        tasks = {
            symbol: self.get_latest_price(symbol, use_cache=use_cache)
            for symbol in symbols
        }

        gathered = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        prices: dict[str, float] = {}
        for symbol, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.error(f"Error obteniendo precio de {symbol}: {result}")
            elif result is not None:
                prices[symbol] = result

        return prices

    # ══════════════════════════════════════════════════════════════
    # ── Estado del mercado ───────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def is_market_open(self) -> bool:
        """Consulta si el mercado de EEUU esta abierto."""
        try:
            return await self._client.is_market_open()
        except Exception as e:
            logger.error(f"Error consultando estado del mercado: {e}")
            return False

    # ══════════════════════════════════════════════════════════════
    # ── Utilidades de datos ──────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    @staticmethod
    def resample_bars(
        df: pd.DataFrame,
        target_timeframe: str,
    ) -> pd.DataFrame:
        """
        Re-muestrea barras a un timeframe superior.

        Args:
            df: DataFrame con columnas OHLCV e indice timestamp.
            target_timeframe: Regla de pandas resample ("5min", "1h", "1D", "1W").

        Returns:
            DataFrame re-muestreado.
        """
        if df.empty:
            return df

        resampled = df.resample(target_timeframe).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        resampled = resampled.dropna(subset=["open", "close"])
        return resampled

    @staticmethod
    def combine_dataframes(
        data: dict[str, pd.DataFrame],
        column: str = "close",
    ) -> pd.DataFrame:
        """Combina una columna de multiples simbolos en un DataFrame."""
        series_list = {}
        for symbol, df in data.items():
            if column in df.columns and not df.empty:
                series_list[symbol] = df[column]

        if not series_list:
            return pd.DataFrame()
        return pd.DataFrame(series_list)

    @staticmethod
    def calculate_returns(
        df: pd.DataFrame,
        column: str = "close",
        periods: int = 1,
    ) -> pd.Series:
        """Calcula retornos porcentuales."""
        return df[column].pct_change(periods=periods)

    # ══════════════════════════════════════════════════════════════
    # ── Acceso a componentes ─────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    @property
    def storage(self) -> LocalStorage:
        """Acceso al almacenamiento local."""
        return self._storage

    @property
    def yahoo(self) -> YahooDataProvider:
        """Acceso al proveedor de Yahoo Finance."""
        return self._yahoo

    # ══════════════════════════════════════════════════════════════
    # ── Gestion de cache en memoria ──────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def clear_cache(self) -> None:
        """Limpia todo el cache en memoria."""
        count = len(self._bars_cache) + len(self._price_cache)
        self._bars_cache.clear()
        self._price_cache.clear()
        logger.debug(f"Cache limpiado ({count} entradas)")

    def clear_expired_cache(self) -> int:
        """Elimina entradas expiradas del cache. Retorna entradas eliminadas."""
        now = time.time()
        removed = 0

        expired_keys = [
            key for key, (ts, _) in self._bars_cache.items()
            if (now - ts) >= self._cache_ttl
        ]
        for key in expired_keys:
            del self._bars_cache[key]
            removed += 1

        expired_symbols = [
            sym for sym, (ts, _) in self._price_cache.items()
            if (now - ts) >= self._cache_ttl
        ]
        for sym in expired_symbols:
            del self._price_cache[sym]
            removed += 1

        if removed > 0:
            logger.debug(f"Cache: {removed} entradas expiradas eliminadas")
        return removed

    @property
    def cache_stats(self) -> dict[str, int]:
        """Retorna estadisticas del cache en memoria."""
        return {
            "bars_entries": len(self._bars_cache),
            "price_entries": len(self._price_cache),
            "ttl_seconds": self._cache_ttl,
        }

    # ── Helpers privados ─────────────────────────────────────────

    @staticmethod
    def _build_cache_key(
        symbol: str,
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
        limit: Optional[int],
    ) -> str:
        """Construye clave unica para cache de barras."""
        start_str = start.isoformat() if start else "none"
        end_str = end.isoformat() if end else "none"
        limit_str = str(limit) if limit else "none"
        return f"{symbol}|{timeframe}|{start_str}|{end_str}|{limit_str}"

    def _get_from_cache(self, key: str) -> Optional[pd.DataFrame]:
        """Busca en cache. Retorna None si no existe o expiro."""
        entry = self._bars_cache.get(key)
        if entry is None:
            return None
        ts, df = entry
        if (time.time() - ts) >= self._cache_ttl:
            del self._bars_cache[key]
            return None
        return df.copy()

    def _put_in_cache(self, key: str, df: pd.DataFrame) -> None:
        """Guarda DataFrame en cache."""
        self._bars_cache[key] = (time.time(), df.copy())
