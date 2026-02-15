"""
Clase abstracta BaseStrategy.
Todas las estrategias de trading heredan de esta clase.

Para crear una nueva estrategia:
    1. Crea un archivo .py en backend/strategies/
    2. Hereda de BaseStrategy
    3. Implementa calculate_signals() y get_parameters()
    4. El registry la descubrira automaticamente

Ejemplo minimo:
    class MiEstrategia(BaseStrategy):
        name = "mi_estrategia"
        symbols = ["AAPL"]
        timeframe = "1Day"

        def calculate_signals(self, data):
            return {"AAPL": Signal.BUY}

        def get_parameters(self):
            return {"param1": 42}
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import pandas as pd
from loguru import logger


# ── Signal enum ──────────────────────────────────────────────────


class Signal(str, Enum):
    """Senal de trading generada por una estrategia."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


# ── Strategy state ───────────────────────────────────────────────


class StrategyStatus(str, Enum):
    """Estado operativo de una estrategia."""
    IDLE = "idle"          # Creada pero nunca arrancada
    RUNNING = "running"    # Ejecutandose activamente
    STOPPED = "stopped"    # Detenida manualmente
    ERROR = "error"        # Detenida por error


# ── Strategy metadata ───────────────────────────────────────────


@dataclass
class StrategyInfo:
    """Metadatos de una estrategia para serializar a la API."""
    name: str
    description: str
    symbols: list[str]
    timeframe: str
    parameters: dict[str, Any]
    status: StrategyStatus
    last_run: Optional[datetime] = None
    total_signals: int = 0


# ── Base class ───────────────────────────────────────────────────


