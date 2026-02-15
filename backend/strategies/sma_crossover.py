"""
Estrategia de cruce de medias moviles (SMA Crossover).
Compra cuando la SMA rapida cruza por encima de la SMA lenta.
Vende cuando la SMA rapida cruza por debajo de la SMA lenta.

Logica:
    - Se calculan dos SMAs: una rapida (por defecto 10 periodos) y una lenta (20 periodos).
    - Si la SMA rapida cruza por encima de la lenta en la ultima barra -> BUY
    - Si la SMA rapida cruza por debajo de la lenta en la ultima barra -> SELL
    - En cualquier otro caso -> HOLD

Parametros configurables:
    - fast_period: Periodos de la SMA rapida (default 10)
    - slow_period: Periodos de la SMA lenta (default 20)
    - symbols: Lista de tickers a operar
    - timeframe: Marco temporal de las barras
"""

from typing import Any

import pandas as pd
from loguru import logger

from backend.data.indicators import add_sma, crossover, crossunder
from backend.strategies.base_strategy import BaseStrategy, Signal


class SMACrossover(BaseStrategy):
    """
    Estrategia de cruce de medias moviles simples.

    Genera senal BUY cuando la SMA rapida cruza por encima de la lenta,
    y SELL cuando cruza por debajo.
    """

    name = "sma_crossover"
    description = "Cruce de medias moviles simples (SMA). Compra en golden cross, vende en death cross."
    symbols = ["AAPL", "MSFT"]
    timeframe = "1Day"

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 20,
    ) -> None:
        # Parametros configurables
        self.fast_period = fast_period
        self.slow_period = slow_period

        # Validar que fast < slow
        if self.fast_period >= self.slow_period:
            raise ValueError(
                f"fast_period ({fast_period}) debe ser menor que "
                f"slow_period ({slow_period})"
            )

        # Inicializar la clase base (valida name, symbols)
        super().__init__()

    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]:
        """
        Calcula senales basadas en el cruce de dos SMAs.

        Args:
            data: Diccionario {symbol: DataFrame} con columnas OHLCV.

        Returns:
            Diccionario {symbol: Signal} para cada simbolo.
        """
        signals: dict[str, Signal] = {}

        # Validar datos — necesitamos al menos slow_period + 1 barras
        valid_data = self.validate_data(data, min_bars=self.slow_period + 1)

        for symbol in self.symbols:
            if symbol not in valid_data:
                logger.debug(
                    f"[{self.name}] {symbol}: datos insuficientes, emitiendo HOLD"
                )
                signals[symbol] = Signal.HOLD
                continue

            df = valid_data[symbol].copy()

            # Calcular las dos SMAs
            df = add_sma(df, self.fast_period)
            df = add_sma(df, self.slow_period)

            fast_col = f"SMA_{self.fast_period}"
            slow_col = f"SMA_{self.slow_period}"

            # Verificar que las columnas se calcularon correctamente
            if df[fast_col].isna().all() or df[slow_col].isna().all():
                logger.debug(
                    f"[{self.name}] {symbol}: SMAs con NaN, emitiendo HOLD"
                )
                signals[symbol] = Signal.HOLD
                continue

            # Detectar cruces en la ultima barra
            golden_cross = crossover(df[fast_col], df[slow_col])
            death_cross = crossunder(df[fast_col], df[slow_col])

            last_idx = len(df) - 1

            if golden_cross.iloc[last_idx]:
                signals[symbol] = Signal.BUY
                logger.info(
                    f"[{self.name}] {symbol}: Golden cross detectado "
                    f"(SMA{self.fast_period}={df[fast_col].iloc[last_idx]:.2f} > "
                    f"SMA{self.slow_period}={df[slow_col].iloc[last_idx]:.2f})"
                )
            elif death_cross.iloc[last_idx]:
                signals[symbol] = Signal.SELL
                logger.info(
                    f"[{self.name}] {symbol}: Death cross detectado "
                    f"(SMA{self.fast_period}={df[fast_col].iloc[last_idx]:.2f} < "
                    f"SMA{self.slow_period}={df[slow_col].iloc[last_idx]:.2f})"
                )
            else:
                signals[symbol] = Signal.HOLD

        return signals

    def get_parameters(self) -> dict[str, Any]:
        """Retorna los parametros configurables de la estrategia."""
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
        }

    def on_trade_executed(self, trade: dict[str, Any]) -> None:
        """Log post-ejecucion de trade."""
        logger.info(
            f"[{self.name}] Trade ejecutado: "
            f"{trade.get('side', '?')} {trade.get('qty', '?')} "
            f"{trade.get('symbol', '?')} @ {trade.get('price', '?')}"
        )
