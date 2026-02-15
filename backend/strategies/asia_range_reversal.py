"""
Estrategia: Reversa Rango Asia (BTC/USD)

Opera reversiones en los extremos del rango asiatico (00:00–07:00 hora Madrid).
Detecta cuando el precio toca AsiaHigh (→ SELL) o AsiaLow (→ BUY) durante
la ventana operativa de 07:30–12:00.

Especificacion completa:
    - Timeframe: M5
    - Timezone: Europe/Madrid (CET/CEST automatico)
    - Rango Asia: 00:00–06:59 → AsiaHigh, AsiaLow
    - ATR_Asia: media de True Ranges de las velas del rango Asia
    - Ventana de entradas: 07:30–12:00
    - Entrada SELL: precio toca AsiaHigh
    - Entrada BUY: precio toca AsiaLow
    - SL/TP: D = 2 * ATR_Asia, RR 1:1
    - Maximo 1 operacion por dia
    - Filtros: min 78 velas Asia, AsiaRange >= 0.8*ATR, spread <= 0.25*ATR

Maquina de estados:
    A → Construyendo Asia (00:00–07:00)
    B → Asia congelada / esperando ventana (07:00–07:30)
    C → Buscando entrada (07:30–12:00)
    D → Cerrado para el dia
"""

from __future__ import annotations

from datetime import date, time, datetime
from enum import Enum
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from loguru import logger

from backend.strategies.base_strategy import BaseStrategy, Signal


# ── Maquina de estados ────────────────────────────────────────────


class AsiaState(str, Enum):
    """Estados del ciclo diario de la estrategia."""
    BUILDING_ASIA = "A"      # 00:00–07:00  Acumulando rango Asia
    ASIA_FROZEN = "B"        # 07:00–07:30  Rango congelado, validando
    SEEKING_ENTRY = "C"      # 07:30–12:00  Buscando toque de extremos
    DONE_FOR_DAY = "D"       # Trade tomado o fuera de ventana


# ── Estrategia ────────────────────────────────────────────────────


