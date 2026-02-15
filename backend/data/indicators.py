"""
Calculos de indicadores tecnicos: SMA, EMA, RSI, MACD, ATR, Stochastic, etc.
Usa pandas-ta como base.

Cada funcion recibe un DataFrame con al menos la columna 'close'
(y 'high', 'low' para algunos indicadores) y retorna el DataFrame
original con la(s) columna(s) del indicador anadida(s).

Convenciones:
    - Los nombres de columna siguen el patron INDICADOR_PERIODO (e.g. SMA_20, RSI_14).
    - Cuando un indicador no puede calcularse (datos insuficientes), la columna
      se rellena con NaN y se emite un warning.
    - Las funciones mutan el DataFrame in-place y lo retornan (permite encadenamiento).
"""

from typing import Any

import pandas as pd
import pandas_ta as ta
from loguru import logger


# ── Medias moviles ───────────────────────────────────────────────


def add_sma(df: pd.DataFrame, period: int, column: str = "close") -> pd.DataFrame:
    """
    Anade una columna SMA_{period} al DataFrame.

    Args:
        df: DataFrame con datos OHLCV.
        period: Numero de periodos para la media.
        column: Columna de origen (por defecto 'close').

    Returns:
        El mismo DataFrame con la columna SMA_{period} anadida.
    """
    col_name = f"SMA_{period}"
    result = ta.sma(df[column], length=period)
    if result is not None:
        df[col_name] = result
    else:
        logger.warning(f"No se pudo calcular SMA({period}) — datos insuficientes")
        df[col_name] = float("nan")
    return df


def add_ema(df: pd.DataFrame, period: int, column: str = "close") -> pd.DataFrame:
    """
    Anade una columna EMA_{period} al DataFrame.

    Args:
        df: DataFrame con datos OHLCV.
        period: Numero de periodos para la media exponencial.
        column: Columna de origen (por defecto 'close').

    Returns:
        El mismo DataFrame con la columna EMA_{period} anadida.
    """
    col_name = f"EMA_{period}"
    result = ta.ema(df[column], length=period)
    if result is not None:
        df[col_name] = result
    else:
        logger.warning(f"No se pudo calcular EMA({period}) — datos insuficientes")
        df[col_name] = float("nan")
    return df


# ── Osciladores ──────────────────────────────────────────────────


def add_rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.DataFrame:
    """
    Anade una columna RSI_{period} al DataFrame.

    Args:
        df: DataFrame con datos OHLCV.
        period: Numero de periodos (por defecto 14).
        column: Columna de origen.

    Returns:
        El mismo DataFrame con la columna RSI_{period} anadida.
    """
    col_name = f"RSI_{period}"
    result = ta.rsi(df[column], length=period)
    if result is not None:
        df[col_name] = result
    else:
        logger.warning(f"No se pudo calcular RSI({period}) — datos insuficientes")
        df[col_name] = float("nan")
    return df


def add_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    column: str = "close",
) -> pd.DataFrame:
    """
    Anade columnas MACD, MACDs (signal), MACDh (histograma) al DataFrame.

    Args:
        df: DataFrame con datos OHLCV.
        fast: Periodo rapido (por defecto 12).
        slow: Periodo lento (por defecto 26).
        signal: Periodo de la linea signal (por defecto 9).
        column: Columna de origen.

    Returns:
        El mismo DataFrame con columnas MACD_12_26_9, MACDs_12_26_9, MACDh_12_26_9.
    """
    result = ta.macd(df[column], fast=fast, slow=slow, signal=signal)
    if result is not None:
        df = pd.concat([df, result], axis=1)
    else:
        logger.warning(
            f"No se pudo calcular MACD({fast},{slow},{signal}) — datos insuficientes"
        )
        suffix = f"{fast}_{slow}_{signal}"
        for col in [f"MACD_{suffix}", f"MACDs_{suffix}", f"MACDh_{suffix}"]:
            df[col] = float("nan")
    return df