class BaseStrategy(ABC):
    """
    Clase base abstracta para todas las estrategias de trading.

    Atributos de clase que cada estrategia debe definir:
        name:        Identificador unico de la estrategia (snake_case).
        description: Descripcion breve para mostrar en el dashboard.
        symbols:     Lista de tickers a operar (e.g. ["AAPL", "MSFT"]).
        timeframe:   Marco temporal de las barras ("1Min", "5Min", "1Hour", "1Day").

    Metodos abstractos:
        calculate_signals(): Genera senales BUY/SELL/HOLD a partir de datos.
        get_parameters():    Retorna los parametros configurables.
    """

    # ── Atributos que cada estrategia debe definir ───────────
    name: str = ""
    description: str = ""
    symbols: list[str] = []
    timeframe: str = "1Day"
    skip_market_check: bool = False  # True para crypto (opera 24/7)

    def __init__(self) -> None:
        self._status: StrategyStatus = StrategyStatus.IDLE
        self._last_run: Optional[datetime] = None
        self._total_signals: int = 0
        self._last_signals: dict[str, Signal] = {}
        self._error_message: Optional[str] = None

        if not self.name:
            raise ValueError(
                f"{self.__class__.__name__} debe definir el atributo 'name'"
            )
        if not self.symbols:
            raise ValueError(
                f"Estrategia '{self.name}' debe definir al menos un simbolo en 'symbols'"
            )

        logger.info(
            f"Estrategia '{self.name}' inicializada "
            f"(symbols={self.symbols}, timeframe={self.timeframe})"
        )

    # ── Metodos abstractos ───────────────────────────────────

    @abstractmethod
    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]:
        """
        Calcula senales de trading a partir de datos de mercado.

        Args:
            data: Diccionario {symbol: DataFrame_OHLCV} con los datos
                  historicos de cada simbolo configurado.
                  Cada DataFrame tiene columnas: open, high, low, close, volume.

        Returns:
            Diccionario {symbol: Signal} con la senal para cada simbolo.
            Ejemplo: {"AAPL": Signal.BUY, "MSFT": Signal.HOLD}
        """
        ...

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """
        Retorna los parametros configurables de la estrategia.

        Estos parametros se muestran en el dashboard y pueden ser
        modificados en runtime (via update_parameters).

        Returns:
            Diccionario {nombre_parametro: valor}.
            Ejemplo: {"fast_period": 10, "slow_period": 20}
        """
        ...

    # ── Metodos opcionales (hooks) ───────────────────────────

    def on_trade_executed(self, trade: dict[str, Any]) -> None:
        """
        Hook invocado despues de que el engine ejecuta una orden
        derivada de una senal de esta estrategia.

        Override este metodo para logica post-trade (e.g. ajustar
        parametros, notificar, registrar metricas).

        Args:
            trade: Diccionario con detalles de la operacion ejecutada.
        """
        pass

    def on_start(self) -> None:
        """
        Hook invocado cuando la estrategia se arranca.
        Util para inicializar estado interno o conexiones.
        """
        pass

    def on_stop(self) -> None:
        """
        Hook invocado cuando la estrategia se detiene.
        Util para limpiar estado o cerrar conexiones.
        """
        pass

    # ── Metodos de ciclo de vida ─────────────────────────────

    def start(self) -> None:
        """Arranca la estrategia."""
        self._status = StrategyStatus.RUNNING
        self._error_message = None
        logger.info(f"Estrategia '{self.name}' arrancada")
        self.on_start()

    def stop(self) -> None:
        """Detiene la estrategia."""
        self._status = StrategyStatus.STOPPED
        logger.info(f"Estrategia '{self.name}' detenida")
        self.on_stop()

    def set_error(self, message: str) -> None:
        """Marca la estrategia en estado de error."""
        self._status = StrategyStatus.ERROR
        self._error_message = message
        logger.error(f"Estrategia '{self.name}' en error: {message}")

    # ── Metodo principal (llamado por el engine) ─────────────

    def run(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]:
        """
        Ejecuta un ciclo de la estrategia.

        Este metodo es invocado por el engine en cada iteracion.
        Llama a calculate_signals() y actualiza el estado interno.

        Args:
            data: Diccionario {symbol: DataFrame_OHLCV}.

        Returns:
            Diccionario {symbol: Signal} con las senales generadas.

        Raises:
            RuntimeError: Si la estrategia no esta en estado RUNNING.
        """
        if self._status != StrategyStatus.RUNNING:
            raise RuntimeError(
                f"Estrategia '{self.name}' no esta corriendo "
                f"(status={self._status.value})"
            )

        try:
            signals = self.calculate_signals(data)
            self._last_run = datetime.now()
            self._last_signals = signals

            # Contar senales que no son HOLD
            active_signals = {
                sym: sig for sym, sig in signals.items() if sig != Signal.HOLD
            }
            self._total_signals += len(active_signals)

            if active_signals:
                logger.info(
                    f"[{self.name}] Senales activas: {active_signals}"
                )
            else:
                logger.debug(f"[{self.name}] Sin senales activas (todo HOLD)")

            return signals

        except Exception as e:
            self.set_error(str(e))
            raise

    # ── Utilidades para parametros ───────────────────────────

    def update_parameters(self, new_params: dict[str, Any]) -> None:
        """
        Actualiza parametros configurables de la estrategia en runtime.

        Solo actualiza atributos que existan en get_parameters().
        Ignora claves desconocidas con un warning.

        Args:
            new_params: Diccionario {nombre_parametro: nuevo_valor}.
        """
        current = self.get_parameters()
        for key, value in new_params.items():
            if key not in current:
                logger.warning(
                    f"[{self.name}] Parametro desconocido ignorado: '{key}'"
                )
                continue
            if hasattr(self, key):
                setattr(self, key, value)
                logger.info(f"[{self.name}] Parametro '{key}' actualizado a {value}")
            else:
                logger.warning(
                    f"[{self.name}] Parametro '{key}' no es un atributo de instancia"
                )

    # ── Informacion / serialization ──────────────────────────

    def get_info(self) -> StrategyInfo:
        """Retorna metadatos de la estrategia para la API."""
        return StrategyInfo(
            name=self.name,
            description=self.description,
            symbols=list(self.symbols),
            timeframe=self.timeframe,
            parameters=self.get_parameters(),
            status=self._status,
            last_run=self._last_run,
            total_signals=self._total_signals,
        )

    @property
    def status(self) -> StrategyStatus:
        """Estado actual de la estrategia."""
        return self._status

    @property
    def is_running(self) -> bool:
        """True si la estrategia esta corriendo."""
        return self._status == StrategyStatus.RUNNING

    @property
    def last_signals(self) -> dict[str, Signal]:
        """Ultimas senales generadas."""
        return dict(self._last_signals)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name='{self.name}' "
            f"symbols={self.symbols} "
            f"status={self._status.value}>"
        )

    # ── Validacion de datos ──────────────────────────────────

    @staticmethod
    def validate_data(
        data: dict[str, pd.DataFrame],
        min_bars: int = 1,
    ) -> dict[str, pd.DataFrame]:
        """
        Valida y filtra los datos de entrada.

        Descarta simbolos con DataFrames vacios o con menos de min_bars filas.

        Args:
            data: Diccionario {symbol: DataFrame}.
            min_bars: Minimo de barras requeridas.

        Returns:
            Diccionario filtrado solo con simbolos validos.
        """
        valid = {}
        for symbol, df in data.items():
            if df is None or df.empty:
                logger.warning(f"Datos vacios para {symbol}, se omite")
                continue
            if len(df) < min_bars:
                logger.warning(
                    f"Datos insuficientes para {symbol}: "
                    f"{len(df)} barras < {min_bars} requeridas"
                )
                continue
            valid[symbol] = df
        return valid
