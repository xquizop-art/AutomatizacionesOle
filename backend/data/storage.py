"""
Almacenamiento local de datos de mercado en formato Parquet.

Gestiona la persistencia de barras OHLCV en disco para evitar
re-descargar datos historicos y acelerar backtests.

Estructura de archivos:
    backend/data/storage/
    ├── AAPL/
    │   ├── 1Day.parquet
    │   ├── 1Hour.parquet
    │   └── 5Min.parquet
    ├── MSFT/
    │   ├── 1Day.parquet
    │   └── ...
    └── ...

Uso:
    from backend.data.storage import LocalStorage

    store = LocalStorage()

    # Guardar datos
    store.save_bars("AAPL", "1Day", df)

    # Cargar datos
    df = store.load_bars("AAPL", "1Day")

    # Cargar con rango de fechas
    df = store.load_bars("AAPL", "1Day", start="2023-01-01", end="2024-01-01")

    # Actualizar (append nuevas barras sin duplicados)
    store.update_bars("AAPL", "1Day", new_df)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger


# Directorio base por defecto para almacenamiento
_DEFAULT_STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "storage",
)


class LocalStorage:
    """
    Gestor de almacenamiento local de barras OHLCV en Parquet.

    Organiza los datos en directorios por simbolo, con un archivo
    Parquet por timeframe. Soporta append incremental para actualizar
    datos sin re-descargar todo.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        """
        Args:
            base_dir: Directorio raiz para los archivos Parquet.
                      Por defecto: backend/data/storage/
        """
        self._base_dir = Path(base_dir or _DEFAULT_STORAGE_DIR)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"LocalStorage inicializado en: {self._base_dir}")

    # ── Guardar / Cargar ─────────────────────────────────────────

    def save_bars(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> None:
        """
        Guarda barras OHLCV en un archivo Parquet (sobreescribe si existe).

        Args:
            symbol: Ticker (e.g. "AAPL").
            timeframe: Timeframe (e.g. "1Day", "1Hour").
            df: DataFrame con columnas OHLCV e indice timestamp.
        """
        if df.empty:
            logger.warning(f"save_bars: DataFrame vacio para {symbol}/{timeframe}")
            return

        path = self._get_file_path(symbol, timeframe)
        path.parent.mkdir(parents=True, exist_ok=True)

        df.to_parquet(path, engine="pyarrow")
        logger.info(
            f"Guardado: {symbol}/{timeframe} | {len(df)} barras | {path}"
        )

    def load_bars(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str | datetime] = None,
        end: Optional[str | datetime] = None,
    ) -> pd.DataFrame:
        """
        Carga barras OHLCV desde un archivo Parquet local.

        Args:
            symbol: Ticker.
            timeframe: Timeframe.
            start: Filtrar desde esta fecha (inclusive). String "YYYY-MM-DD" o datetime.
            end: Filtrar hasta esta fecha (inclusive). String "YYYY-MM-DD" o datetime.

        Returns:
            DataFrame con datos OHLCV, o DataFrame vacio si no existe el archivo.
        """
        path = self._get_file_path(symbol, timeframe)

        if not path.exists():
            logger.debug(f"No hay datos locales para {symbol}/{timeframe}")
            return pd.DataFrame()

        try:
            df = pd.read_parquet(path, engine="pyarrow")

            # Asegurar que el indice sea DatetimeIndex con nombre 'timestamp'
            if not isinstance(df.index, pd.DatetimeIndex):
                if "timestamp" in df.columns:
                    df = df.set_index("timestamp")
                df.index = pd.to_datetime(df.index)
            df.index.name = "timestamp"

            # Filtrar por rango de fechas si se especifica
            if start is not None:
                start_dt = pd.Timestamp(start)
                # Si el indice es tz-aware y start no, o viceversa
                if df.index.tz is not None and start_dt.tz is None:
                    start_dt = start_dt.tz_localize(df.index.tz)
                elif df.index.tz is None and start_dt.tz is not None:
                    start_dt = start_dt.tz_localize(None)
                df = df[df.index >= start_dt]

            if end is not None:
                end_dt = pd.Timestamp(end)
                if df.index.tz is not None and end_dt.tz is None:
                    end_dt = end_dt.tz_localize(df.index.tz)
                elif df.index.tz is None and end_dt.tz is not None:
                    end_dt = end_dt.tz_localize(None)
                df = df[df.index <= end_dt]

            logger.debug(
                f"Cargado: {symbol}/{timeframe} | {len(df)} barras"
            )
            return df

        except Exception as e:
            logger.error(f"Error cargando {symbol}/{timeframe}: {e}")
            return pd.DataFrame()

    def update_bars(
        self,
        symbol: str,
        timeframe: str,
        new_df: pd.DataFrame,
    ) -> int:
        """
        Actualiza datos existentes anadiendo nuevas barras.

        Combina datos existentes con los nuevos, elimina duplicados
        (por timestamp) y guarda el resultado.

        Args:
            symbol: Ticker.
            timeframe: Timeframe.
            new_df: DataFrame con barras nuevas.

        Returns:
            Numero de barras nuevas anadidas.
        """
        if new_df.empty:
            return 0

        existing = self.load_bars(symbol, timeframe)

        if existing.empty:
            # No habia datos previos, guardar todo
            self.save_bars(symbol, timeframe, new_df)
            return len(new_df)

        # Combinar y eliminar duplicados
        before_count = len(existing)
        combined = pd.concat([existing, new_df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()

        new_count = len(combined) - before_count
        self.save_bars(symbol, timeframe, combined)

        logger.info(
            f"Actualizado: {symbol}/{timeframe} | "
            f"+{new_count} barras nuevas | total: {len(combined)}"
        )
        return new_count

    # ── Consultas ────────────────────────────────────────────────

    def has_data(self, symbol: str, timeframe: str) -> bool:
        """Verifica si existen datos locales para un simbolo/timeframe."""
        return self._get_file_path(symbol, timeframe).exists()

    def get_data_range(
        self,
        symbol: str,
        timeframe: str,
    ) -> Optional[tuple[datetime, datetime]]:
        """
        Retorna el rango de fechas de los datos almacenados.

        Args:
            symbol: Ticker.
            timeframe: Timeframe.

        Returns:
            Tupla (fecha_inicio, fecha_fin) o None si no hay datos.
        """
        df = self.load_bars(symbol, timeframe)
        if df.empty:
            return None

        return (df.index[0].to_pydatetime(), df.index[-1].to_pydatetime())

    def get_bar_count(self, symbol: str, timeframe: str) -> int:
        """Retorna el numero de barras almacenadas, o 0 si no hay datos."""
        path = self._get_file_path(symbol, timeframe)
        if not path.exists():
            return 0
        try:
            df = pd.read_parquet(path, engine="pyarrow")
            return len(df)
        except Exception:
            return 0

    def list_symbols(self) -> list[str]:
        """Lista todos los simbolos con datos almacenados."""
        if not self._base_dir.exists():
            return []

        symbols = [
            d.name
            for d in self._base_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        return sorted(symbols)

    def list_timeframes(self, symbol: str) -> list[str]:
        """Lista los timeframes disponibles para un simbolo."""
        symbol_dir = self._base_dir / symbol.upper()
        if not symbol_dir.exists():
            return []

        timeframes = [
            f.stem  # nombre sin extension
            for f in symbol_dir.iterdir()
            if f.suffix == ".parquet"
        ]
        return sorted(timeframes)

    def get_storage_summary(self) -> list[dict]:
        """
        Retorna un resumen de todos los datos almacenados.

        Returns:
            Lista de diccionarios con info de cada dataset:
            [{"symbol": "AAPL", "timeframe": "1Day", "bars": 1234,
              "start": datetime, "end": datetime, "size_mb": 0.5}, ...]
        """
        summary = []
        for symbol in self.list_symbols():
            for timeframe in self.list_timeframes(symbol):
                path = self._get_file_path(symbol, timeframe)
                size_mb = path.stat().st_size / (1024 * 1024)
                data_range = self.get_data_range(symbol, timeframe)

                entry = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "bars": self.get_bar_count(symbol, timeframe),
                    "size_mb": round(size_mb, 3),
                    "start": data_range[0] if data_range else None,
                    "end": data_range[1] if data_range else None,
                }
                summary.append(entry)

        return summary

    # ── Limpieza ─────────────────────────────────────────────────

    def delete_bars(self, symbol: str, timeframe: str) -> bool:
        """
        Elimina los datos de un simbolo/timeframe.

        Returns:
            True si se elimino, False si no existia.
        """
        path = self._get_file_path(symbol, timeframe)
        if path.exists():
            path.unlink()
            logger.info(f"Eliminado: {symbol}/{timeframe}")
            # Limpiar directorio vacio
            if path.parent.exists() and not any(path.parent.iterdir()):
                path.parent.rmdir()
            return True
        return False

    def delete_symbol(self, symbol: str) -> int:
        """
        Elimina todos los datos de un simbolo.

        Returns:
            Numero de archivos eliminados.
        """
        import shutil

        symbol_dir = self._base_dir / symbol.upper()
        if not symbol_dir.exists():
            return 0

        count = sum(1 for f in symbol_dir.iterdir() if f.suffix == ".parquet")
        shutil.rmtree(symbol_dir)
        logger.info(f"Eliminado simbolo completo: {symbol} ({count} archivos)")
        return count

    # ── Helpers privados ─────────────────────────────────────────

    def _get_file_path(self, symbol: str, timeframe: str) -> Path:
        """Construye la ruta del archivo Parquet para un simbolo/timeframe."""
        return self._base_dir / symbol.upper() / f"{timeframe}.parquet"