def add_stochastic(
    df: pd.DataFrame,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> pd.DataFrame:
    """
    Anade el oscilador estocastico (%K y %D) al DataFrame.

    El estocastico mide la posicion del precio de cierre relativo al
    rango high-low durante un periodo. Valores por encima de 80 indican
    sobrecompra; por debajo de 20, sobreventa.

    Columnas anadidas:
        - STOCHk_{k}_{d}_{smooth}: Linea %K (mas rapida).
        - STOCHd_{k}_{d}_{smooth}: Linea %D (signal, media de %K).

    Args:
        df: DataFrame con columnas high, low, close.
        k_period: Periodo para %K (por defecto 14).
        d_period: Periodo de suavizado para %D (por defecto 3).
        smooth_k: Suavizado de %K (por defecto 3).

    Returns:
        El mismo DataFrame con las columnas del estocastico anadidas.
    """
    result = ta.stoch(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        k=k_period,
        d=d_period,
        smooth_k=smooth_k,
    )
    if result is not None:
        df = pd.concat([df, result], axis=1)
    else:
        logger.warning(
            f"No se pudo calcular Stochastic({k_period},{d_period},{smooth_k}) "
            "— datos insuficientes"
        )
        suffix = f"{k_period}_{d_period}_{smooth_k}"
        df[f"STOCHk_{suffix}"] = float("nan")
        df[f"STOCHd_{suffix}"] = float("nan")
    return df


# ── Volatilidad ──────────────────────────────────────────────────


def add_bbands(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
    column: str = "close",
) -> pd.DataFrame:
    """
    Anade Bollinger Bands: BBL (lower), BBM (mid), BBU (upper), BBB (bandwidth), BBP (percent).

    Args:
        df: DataFrame con datos OHLCV.
        period: Periodo (por defecto 20).
        std: Desviaciones estandar (por defecto 2.0).
        column: Columna de origen.

    Returns:
        El mismo DataFrame con las columnas de Bollinger Bands anadidas.
    """
    result = ta.bbands(df[column], length=period, std=std)
    if result is not None:
        df = pd.concat([df, result], axis=1)
    else:
        logger.warning(
            f"No se pudo calcular BBands({period},{std}) — datos insuficientes"
        )
    return df


def add_atr(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.DataFrame:
    """
    Anade el Average True Range (ATR) al DataFrame.

    El ATR mide la volatilidad del activo. Es esencial para:
    - Dimensionar posiciones (position sizing).
    - Colocar stop-losses dinamicos.
    - Filtrar mercados por volatilidad.

    Columna anadida: ATR_{period}

    Args:
        df: DataFrame con columnas high, low, close.
        period: Periodo para el ATR (por defecto 14).

    Returns:
        El mismo DataFrame con la columna ATR_{period} anadida.
    """
    col_name = f"ATR_{period}"
    result = ta.atr(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        length=period,
    )
    if result is not None:
        df[col_name] = result
    else:
        logger.warning(f"No se pudo calcular ATR({period}) — datos insuficientes")
        df[col_name] = float("nan")
    return df


# ── Tendencia ────────────────────────────────────────────────────


def add_adx(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.DataFrame:
    """
    Anade el Average Directional Index (ADX) y lineas DI al DataFrame.

    El ADX mide la fuerza de la tendencia (sin importar la direccion):
    - ADX > 25: tendencia fuerte.
    - ADX < 20: mercado lateral / sin tendencia.
    - DMP (DI+) > DMN (DI-): tendencia alcista.
    - DMN (DI-) > DMP (DI+): tendencia bajista.

    Columnas anadidas:
        - ADX_{period}: Valor del ADX.
        - DMP_{period}: DI+ (Directional Movement Plus).
        - DMN_{period}: DI- (Directional Movement Minus).

    Args:
        df: DataFrame con columnas high, low, close.
        period: Periodo (por defecto 14).

    Returns:
        El mismo DataFrame con las columnas de ADX anadidas.
    """
    result = ta.adx(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        length=period,
    )
    if result is not None:
        df = pd.concat([df, result], axis=1)
    else:
        logger.warning(f"No se pudo calcular ADX({period}) — datos insuficientes")
        df[f"ADX_{period}"] = float("nan")
        df[f"DMP_{period}"] = float("nan")
        df[f"DMN_{period}"] = float("nan")
    return df


# ── Volumen ──────────────────────────────────────────────────────


def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Anade el On Balance Volume (OBV) al DataFrame.

    El OBV acumula volumen sumandolo cuando el precio sube
    y restandolo cuando baja. Divergencias entre OBV y precio
    pueden anticipar cambios de tendencia.

    Columna anadida: OBV

    Args:
        df: DataFrame con columnas close, volume.

    Returns:
        El mismo DataFrame con la columna OBV anadida.
    """
    result = ta.obv(close=df["close"], volume=df["volume"])
    if result is not None:
        df["OBV"] = result
    else:
        logger.warning("No se pudo calcular OBV — datos insuficientes")
        df["OBV"] = float("nan")
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Anade el Volume Weighted Average Price (VWAP) al DataFrame.

    El VWAP es un benchmark intradiario que pondera el precio promedio
    por volumen. Se usa frecuentemente para:
    - Evaluar si una compra fue a buen precio (debajo de VWAP).
    - Soporte/resistencia intradiario.

    Nota: VWAP se reinicia cada dia. Funciona mejor con datos intradiarios.

    Columna anadida: VWAP

    Args:
        df: DataFrame con columnas high, low, close, volume.

    Returns:
        El mismo DataFrame con la columna VWAP anadida.
    """
    result = ta.vwap(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        volume=df["volume"],
    )
    if result is not None:
        # pandas-ta nombra la columna como VWAP_D por defecto
        if isinstance(result, pd.Series):
            df["VWAP"] = result
        else:
            # Si retorna DataFrame, tomar la primera columna
            df["VWAP"] = result.iloc[:, 0]
    else:
        logger.warning("No se pudo calcular VWAP — datos insuficientes")
        df["VWAP"] = float("nan")
    return df


# ── Utilidades ───────────────────────────────────────────────────


def crossover(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """
    Detecta cruce alcista: series_a cruza POR ENCIMA de series_b.

    Retorna una Serie booleana donde True indica que en esa barra
    series_a paso de estar debajo a estar encima de series_b.
    """
    prev_a = series_a.shift(1)
    prev_b = series_b.shift(1)
    return (prev_a <= prev_b) & (series_a > series_b)


def crossunder(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    """
    Detecta cruce bajista: series_a cruza POR DEBAJO de series_b.

    Retorna una Serie booleana donde True indica que en esa barra
    series_a paso de estar encima a estar debajo de series_b.
    """
    prev_a = series_a.shift(1)
    prev_b = series_b.shift(1)
    return (prev_a >= prev_b) & (series_a < series_b)


def validate_dataframe(df: pd.DataFrame, required_columns: list[str] | None = None) -> bool:
    """
    Valida que el DataFrame tenga las columnas necesarias y no este vacio.

    Args:
        df: DataFrame a validar.
        required_columns: Columnas requeridas (por defecto OHLCV).

    Returns:
        True si es valido, False en caso contrario.
    """
    if required_columns is None:
        required_columns = ["open", "high", "low", "close", "volume"]

    if df is None or df.empty:
        logger.warning("DataFrame vacio o None")
        return False

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        logger.warning(f"Columnas faltantes en DataFrame: {missing}")
        return False

    return True


# ── Batch / Conveniencia ─────────────────────────────────────────


def add_common_indicators(
    df: pd.DataFrame,
    sma_periods: list[int] | None = None,
    ema_periods: list[int] | None = None,
    rsi_period: int = 14,
    macd: bool = True,
    bbands: bool = True,
    atr_period: int = 14,
    adx_period: int = 14,
    obv: bool = True,
) -> pd.DataFrame:
    """
    Funcion de conveniencia que aplica un conjunto estandar de indicadores
    de una sola vez.

    Ideal para exploracion rapida o para estrategias que necesitan
    multiples indicadores. Cada indicador es opcional y configurable.

    Args:
        df: DataFrame con columnas OHLCV.
        sma_periods: Lista de periodos SMA (default [10, 20, 50, 200]).
        ema_periods: Lista de periodos EMA (default [12, 26]).
        rsi_period: Periodo RSI (0 para omitir).
        macd: Si True, agrega MACD(12,26,9).
        bbands: Si True, agrega Bollinger Bands(20,2).
        atr_period: Periodo ATR (0 para omitir).
        adx_period: Periodo ADX (0 para omitir).
        obv: Si True, agrega OBV.

    Returns:
        El mismo DataFrame con todos los indicadores solicitados anadidos.
    """
    if not validate_dataframe(df):
        logger.warning(
            "add_common_indicators: DataFrame no valido, retornando sin cambios"
        )
        return df

    if sma_periods is None:
        sma_periods = [10, 20, 50, 200]
    if ema_periods is None:
        ema_periods = [12, 26]

    # Medias moviles
    for period in sma_periods:
        df = add_sma(df, period)
    for period in ema_periods:
        df = add_ema(df, period)

    # Osciladores
    if rsi_period > 0:
        df = add_rsi(df, rsi_period)
    if macd:
        df = add_macd(df)

    # Volatilidad
    if bbands:
        df = add_bbands(df)
    if atr_period > 0:
        df = add_atr(df, atr_period)

    # Tendencia
    if adx_period > 0:
        df = add_adx(df, adx_period)

    # Volumen
    if obv:
        df = add_obv(df)

    logger.debug(
        f"add_common_indicators: {len(df.columns)} columnas totales "
        f"({len(df)} barras)"
    )
    return df


def get_indicator_summary(df: pd.DataFrame) -> dict[str, Any]:
    """
    Genera un resumen de los valores actuales (ultima barra) de los
    indicadores presentes en el DataFrame.

    Util para logging, dashboards o depuracion rapida.

    Args:
        df: DataFrame con indicadores ya calculados.

    Returns:
        Diccionario {nombre_indicador: ultimo_valor}.
        Solo incluye columnas que no son OHLCV basicas.
    """
    base_cols = {"open", "high", "low", "close", "volume"}
    if df.empty:
        return {}

    last_row = df.iloc[-1]
    summary: dict[str, Any] = {}

    for col in df.columns:
        if col not in base_cols:
            value = last_row[col]
            # Convertir numpy types a Python nativos para serializacion
            if pd.notna(value):
                summary[col] = round(float(value), 4)
            else:
                summary[col] = None

    return summary
