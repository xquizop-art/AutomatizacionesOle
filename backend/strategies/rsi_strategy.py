"""
Estrategia basada en RSI (Relative Strength Index).
Compra en zona de sobreventa, vende en zona de sobrecompra.

Logica:
    - Se calcula el RSI con un periodo configurable (por defecto 14).
    - Si el RSI cruza por debajo del nivel de sobreventa (default 30) -> BUY
      (el activo esta "barato", potencial rebote alcista).
    - Si el RSI cruza por encima del nivel de sobrecompra (default 70) -> SELL
      (el activo esta "caro", potencial correccion bajista).
    - En cualquier otro caso -> HOLD

Parametros configurables:
    - rsi_period: Periodos para el calculo del RSI (default 14)
    - overbought: Nivel de sobrecompra (default 70)
    - oversold: Nivel de sobreventa (default 30)
    - symbols: Lista de tickers a operar
    - timeframe: Marco temporal de las barras
"""

from typing import Any

import pandas as pd
from loguru import logger

from backend.data.indicators import add_rsi
from backend.strategies.base_strategy import BaseStrategy, Signal


class RSIStrategy(BaseStrategy):
    """
    Estrategia basada en el Relative Strength Index (RSI).

    Genera senal BUY cuando el RSI entra en zona de sobreventa,
    y SELL cuando entra en zona de sobrecompra.
    """

    name = "rsi_strategy"
    description = "Estrategia RSI. Compra en sobreventa, vende en sobrecompra."
    symbols = ["AAPL", "MSFT"]
    timeframe = "1Day"

    def __init__(
        self,
        rsi_period: int = 14,
        overbought: float = 70.0,
        oversold: float = 30.0,
    ) -> None:
        # Parametros configurables
        self.rsi_period = rsi_period
        self.overbought = overbought
        self.oversold = oversold

        # Validacion de parametros
        if not (0 < oversold < overbought < 100):
            raise ValueError(
                f"Niveles invalidos: oversold ({oversold}) debe ser menor que "
                f"overbought ({overbought}), ambos entre 0 y 100"
            )
        if rsi_period < 2:
            raise ValueError(
                f"rsi_period ({rsi_period}) debe ser al menos 2"
            )

        # Inicializar la clase base
        super().__init__()

    def calculate_signals(self, data: dict[str, pd.DataFrame]) -> dict[str, Signal]:
        """
        Calcula senales basadas en niveles de RSI.

        La logica usa cruces de nivel para evitar senales repetidas:
        - BUY: RSI de la barra anterior estaba >= oversold y ahora esta < oversold
                (acaba de entrar en zona de sobreventa).
        - SELL: RSI de la barra anterior estaba <= overbought y ahora esta > overbought
                (acaba de entrar en zona de sobrecompra).
        - HOLD: RSI no cruzo ningun nivel critico.

        Args:
            data: Diccionario {symbol: DataFrame} con columnas OHLCV.

        Returns:
            Diccionario {symbol: Signal} para cada simbolo.
        """
        signals: dict[str, Signal] = {}

        # Necesitamos al menos rsi_period + 2 barras (periodo RSI + 1 para el cruce)
        valid_data = self.validate_data(data, min_bars=self.rsi_period + 2)

        for symbol in self.symbols:
            if symbol not in valid_data:
                logger.debug(
                    f"[{self.name}] {symbol}: datos insuficientes, emitiendo HOLD"
                )
                signals[symbol] = Signal.HOLD
                continue

            df = valid_data[symbol].copy()

            # Calcular RSI
            df = add_rsi(df, self.rsi_period)
            rsi_col = f"RSI_{self.rsi_period}"

            # Verificar que el RSI se calculo correctamente
            if df[rsi_col].isna().all():
                logger.debug(
                    f"[{self.name}] {symbol}: RSI todo NaN, emitiendo HOLD"
                )
                signals[symbol] = Signal.HOLD
                continue

            # Obtener RSI actual y anterior
            current_rsi = df[rsi_col].iloc[-1]
            previous_rsi = df[rsi_col].iloc[-2]

            # Verificar que tenemos valores validos
            if pd.isna(current_rsi) or pd.isna(previous_rsi):
                signals[symbol] = Signal.HOLD
                continue

            # Detectar cruces de nivel
            # BUY: RSI cruza hacia abajo del nivel de sobreventa
            crossed_into_oversold = (
                previous_rsi >= self.oversold and current_rsi < self.oversold
            )

            # SELL: RSI cruza hacia arriba del nivel de sobrecompra
            crossed_into_overbought = (
                previous_rsi <= self.overbought and current_rsi > self.overbought
            )

            if crossed_into_oversold:
                signals[symbol] = Signal.BUY
                logger.info(
                    f"[{self.name}] {symbol}: RSI entro en sobreventa "
                    f"(RSI={current_rsi:.2f} < {self.oversold})"
                )
            elif crossed_into_overbought:
                signals[symbol] = Signal.SELL
                logger.info(
                    f"[{self.name}] {symbol}: RSI entro en sobrecompra "
                    f"(RSI={current_rsi:.2f} > {self.overbought})"
                )
            else:
                signals[symbol] = Signal.HOLD
                logger.debug(
                    f"[{self.name}] {symbol}: RSI={current_rsi:.2f} "
                    f"(zona neutral {self.oversold}-{self.overbought})"
                )

        return signals

    def get_parameters(self) -> dict[str, Any]:
        """Retorna los parametros configurables de la estrategia."""
        return {
            "rsi_period": self.rsi_period,
            "overbought": self.overbought,
            "oversold": self.oversold,
        }

    def on_trade_executed(self, trade: dict[str, Any]) -> None:
        """Log post-ejecucion de trade."""
        logger.info(
            f"[{self.name}] Trade ejecutado: "
            f"{trade.get('side', '?')} {trade.get('qty', '?')} "
            f"{trade.get('symbol', '?')} @ {trade.get('price', '?')}"
        )