class AsiaRangeReversal(BaseStrategy):
    """
    Reversa del Rango Asiatico.

    Opera en BTC/USD (M5) buscando reversiones cuando el precio
    toca los extremos del rango formado durante la sesion asiatica
    (00:00–07:00 hora de Madrid). Usa ATR calculado exclusivamente
    con velas de la sesion Asia para dimensionar SL/TP.
    """

    # ── Atributos de clase (registrados por el registry) ──────
    name = "reversa_rango_asia"
    description = (
        "Reversa del Rango Asia en BTC/USD (M5). "
        "Vende en AsiaHigh, compra en AsiaLow. "
        "SL/TP: 2xATR_Asia (RR 1:1). "
        "Ventana 07:30–12:00 Madrid. Max 1 trade/dia."
    )
    symbols = ["BTC/USD"]
    timeframe = "5Min"
    skip_market_check = True  # Crypto opera 24/7

    # ── Constantes de horario (Europe/Madrid) ─────────────────
    TIMEZONE = ZoneInfo("Europe/Madrid")

    ASIA_START_HOUR = 0    # 00:00
    ASIA_END_HOUR = 7      # 07:00 congela
    ENTRY_START = time(7, 30)
    ENTRY_END = time(12, 0)

    def __init__(
        self,
        atr_multiplier: float = 2.0,
        min_asia_candles: int = 78,
        min_range_ratio: float = 0.8,
        max_spread_ratio: float = 0.25,
        max_trades_per_day: int = 1,
        wick_outlier_multiplier: float = 5.0,
    ) -> None:
        """
        Args:
            atr_multiplier: Multiplicador del ATR para SL/TP (default 2.0).
            min_asia_candles: Minimo de velas Asia requeridas (default 78 = 93%).
            min_range_ratio: Ratio minimo AsiaRange/ATR (default 0.8).
            max_spread_ratio: Ratio maximo spread/ATR permitido (default 0.25).
            max_trades_per_day: Maximo de trades por dia (default 1).
            wick_outlier_multiplier: Una vela cuyo rango (H-L) supere este
                multiplo de la mediana de rangos se considera outlier y sus
                H/L se recortan al cuerpo (open/close). Default 5.0.
        """
        # ── Parametros configurables ─────────────────────────
        self.atr_multiplier = atr_multiplier
        self.min_asia_candles = min_asia_candles
        self.min_range_ratio = min_range_ratio
        self.max_spread_ratio = max_spread_ratio
        self.max_trades_per_day = max_trades_per_day
        self.wick_outlier_multiplier = wick_outlier_multiplier

        # ── Estado interno (se resetea cada dia) ─────────────
        self._state: AsiaState = AsiaState.BUILDING_ASIA
        self._current_date: Optional[date] = None

        # Niveles del rango Asia
        self._asia_high: Optional[float] = None
        self._asia_low: Optional[float] = None
        self._asia_range: float = 0.0
        self._atr_asia: float = 0.0
        self._asia_candle_count: int = 0

        # Control de operativa
        self._trade_taken: bool = False
        self._trades_today: int = 0
        self._day_enabled: bool = False

        # Parametros de la orden bracket (leidos por el engine)
        self._bracket_params: Optional[dict[str, float]] = None

        # Info del ultimo trade (para logging/dashboard)
        self._entry_price: Optional[float] = None
        self._entry_side: Optional[str] = None
        self._sl_price: Optional[float] = None
        self._tp_price: Optional[float] = None

        # Inicializar clase base (valida name, symbols)
        super().__init__()

    # ══════════════════════════════════════════════════════════════
    # ── Metodo principal: calculate_signals ──────────────────────
    # ══════════════════════════════════════════════════════════════

    def calculate_signals(
        self, data: dict[str, pd.DataFrame]
    ) -> dict[str, Signal]:
        """
        Ejecuta la maquina de estados para generar senales.

        Cada ciclo (cada 5 minutos):
          1. Obtiene la hora actual en Madrid.
          2. Si es un nuevo dia, resetea todo el estado.
          3. Segun la hora, ejecuta el estado correspondiente.
          4. Retorna la senal para BTC/USD.

        Args:
            data: {symbol: DataFrame_OHLCV} del engine.

        Returns:
            {"BTC/USD": Signal.BUY|SELL|HOLD}
        """
        signals: dict[str, Signal] = {}
        symbol = self.symbols[0]  # "BTC/USD"

        # Verificar que tenemos datos
        if symbol not in data or data[symbol].empty:
            logger.debug(f"[{self.name}] Sin datos para {symbol}")
            signals[symbol] = Signal.HOLD
            return signals

        df = data[symbol].copy()

        # Convertir timestamps a Europe/Madrid
        df = self._localize_to_madrid(df)

        # Hora actual en Madrid
        now_madrid = datetime.now(self.TIMEZONE)
        today_madrid = now_madrid.date()
        current_time = now_madrid.time()

        # ── Reset diario ─────────────────────────────────────
        if self._current_date != today_madrid:
            self._reset_day(today_madrid)

        # ── Maquina de estados ───────────────────────────────
        signal = self._run_state_machine(df, current_time, now_madrid)
        signals[symbol] = signal

        return signals

    # ══════════════════════════════════════════════════════════════
    # ── Maquina de estados ──────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def _run_state_machine(
        self,
        df: pd.DataFrame,
        current_time: time,
        now_madrid: datetime,
    ) -> Signal:
        """
        Transiciones de la maquina de estados segun la hora de Madrid.

        A (00:00–07:00) → B (07:00–07:30) → C (07:30–12:00) → D (>=12:00)
        """
        # ── Estado A: Construyendo Asia (00:00–06:59) ────────
        if current_time < time(self.ASIA_END_HOUR, 0):
            self._state = AsiaState.BUILDING_ASIA
            self._build_asia_range(df, now_madrid)
            return Signal.HOLD

        # ── Transicion A→B: Asia congelada (07:00–07:29) ─────
        if current_time < self.ENTRY_START:
            if self._state == AsiaState.BUILDING_ASIA:
                self._freeze_asia(df, now_madrid)
            self._state = AsiaState.ASIA_FROZEN
            return Signal.HOLD

        # ── Estado C: Buscando entrada (07:30–11:59) ─────────
        if current_time < self.ENTRY_END:
            # Asegurar que Asia esta congelada antes de buscar entradas
            if self._state in (AsiaState.BUILDING_ASIA, AsiaState.ASIA_FROZEN):
                if self._state == AsiaState.BUILDING_ASIA:
                    self._freeze_asia(df, now_madrid)
                self._state = AsiaState.SEEKING_ENTRY

            if self._state == AsiaState.SEEKING_ENTRY:
                if self._trade_taken or not self._day_enabled:
                    return Signal.HOLD
                return self._check_entry(df)

            return Signal.HOLD

        # ── Estado D: Cerrado para el dia (>=12:00) ──────────
        self._state = AsiaState.DONE_FOR_DAY
        return Signal.HOLD

    # ══════════════════════════════════════════════════════════════
    # ── Estado A: Construir rango Asia ──────────────────────────
    # ══════════════════════════════════════════════════════════════

    def _build_asia_range(
        self, df: pd.DataFrame, now_madrid: datetime
    ) -> None:
        """
        Acumula AsiaHigh/AsiaLow con las velas M5 entre 00:00–06:59.
        Se llama en cada ciclo durante el estado A.
        Aplica filtro de outliers para descartar mechas anomalas.
        """
        today = now_madrid.date()
        asia_bars = self._get_asia_bars(df, today)

        if asia_bars.empty:
            return

        # Filtrar mechas anomalas (flash wicks / datos sucios)
        clean_bars = self._filter_outlier_wicks(asia_bars)

        self._asia_high = float(clean_bars["high"].max())
        self._asia_low = float(clean_bars["low"].min())
        self._asia_range = self._asia_high - self._asia_low
        self._asia_candle_count = len(asia_bars)  # count original (para filtro N)

        logger.debug(
            f"[{self.name}] Asia construyendo: "
            f"H={self._asia_high:.2f} L={self._asia_low:.2f} "
            f"R={self._asia_range:.2f} N={self._asia_candle_count}"
        )

    # ══════════════════════════════════════════════════════════════
    # ── Transicion A→B: Congelar Asia y validar filtros ─────────
    # ══════════════════════════════════════════════════════════════

    def _freeze_asia(
        self, df: pd.DataFrame, now_madrid: datetime
    ) -> None:
        """
        A las 07:00: congela el rango Asia, calcula ATR_Asia y
        valida los filtros de calidad. Marca _day_enabled si todo OK.
        """
        today = now_madrid.date()
        asia_bars = self._get_asia_bars(df, today)

        if asia_bars.empty:
            logger.warning(
                f"[{self.name}] Sin velas Asia para {today}. "
                "No se opera hoy."
            )
            self._day_enabled = False
            return

        # ── Filtrar mechas anomalas (flash wicks) ───────────
        clean_bars = self._filter_outlier_wicks(asia_bars)

        # ── Calcular niveles finales (sobre datos limpios) ──
        self._asia_candle_count = len(asia_bars)  # N original para filtro de velas
        self._asia_high = float(clean_bars["high"].max())
        self._asia_low = float(clean_bars["low"].min())
        self._asia_range = self._asia_high - self._asia_low

        # ── Calcular ATR_Asia (sobre datos limpios) ─────────
        self._atr_asia = self._calculate_asia_atr(clean_bars)

        logger.info(
            f"[{self.name}] ═══ Asia congelada ({today}) ═══\n"
            f"  AsiaHigh  = {self._asia_high:.2f}\n"
            f"  AsiaLow   = {self._asia_low:.2f}\n"
            f"  Range     = {self._asia_range:.2f}\n"
            f"  ATR_Asia  = {self._atr_asia:.2f}\n"
            f"  Velas     = {self._asia_candle_count}/84"
        )

        # ── Filtro 7.1: Validacion de datos (min N velas) ────
        if self._asia_candle_count < self.min_asia_candles:
            logger.warning(
                f"[{self.name}] FILTRO: Pocas velas Asia "
                f"({self._asia_candle_count} < {self.min_asia_candles}). "
                "No se opera hoy."
            )
            self._day_enabled = False
            return

        # ── Filtro: ATR > 0 ─────────────────────────────────
        if self._atr_asia <= 0:
            logger.warning(
                f"[{self.name}] FILTRO: ATR_Asia = 0. No se opera hoy."
            )
            self._day_enabled = False
            return

        # ── Filtro 7.2: Rango minimo ────────────────────────
        min_required_range = self.min_range_ratio * self._atr_asia
        if self._asia_range < min_required_range:
            logger.warning(
                f"[{self.name}] FILTRO: Rango Asia ({self._asia_range:.2f}) "
                f"< {self.min_range_ratio} * ATR ({min_required_range:.2f}). "
                "No se opera hoy."
            )
            self._day_enabled = False
            return

        # ── Todo OK: dia habilitado ──────────────────────────
        self._day_enabled = True
        D = self.atr_multiplier * self._atr_asia
        logger.info(
            f"[{self.name}] DIA HABILITADO | "
            f"D = 2 × {self._atr_asia:.2f} = {D:.2f} | "
            f"Buscando entrada desde 07:30"
        )

    # ══════════════════════════════════════════════════════════════
    # ── Estado C: Buscar entrada ────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def _check_entry(self, df: pd.DataFrame) -> Signal:
        """
        Verifica si el precio ha tocado los extremos del rango Asia
        usando la ultima barra M5 completada.

        - high >= AsiaHigh → SELL (reversa desde el techo)
        - low  <= AsiaLow  → BUY  (reversa desde el suelo)

        Si ambos se tocan en la misma barra, desempata por cercania
        del close al extremo correspondiente.
        """
        if self._asia_high is None or self._asia_low is None:
            return Signal.HOLD

        if self._atr_asia <= 0:
            return Signal.HOLD

        if df.empty:
            return Signal.HOLD

        # Ultima barra completada
        last_bar = df.iloc[-1]
        bar_high = float(last_bar["high"])
        bar_low = float(last_bar["low"])
        bar_close = float(last_bar["close"])

        # ── Filtro 7.3: Spread ───────────────────────────────
        # Estimacion de spread desde la barra M5.
        # Para BTC/USD en Alpaca el spread real suele ser <$10 en M5.
        # Usamos una heuristica conservadora: 2% del rango de la barra.
        bar_range = bar_high - bar_low
        estimated_spread = max(bar_range * 0.02, 1.0)  # minimo $1

        max_allowed_spread = self.max_spread_ratio * self._atr_asia
        if estimated_spread > max_allowed_spread:
            logger.debug(
                f"[{self.name}] Spread estimado ({estimated_spread:.2f}) > "
                f"max ({max_allowed_spread:.2f}). Esperando..."
            )
            return Signal.HOLD

        D = self.atr_multiplier * self._atr_asia

        # ── Detectar toques ──────────────────────────────────
        touch_high = bar_high >= self._asia_high
        touch_low = bar_low <= self._asia_low

        # ── Desempate (ambos en la misma barra, muy raro) ────
        if touch_high and touch_low:
            dist_to_high = abs(bar_close - self._asia_high)
            dist_to_low = abs(bar_close - self._asia_low)
            if dist_to_high <= dist_to_low:
                # Cerro mas cerca del high → probablemente fue hacia arriba
                touch_low = False
            else:
                touch_high = False

        # ── SELL: precio toca AsiaHigh ───────────────────────
        if touch_high:
            entry_price = self._asia_high
            sl = entry_price + D
            tp = entry_price - D

            self._bracket_params = {
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
            }
            self._entry_price = entry_price
            self._entry_side = "SELL"
            self._sl_price = sl
            self._tp_price = tp
            self._trade_taken = True
            self._trades_today += 1

            logger.info(
                f"[{self.name}] ═══ SELL SIGNAL ═══\n"
                f"  Entry = {entry_price:.2f} (AsiaHigh)\n"
                f"  SL    = {sl:.2f} (+{D:.2f})\n"
                f"  TP    = {tp:.2f} (-{D:.2f})\n"
                f"  D     = {D:.2f} (2 × ATR {self._atr_asia:.2f})\n"
                f"  Bar   = H:{bar_high:.2f} L:{bar_low:.2f} C:{bar_close:.2f}"
            )
            return Signal.SELL

        # ── BUY: precio toca AsiaLow ─────────────────────────
        if touch_low:
            entry_price = self._asia_low
            sl = entry_price - D
            tp = entry_price + D

            self._bracket_params = {
                "take_profit": round(tp, 2),
                "stop_loss": round(sl, 2),
            }
            self._entry_price = entry_price
            self._entry_side = "BUY"
            self._sl_price = sl
            self._tp_price = tp
            self._trade_taken = True
            self._trades_today += 1

            logger.info(
                f"[{self.name}] ═══ BUY SIGNAL ═══\n"
                f"  Entry = {entry_price:.2f} (AsiaLow)\n"
                f"  SL    = {sl:.2f} (-{D:.2f})\n"
                f"  TP    = {tp:.2f} (+{D:.2f})\n"
                f"  D     = {D:.2f} (2 × ATR {self._atr_asia:.2f})\n"
                f"  Bar   = H:{bar_high:.2f} L:{bar_low:.2f} C:{bar_close:.2f}"
            )
            return Signal.BUY

        return Signal.HOLD

    # ══════════════════════════════════════════════════════════════
    # ── Helpers ─────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def _reset_day(self, today: date) -> None:
        """Resetea todo el estado interno al inicio de un nuevo dia (00:00 Madrid)."""
        logger.info(f"[{self.name}] ─── Nuevo dia: {today} ───")
        self._current_date = today
        self._state = AsiaState.BUILDING_ASIA
        self._asia_high = None
        self._asia_low = None
        self._asia_range = 0.0
        self._atr_asia = 0.0
        self._asia_candle_count = 0
        self._trade_taken = False
        self._trades_today = 0
        self._day_enabled = False
        self._bracket_params = None
        self._entry_price = None
        self._entry_side = None
        self._sl_price = None
        self._tp_price = None

    def _get_asia_bars(
        self, df: pd.DataFrame, today: date
    ) -> pd.DataFrame:
        """
        Filtra velas M5 de la sesion asiatica (00:00–06:59 Madrid)
        del dia especificado.

        Args:
            df: DataFrame con indice DatetimeIndex (ya en Europe/Madrid).
            today: Fecha del dia en Madrid.

        Returns:
            DataFrame filtrado con solo las velas de la sesion Asia.
        """
        if df.empty:
            return df

        idx = df.index

        # Filtrar: mismo dia + hora < 7 (00:00–06:59)
        mask = (idx.date == today) & (idx.hour < self.ASIA_END_HOUR)

        result = df.loc[mask]
        return result

    def _filter_outlier_wicks(
        self, asia_bars: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Filtra mechas anomalas (flash wicks / datos sucios) de las velas
        del rango asiatico.

        Estrategia:
            1. Calcula el rango (H-L) de cada vela.
            2. Calcula la mediana de esos rangos.
            3. Si una vela tiene un rango > wick_outlier_multiplier * mediana,
               se recortan sus H/L al rango del cuerpo (max/min de open/close).
               Esto preserva la vela (para el count) pero elimina la mecha
               anomala del calculo de AsiaHigh/AsiaLow.

        Esto protege contra flash crashes, bad ticks y datos sucios que
        los exchanges a veces reportan en velas de baja liquidez.

        Returns:
            DataFrame con H/L recortados donde se detecten outliers.
        """
        if len(asia_bars) < 3:
            return asia_bars

        bars = asia_bars.copy()
        bar_ranges = bars["high"] - bars["low"]
        median_range = float(np.median(bar_ranges))

        if median_range <= 0:
            return bars

        threshold = self.wick_outlier_multiplier * median_range
        outlier_mask = bar_ranges > threshold

        n_outliers = int(outlier_mask.sum())
        if n_outliers > 0:
            # Recortar H/L al cuerpo de la vela (open/close)
            body_high = bars[["open", "close"]].max(axis=1)
            body_low = bars[["open", "close"]].min(axis=1)

            bars.loc[outlier_mask, "high"] = body_high[outlier_mask]
            bars.loc[outlier_mask, "low"] = body_low[outlier_mask]

            for idx_val in bars.index[outlier_mask]:
                orig_h = float(asia_bars.loc[idx_val, "high"])
                orig_l = float(asia_bars.loc[idx_val, "low"])
                new_h = float(bars.loc[idx_val, "high"])
                new_l = float(bars.loc[idx_val, "low"])
                orig_range = orig_h - orig_l
                logger.warning(
                    f"[{self.name}] OUTLIER detectado en {idx_val}: "
                    f"H={orig_h:.2f} L={orig_l:.2f} "
                    f"rango={orig_range:.2f} "
                    f"(mediana={median_range:.2f}, "
                    f"umbral={threshold:.2f}). "
                    f"Recortado a H={new_h:.2f} L={new_l:.2f}"
                )

            logger.info(
                f"[{self.name}] Filtro outliers: {n_outliers} vela(s) "
                f"recortada(s) de {len(bars)} totales."
            )

        return bars

    @staticmethod
    def _calculate_asia_atr(asia_bars: pd.DataFrame) -> float:
        """
        Calcula ATR usando exclusivamente las velas de la sesion Asia.

        Para cada vela i:
            TR_i = max(high_i - low_i,
                       abs(high_i - close_{i-1}),
                       abs(low_i  - close_{i-1}))

        ATR_Asia = sum(TR_i) / N

        Args:
            asia_bars: DataFrame con velas de la sesion Asia (OHLCV).

        Returns:
            ATR_Asia (media simple de TRs). 0.0 si datos insuficientes.
        """
        n = len(asia_bars)
        if n < 2:
            return 0.0

        highs = asia_bars["high"].values
        lows = asia_bars["low"].values
        closes = asia_bars["close"].values

        trs: list[float] = []
        for i in range(n):
            hl = float(highs[i] - lows[i])
            if i == 0:
                # Primera vela: solo high-low (no tenemos close anterior)
                tr = hl
            else:
                hc = abs(float(highs[i]) - float(closes[i - 1]))
                lc = abs(float(lows[i]) - float(closes[i - 1]))
                tr = max(hl, hc, lc)
            trs.append(tr)

        return sum(trs) / len(trs) if trs else 0.0

    def _localize_to_madrid(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Convierte los timestamps del DataFrame a Europe/Madrid.

        Alpaca devuelve timestamps en UTC. Los convertimos a Madrid
        para evaluar correctamente los horarios de la sesion.
        """
        if df.empty:
            return df

        idx = df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            df.index = idx.tz_convert(self.TIMEZONE)
        else:
            # Sin timezone → asumir UTC
            df.index = idx.tz_localize("UTC").tz_convert(self.TIMEZONE)

        return df

    # ══════════════════════════════════════════════════════════════
    # ── Interfaz BaseStrategy ───────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def get_parameters(self) -> dict[str, Any]:
        """
        Retorna parametros configurables y estado actual.
        Se muestra en el dashboard y API.
        """
        return {
            "atr_multiplier": self.atr_multiplier,
            "min_asia_candles": self.min_asia_candles,
            "min_range_ratio": self.min_range_ratio,
            "max_spread_ratio": self.max_spread_ratio,
            "max_trades_per_day": self.max_trades_per_day,
            "wick_outlier_multiplier": self.wick_outlier_multiplier,
            # Estado actual (informativo)
            "state": self._state.value if self._state else "?",
            "asia_high": self._asia_high,
            "asia_low": self._asia_low,
            "asia_range": round(self._asia_range, 2) if self._asia_range else None,
            "atr_asia": round(self._atr_asia, 2) if self._atr_asia else None,
            "asia_candles": self._asia_candle_count,
            "day_enabled": self._day_enabled,
            "trade_taken": self._trade_taken,
            "entry_price": self._entry_price,
            "entry_side": self._entry_side,
            "sl_price": self._sl_price,
            "tp_price": self._tp_price,
        }

    def on_trade_executed(self, trade: dict[str, Any]) -> None:
        """Callback post-ejecucion de trade."""
        logger.info(
            f"[{self.name}] ═══ TRADE EJECUTADO ═══\n"
            f"  {trade.get('side', '?')} {trade.get('qty', '?')} "
            f"{trade.get('symbol', '?')} @ {trade.get('price', '?')}\n"
            f"  Order ID: {trade.get('order_id', '?')}\n"
            f"  AsiaHigh={self._asia_high} | AsiaLow={self._asia_low}\n"
            f"  ATR_Asia={self._atr_asia:.2f} | "
            f"SL={self._sl_price} | TP={self._tp_price}"
        )

    def on_start(self) -> None:
        """Inicializacion al arrancar la estrategia."""
        logger.info(
            f"[{self.name}] Arrancada |\n"
            f"  Symbol: {self.symbols[0]}\n"
            f"  Timeframe: {self.timeframe}\n"
            f"  ATR Multiplier: {self.atr_multiplier}\n"
            f"  Timezone: Europe/Madrid\n"
            f"  Ventana Asia: 00:00–07:00\n"
            f"  Ventana Entradas: 07:30–12:00"
        )

    def on_stop(self) -> None:
        """Limpieza al detener la estrategia."""
        logger.info(
            f"[{self.name}] Detenida | "
            f"Estado={self._state.value} | "
            f"Trades hoy={self._trades_today} | "
            f"Day enabled={self._day_enabled}"
        )
