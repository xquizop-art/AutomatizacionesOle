"""
Proveedor de datos historicos via Yahoo Finance (yfinance).

Descarga barras OHLCV historicas gratuitas con hasta 20+ anios de datos
diarios. Ideal para backtesting.

Uso:
    from backend.data.yahoo_provider import YahooDataProvider

    provider = YahooDataProvider()

    # Un simbolo
    df = provider.download_bars("AAPL", start="2020-01-01", end="2025-01-01")

    # Multiples simbolos
    data = provider.download_multiple(
        symbols=["AAPL", "MSFT", "GOOG"],
        start="2020-01-01",
        end="2025-01-01",
    )

Notas:
    - Los datos de Yahoo Finance son del activo subyacente real (no CFDs).
    - Los datos diarios tienen historico de ~20-30 anios.
    - Los datos intradiarios tienen historico limitado (7-60 dias segun intervalo).
    - Los precios estan ajustados por splits y dividendos por defecto.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger


# Mapeo de nuestros timeframes a intervalos de yfinance
_INTERVAL_MAP: dict[str, str] = {
    "1Min": "1m",
    "2Min": "2m",
    "5Min": "5m",
    "15Min": "15m",
    "30Min": "30m",
    "1Hour": "1h",
    "1Day": "1d",
    "5Day": "5d",
    "1Week": "1wk",
    "1Month": "1mo",
    "3Month": "3mo",
}

# Historico maximo por intervalo (limitaciones de Yahoo Finance)
_MAX_HISTORY: dict[str, str] = {
    "1m": "7 dias",
    "2m": "60 dias",
    "5m": "60 dias",
    "15m": "60 dias",
    "30m": "60 dias",
    "1h": "730 dias (~2 anios)",
    "1d": "sin limite practico (~30 anios)",
    "1wk": "sin limite practico",
    "1mo": "sin limite practico",
}


class YahooDataProvider:
    """
    Proveedor de datos historicos via Yahoo Finance.

    Descarga datos OHLCV y los normaliza al formato estandar del proyecto:
    columnas lowercase (open, high, low, close, volume) con indice timestamp.
    """

    def download_bars(
        self,
        symbol: str,
        start: Optional[str | datetime] = None,
        end: Optional[str | datetime] = None,
        timeframe: str = "1Day",
        period: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Descarga barras OHLCV de un simbolo.

        Args:
            symbol: Ticker (e.g. "AAPL", "MSFT").
            start: Fecha inicio ("YYYY-MM-DD" o datetime). Ignorado si period se usa.
            end: Fecha fin ("YYYY-MM-DD" o datetime). Default: hoy.
            timeframe: Nuestro formato de timeframe ("1Day", "1Hour", etc.)
            period: Alternativa a start/end. Periodo relativo de yfinance:
                    "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y",
                    "10y", "ytd", "max".

        Returns:
            DataFrame con columnas: open, high, low, close, volume.
            Indice: timestamp (DatetimeIndex, timezone-aware UTC o tz-naive).
            DataFrame vacio si no se obtuvieron datos.
        """
        interval = self._resolve_interval(timeframe)

        logger.info(
            f"Descargando de Yahoo: {symbol} | {timeframe} ({interval}) | "
            f"start={start} | end={end} | period={period}"
        )

        try:
            ticker = yf.Ticker(symbol)

            if period:
                raw_df = ticker.history(period=period, interval=interval)
            else:
                raw_df = ticker.history(
                    start=start,
                    end=end,
                    interval=interval,
                )

            if raw_df.empty:
                logger.warning(f"Yahoo no retorno datos para {symbol}")
                return pd.DataFrame()

            df = self._normalize_dataframe(raw_df)

            logger.info(
                f"Yahoo: {symbol} | {len(df)} barras descargadas "
                f"({df.index[0]} -> {df.index[-1]})"
            )
            return df

        except Exception as e:
            logger.error(f"Error descargando {symbol} de Yahoo: {e}")
            return pd.DataFrame()

    def download_multiple(
        self,
        symbols: list[str],
        start: Optional[str | datetime] = None,
        end: Optional[str | datetime] = None,
        timeframe: str = "1Day",
        period: Optional[str] = None,
    ) -> dict[str, pd.DataFrame]:
        """
        Descarga barras OHLCV de multiples simbolos.

        Usa yf.download() para eficiencia (una sola peticion HTTP para
        todos los simbolos cuando es posible).

        Args:
            symbols: Lista de tickers.
            start: Fecha inicio.
            end: Fecha fin.
            timeframe: Timeframe ("1Day", etc.)
            period: Periodo relativo alternativo.

        Returns:
            Diccionario {symbol: DataFrame} con datos OHLCV normalizados.
            Simbolos sin datos se omiten.
        """
        if not symbols:
            return {}

        interval = self._resolve_interval(timeframe)

        logger.info(
            f"Descargando de Yahoo (batch): {symbols} | {timeframe} ({interval})"
        )

        try:
            # yf.download con multiples tickers
            if period:
                raw = yf.download(
                    tickers=symbols,
                    period=period,
                    interval=interval,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
            else:
                raw = yf.download(
                    tickers=symbols,
                    start=start,
                    end=end,
                    interval=interval,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )

            if raw.empty:
                logger.warning("Yahoo no retorno datos para ningun simbolo")
                return {}

            results: dict[str, pd.DataFrame] = {}

            if len(symbols) == 1:
                # yf.download con un solo ticker no agrupa por ticker
                df = self._normalize_dataframe(raw)
                if not df.empty:
                    results[symbols[0]] = df
            else:
                # Multiples tickers: el DataFrame tiene MultiIndex en columnas
                for symbol in symbols:
                    try:
                        symbol_df = raw[symbol].copy()
                        symbol_df = self._normalize_dataframe(symbol_df)
                        if not symbol_df.empty:
                            results[symbol] = symbol_df
                        else:
                            logger.warning(
                                f"Datos vacios para {symbol} en descarga batch"
                            )
                    except KeyError:
                        logger.warning(
                            f"Simbolo {symbol} no encontrado en respuesta de Yahoo"
                        )

            logger.info(
                f"Yahoo batch: {len(results)}/{len(symbols)} simbolos descargados"
            )
            return results

        except Exception as e:
            logger.error(f"Error en descarga batch de Yahoo: {e}")
            # Fallback: descargar uno a uno
            logger.info("Intentando descarga individual como fallback...")
            results = {}
            for symbol in symbols:
                df = self.download_bars(
                    symbol=symbol,
                    start=start,
                    end=end,
                    timeframe=timeframe,
                    period=period,
                )
                if not df.empty:
                    results[symbol] = df
            return results

    def get_symbol_info(self, symbol: str) -> dict:
        """
        Obtiene informacion basica de un simbolo (nombre, sector, etc.)

        Args:
            symbol: Ticker.

        Returns:
            Diccionario con info del simbolo.
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "symbol": symbol,
                "name": info.get("longName", info.get("shortName", symbol)),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "market_cap": info.get("marketCap", 0),
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", "N/A"),
            }
        except Exception as e:
            logger.error(f"Error obteniendo info de {symbol}: {e}")
            return {"symbol": symbol, "name": symbol}

    # ── Helpers privados ─────────────────────────────────────────

    def _resolve_interval(self, timeframe: str) -> str:
        """Convierte nuestro timeframe al intervalo de yfinance."""
        interval = _INTERVAL_MAP.get(timeframe)
        if interval is None:
            valid = ", ".join(_INTERVAL_MAP.keys())
            raise ValueError(
                f"Timeframe '{timeframe}' no soportado por Yahoo. "
                f"Opciones: {valid}"
            )
        return interval

    @staticmethod
    def _normalize_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Normaliza un DataFrame de yfinance al formato estandar del proyecto.

        - Renombra columnas a lowercase.
        - Elimina columnas innecesarias (Dividends, Stock Splits, Capital Gains).
        - Establece el indice como 'timestamp'.
        - Elimina filas con NaN en OHLCV.
        """
        if raw_df.empty:
            return pd.DataFrame()

        df = raw_df.copy()

        # Renombrar columnas a lowercase
        df.columns = [col.lower().replace(" ", "_") for col in df.columns]

        # Mantener solo OHLCV
        ohlcv_cols = ["open", "high", "low", "close", "volume"]
        available = [col for col in ohlcv_cols if col in df.columns]

        if len(available) < 5:
            logger.warning(
                f"Columnas OHLCV incompletas: {available}. "
                f"Esperadas: {ohlcv_cols}"
            )
            return pd.DataFrame()

        df = df[available]

        # Eliminar filas donde OHLC es NaN (volumen puede ser 0)
        df = df.dropna(subset=["open", "high", "low", "close"])

        # Asegurar que el indice se llame 'timestamp'
        df.index.name = "timestamp"

        # Asegurar tipos numericos
        for col in ohlcv_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Volume como entero (puede tener decimales en Yahoo)
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0).astype(int)

        return df

    @staticmethod
    def get_available_history_info() -> dict[str, str]:
        """
        Retorna informacion sobre el historico maximo disponible
        por intervalo en Yahoo Finance.
        """
        return dict(_MAX_HISTORY)
