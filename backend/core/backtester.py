"""
Motor de backtesting.

Simula la ejecucion de una estrategia sobre datos historicos,
registrando trades, equity curve y metricas de rendimiento.

El backtester reutiliza las mismas estrategias (BaseStrategy) que se
usan en trading en vivo, garantizando que el backtest sea representativo.

Flujo:
    1. Carga datos historicos (local / Yahoo Finance).
    2. Recorre las barras cronologicamente.
    3. En cada barra: alimenta la estrategia con una ventana de datos.
    4. Las senales (BUY/SELL) se ejecutan al open de la SIGUIENTE barra
       (sin look-ahead bias).
    5. Al finalizar, calcula metricas de rendimiento.

Uso:
    from backend.core.backtester import Backtester, BacktestConfig
    from backend.strategies.sma_crossover import SMACrossover

    config = BacktestConfig(
        strategy=SMACrossover(fast_period=10, slow_period=20),
        start_date="2020-01-01",
        end_date="2025-01-01",
        initial_capital=100_000,
    )

    bt = Backtester(config)
    result = bt.run()

    print(result.metrics)
    print(result.trades_df)
    result.equity_curve.plot()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd
from loguru import logger

from backend.data.market_data import MarketDataService
from backend.strategies.base_strategy import BaseStrategy, Signal


# ── Configuracion ────────────────────────────────────────────────


@dataclass
class BacktestConfig:
    """
    Configuracion para ejecutar un backtest.

    Attributes:
        strategy: Instancia de la estrategia a backtear.
        start_date: Fecha de inicio del backtest ("YYYY-MM-DD" o datetime).
        end_date: Fecha de fin del backtest ("YYYY-MM-DD" o datetime).
        initial_capital: Capital inicial en USD (default 100k).
        commission_per_trade: Comision por operacion en USD (default 0 — Alpaca es gratis).
        position_size_pct: Porcentaje del equity a invertir por posicion (default 10%).
        max_positions: Numero maximo de posiciones simultaneas (default 10).
        allow_short: Permitir ventas en corto (default False — solo long).
        timeframe: Override del timeframe de la estrategia (opcional).
    """
    strategy: BaseStrategy
    start_date: str | datetime
    end_date: str | datetime
    initial_capital: float = 100_000.0
    commission_per_trade: float = 0.0
    position_size_pct: float = 0.10
    max_positions: int = 10
    allow_short: bool = False
    timeframe: Optional[str] = None

    @property
    def effective_timeframe(self) -> str:
        """Timeframe a usar (override o el de la estrategia)."""
        return self.timeframe or self.strategy.timeframe


# ── Trade record ─────────────────────────────────────────────────


@dataclass
class BacktestTrade:
    """Registro de una operacion completada (entry + exit)."""
    symbol: str
    side: str                   # "BUY" (long entry) o "SELL" (short entry)
    qty: float
    entry_price: float
    entry_date: datetime
    exit_price: float
    exit_date: datetime
    commission: float
    pnl: float                  # Beneficio/perdida neto (despues de comisiones)
    pnl_pct: float              # Retorno porcentual
    bars_held: int              # Numero de barras que se mantuvo la posicion


# ── Open position (internal) ────────────────────────────────────


@dataclass
class _OpenPosition:
    """Posicion abierta durante el backtest (uso interno)."""
    symbol: str
    side: str
    qty: float
    entry_price: float
    entry_date: datetime
    entry_bar_idx: int


# ── Resultado ────────────────────────────────────────────────────


@dataclass
class BacktestResult:
    """
    Resultado completo de un backtest.

    Contiene el equity curve, historial de trades y metricas
    de rendimiento calculadas.
    """
    config: BacktestConfig
    equity_curve: pd.Series             # Serie temporal con el valor del portfolio
    trades: list[BacktestTrade]         # Lista de trades completados
    signals_log: list[dict]             # Log de todas las senales generadas
    metrics: dict[str, Any]             # Metricas de rendimiento
    daily_returns: pd.Series            # Retornos diarios
    data_used: dict[str, pd.DataFrame]  # Datos historicos utilizados

    @property
    def trades_df(self) -> pd.DataFrame:
        """Retorna los trades como DataFrame para analisis facil."""
        if not self.trades:
            return pd.DataFrame()

        records = []
        for t in self.trades:
            records.append({
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "entry_price": t.entry_price,
                "entry_date": t.entry_date,
                "exit_price": t.exit_price,
                "exit_date": t.exit_date,
                "commission": t.commission,
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 4),
                "bars_held": t.bars_held,
            })

        return pd.DataFrame(records)

    def print_summary(self) -> None:
        """Imprime un resumen legible del backtest."""
        m = self.metrics
        print("\n" + "=" * 60)
        print(f"  BACKTEST: {self.config.strategy.name}")
        print(f"  {self.config.start_date} → {self.config.end_date}")
        print("=" * 60)
        print(f"  Capital inicial:    ${self.config.initial_capital:>12,.2f}")
        print(f"  Capital final:      ${m['final_equity']:>12,.2f}")
        print(f"  Retorno total:      {m['total_return_pct']:>12.2f}%")
        print(f"  Retorno anualizado: {m['annualized_return_pct']:>12.2f}%")
        print("-" * 60)
        print(f"  Sharpe ratio:       {m['sharpe_ratio']:>12.3f}")
        print(f"  Max drawdown:       {m['max_drawdown_pct']:>12.2f}%")
        print(f"  Volatilidad anual:  {m['annual_volatility_pct']:>12.2f}%")
        print("-" * 60)
        print(f"  Total trades:       {m['total_trades']:>12d}")
        print(f"  Trades ganadores:   {m['winning_trades']:>12d}")
        print(f"  Trades perdedores:  {m['losing_trades']:>12d}")
        print(f"  Win rate:           {m['win_rate_pct']:>12.1f}%")
        print(f"  Profit factor:      {m['profit_factor']:>12.3f}")
        print(f"  Avg trade PnL:      ${m['avg_trade_pnl']:>12,.2f}")
        print(f"  Avg winner:         ${m['avg_winner']:>12,.2f}")
        print(f"  Avg loser:          ${m['avg_loser']:>12,.2f}")
        print(f"  Avg bars held:      {m['avg_bars_held']:>12.1f}")
        print("-" * 60)
        print(f"  Comisiones totales: ${m['total_commissions']:>12,.2f}")
        print("=" * 60 + "\n")


# ── Motor de backtesting ─────────────────────────────────────────


class Backtester:
    """
    Motor de backtesting que simula la ejecucion de una estrategia
    sobre datos historicos.
    """

    def __init__(
        self,
        config: BacktestConfig,
        market_data: Optional[MarketDataService] = None,
    ) -> None:
        """
        Args:
            config: Configuracion del backtest.
            market_data: Servicio de datos. Si no se provee, crea uno nuevo.
        """
        self._config = config
        self._mds = market_data or MarketDataService()

        # Estado del backtest
        self._cash: float = 0.0
        self._positions: dict[str, _OpenPosition] = {}
        self._closed_trades: list[BacktestTrade] = []
        self._signals_log: list[dict] = []
        self._equity_history: list[tuple[datetime, float]] = []

    def run(self) -> BacktestResult:
        """
        Ejecuta el backtest completo.

        Returns:
            BacktestResult con equity curve, trades y metricas.
        """
        strategy = self._config.strategy
        timeframe = self._config.effective_timeframe

        logger.info(
            f"═══ BACKTEST START ═══ "
            f"Estrategia: {strategy.name} | "
            f"Simbolos: {strategy.symbols} | "
            f"Timeframe: {timeframe} | "
            f"Periodo: {self._config.start_date} → {self._config.end_date} | "
            f"Capital: ${self._config.initial_capital:,.2f}"
        )

        # ── 1. Cargar datos historicos ─────────────────────────
        data = self._mds.get_historical_data(
            symbols=strategy.symbols,
            timeframe=timeframe,
            start=self._config.start_date,
            end=self._config.end_date,
        )

        if not data:
            raise ValueError(
                "No se pudieron obtener datos historicos para ningun simbolo. "
                "Ejecuta download_and_store() primero."
            )

        # Verificar que tenemos datos para al menos un simbolo
        available_symbols = list(data.keys())
        logger.info(f"Datos cargados para: {available_symbols}")

        # ── 2. Construir indice temporal comun ─────────────────
        # Usar la union de todos los timestamps
        all_timestamps = set()
        for df in data.values():
            all_timestamps.update(df.index.tolist())
        timeline = sorted(all_timestamps)

        if len(timeline) < 2:
            raise ValueError(
                f"Datos insuficientes: solo {len(timeline)} barras. "
                "Se necesitan al menos 2."
            )

        logger.info(
            f"Timeline: {len(timeline)} barras "
            f"({timeline[0]} → {timeline[-1]})"
        )

        # ── 3. Inicializar estado ──────────────────────────────
        self._cash = self._config.initial_capital
        self._positions = {}
        self._closed_trades = []
        self._signals_log = []
        self._equity_history = []

        # Arrancar la estrategia
        strategy.start()

        # ── 4. Determinar lookback necesario ───────────────────
        # Usar los parametros de la estrategia para estimar lookback
        params = strategy.get_parameters()
        lookback = self._estimate_lookback(params)
        logger.info(f"Lookback estimado: {lookback} barras")

        # ── 5. Loop principal ──────────────────────────────────
        pending_signals: dict[str, Signal] = {}

        for i, current_time in enumerate(timeline):
            # ── 5a. Ejecutar senales pendientes del ciclo anterior ──
            if pending_signals:
                self._execute_signals(
                    signals=pending_signals,
                    data=data,
                    timeline=timeline,
                    bar_idx=i,
                )
                pending_signals = {}

            # ── 5b. Calcular equity al cierre de esta barra ──
            equity = self._calculate_equity(data, current_time)
            self._equity_history.append((current_time, equity))

            # ── 5c. Generar senales si tenemos suficiente lookback ──
            if i < lookback:
                continue

            # Construir ventana de datos hasta la barra actual (inclusive)
            window = self._build_data_window(data, timeline, i)

            if not window:
                continue

            # Ejecutar la estrategia
            try:
                signals = strategy.run(window)
            except Exception as e:
                logger.warning(
                    f"Error en estrategia en barra {i} ({current_time}): {e}"
                )
                # Reiniciar estrategia tras error
                strategy._status = strategy._status.RUNNING
                continue

            # Registrar senales
            active_signals = {
                sym: sig for sym, sig in signals.items()
                if sig != Signal.HOLD
            }
            if active_signals:
                self._signals_log.append({
                    "bar_idx": i,
                    "timestamp": current_time,
                    "signals": {s: sig.value for s, sig in active_signals.items()},
                })

            # Las senales se ejecutan en la SIGUIENTE barra
            pending_signals = active_signals

        # ── 6. Cerrar posiciones abiertas al final ─────────────
        self._close_all_positions(data, timeline, len(timeline) - 1)

        # Equity final
        final_time = timeline[-1]
        final_equity = self._calculate_equity(data, final_time)
        self._equity_history.append((final_time, final_equity))

        # Detener estrategia
        strategy.stop()

        # ── 7. Construir resultado ─────────────────────────────
        equity_series = pd.Series(
            data=[eq for _, eq in self._equity_history],
            index=pd.DatetimeIndex([t for t, _ in self._equity_history]),
            name="equity",
        )
        # Eliminar duplicados en el indice (mantener ultimo)
        equity_series = equity_series[~equity_series.index.duplicated(keep="last")]

        metrics = self._calculate_metrics(equity_series, self._closed_trades)

        result = BacktestResult(
            config=self._config,
            equity_curve=equity_series,
            trades=self._closed_trades,
            signals_log=self._signals_log,
            metrics=metrics,
            daily_returns=equity_series.pct_change().dropna(),
            data_used=data,
        )

        logger.info(
            f"═══ BACKTEST END ═══ "
            f"Retorno: {metrics['total_return_pct']:.2f}% | "
            f"Sharpe: {metrics['sharpe_ratio']:.3f} | "
            f"Trades: {metrics['total_trades']} | "
            f"Win rate: {metrics['win_rate_pct']:.1f}%"
        )

        return result

    # ── Ejecucion de senales ─────────────────────────────────────

    def _execute_signals(
        self,
        signals: dict[str, Signal],
        data: dict[str, pd.DataFrame],
        timeline: list,
        bar_idx: int,
    ) -> None:
        """Ejecuta senales pendientes al open de la barra actual."""
        for symbol, signal in signals.items():
            if symbol not in data:
                continue

            df = data[symbol]
            current_time = timeline[bar_idx]

            # Buscar la barra mas cercana a current_time
            bar = self._get_bar_at(df, current_time)
            if bar is None:
                continue

            exec_price = bar["open"]

            if signal == Signal.BUY:
                self._open_long(symbol, exec_price, current_time, bar_idx)

            elif signal == Signal.SELL:
                if symbol in self._positions:
                    self._close_position(symbol, exec_price, current_time, bar_idx)
                elif self._config.allow_short:
                    self._open_short(symbol, exec_price, current_time, bar_idx)

    def _open_long(
        self, symbol: str, price: float, time: datetime, bar_idx: int
    ) -> None:
        """Abre una posicion larga."""
        # No duplicar posiciones
        if symbol in self._positions:
            return

        # Verificar limite de posiciones
        if len(self._positions) >= self._config.max_positions:
            logger.debug(
                f"Max posiciones alcanzado ({self._config.max_positions}), "
                f"ignorando BUY {symbol}"
            )
            return

        # Calcular cantidad
        equity = self._cash + sum(
            pos.qty * price for pos in self._positions.values()
        )
        position_value = equity * self._config.position_size_pct
        qty = position_value / price

        if qty <= 0 or position_value > self._cash:
            logger.debug(f"Capital insuficiente para BUY {symbol}")
            return

        cost = qty * price + self._config.commission_per_trade
        self._cash -= cost

        self._positions[symbol] = _OpenPosition(
            symbol=symbol,
            side="BUY",
            qty=qty,
            entry_price=price,
            entry_date=time,
            entry_bar_idx=bar_idx,
        )

        logger.debug(
            f"OPEN LONG: {qty:.4f} {symbol} @ ${price:.2f} "
            f"(costo: ${cost:.2f})"
        )

    def _open_short(
        self, symbol: str, price: float, time: datetime, bar_idx: int
    ) -> None:
        """Abre una posicion corta."""
        if symbol in self._positions:
            return

        if len(self._positions) >= self._config.max_positions:
            return

        equity = self._cash + sum(
            pos.qty * price for pos in self._positions.values()
        )
        position_value = equity * self._config.position_size_pct
        qty = position_value / price

        if qty <= 0:
            return

        # En short, recibimos el dinero de la venta
        proceeds = qty * price - self._config.commission_per_trade
        self._cash += proceeds

        self._positions[symbol] = _OpenPosition(
            symbol=symbol,
            side="SELL",
            qty=qty,
            entry_price=price,
            entry_date=time,
            entry_bar_idx=bar_idx,
        )

        logger.debug(
            f"OPEN SHORT: {qty:.4f} {symbol} @ ${price:.2f}"
        )

    def _close_position(
        self, symbol: str, price: float, time: datetime, bar_idx: int
    ) -> None:
        """Cierra una posicion existente."""
        if symbol not in self._positions:
            return

        pos = self._positions[symbol]
        commission = self._config.commission_per_trade

        if pos.side == "BUY":
            # Cerrar long: vendemos
            proceeds = pos.qty * price - commission
            self._cash += proceeds
            pnl = (price - pos.entry_price) * pos.qty - (commission * 2)
            pnl_pct = (price - pos.entry_price) / pos.entry_price
        else:
            # Cerrar short: compramos de vuelta
            cost = pos.qty * price + commission
            self._cash -= cost
            pnl = (pos.entry_price - price) * pos.qty - (commission * 2)
            pnl_pct = (pos.entry_price - price) / pos.entry_price

        trade = BacktestTrade(
            symbol=symbol,
            side=pos.side,
            qty=pos.qty,
            entry_price=pos.entry_price,
            entry_date=pos.entry_date,
            exit_price=price,
            exit_date=time,
            commission=commission * 2,
            pnl=pnl,
            pnl_pct=pnl_pct,
            bars_held=bar_idx - pos.entry_bar_idx,
        )
        self._closed_trades.append(trade)

        logger.debug(
            f"CLOSE {'LONG' if pos.side == 'BUY' else 'SHORT'}: "
            f"{pos.qty:.4f} {symbol} @ ${price:.2f} | "
            f"PnL: ${pnl:.2f} ({pnl_pct:.2%})"
        )

        del self._positions[symbol]

    def _close_all_positions(
        self, data: dict[str, pd.DataFrame], timeline: list, bar_idx: int
    ) -> None:
        """Cierra todas las posiciones abiertas al precio de cierre."""
        current_time = timeline[bar_idx]
        symbols_to_close = list(self._positions.keys())

        for symbol in symbols_to_close:
            if symbol in data:
                bar = self._get_bar_at(data[symbol], current_time)
                if bar is not None:
                    self._close_position(
                        symbol, bar["close"], current_time, bar_idx
                    )

    # ── Calculo de equity ────────────────────────────────────────

    def _calculate_equity(
        self,
        data: dict[str, pd.DataFrame],
        current_time: datetime,
    ) -> float:
        """Calcula el valor total del portfolio (cash + posiciones)."""
        equity = self._cash

        for symbol, pos in self._positions.items():
            if symbol in data:
                bar = self._get_bar_at(data[symbol], current_time)
                if bar is not None:
                    equity += pos.qty * bar["close"]
                else:
                    equity += pos.qty * pos.entry_price

        return equity

    # ── Construccion de ventana de datos ─────────────────────────

    @staticmethod
    def _build_data_window(
        data: dict[str, pd.DataFrame],
        timeline: list,
        current_idx: int,
    ) -> dict[str, pd.DataFrame]:
        """
        Construye la ventana de datos hasta la barra actual
        para alimentar a la estrategia.
        """
        current_time = timeline[current_idx]
        window: dict[str, pd.DataFrame] = {}

        for symbol, df in data.items():
            # Filtrar barras hasta la barra actual inclusive
            mask = df.index <= current_time
            symbol_window = df.loc[mask]

            if not symbol_window.empty:
                window[symbol] = symbol_window

        return window

    @staticmethod
    def _get_bar_at(df: pd.DataFrame, timestamp: datetime) -> Optional[pd.Series]:
        """Obtiene la barra mas cercana a un timestamp dado."""
        if df.empty:
            return None

        # Intentar exacta primero
        if timestamp in df.index:
            return df.loc[timestamp]

        # Buscar la mas cercana anterior o igual
        mask = df.index <= timestamp
        filtered = df.loc[mask]
        if filtered.empty:
            return None

        return filtered.iloc[-1]

    # ── Estimacion de lookback ───────────────────────────────────

    @staticmethod
    def _estimate_lookback(params: dict[str, Any]) -> int:
        """
        Estima el lookback necesario basandose en los parametros
        de la estrategia. Busca el valor maximo entre periodos.
        """
        lookback = 1

        # Buscar parametros que parezcan periodos
        period_keywords = [
            "period", "length", "window", "slow", "fast",
            "long", "short", "signal",
        ]

        for key, value in params.items():
            if isinstance(value, (int, float)):
                key_lower = key.lower()
                if any(kw in key_lower for kw in period_keywords):
                    lookback = max(lookback, int(value))

        # Agregar margen de seguridad
        lookback = int(lookback * 1.5) + 5

        return lookback

    # ── Calculo de metricas ──────────────────────────────────────

    @staticmethod
    def _calculate_metrics(
        equity_curve: pd.Series,
        trades: list[BacktestTrade],
    ) -> dict[str, Any]:
        """
        Calcula metricas de rendimiento del backtest.
        """
        initial = equity_curve.iloc[0]
        final = equity_curve.iloc[-1]

        # Retornos
        total_return = (final - initial) / initial
        total_return_pct = total_return * 100

        # Retornos diarios
        daily_returns = equity_curve.pct_change().dropna()

        # Dias de trading
        if len(equity_curve) > 1:
            total_days = (equity_curve.index[-1] - equity_curve.index[0]).days
            trading_years = max(total_days / 365.25, 1 / 365.25)
        else:
            trading_years = 1 / 365.25

        # Retorno anualizado
        if total_return > -1:
            annualized_return = (1 + total_return) ** (1 / trading_years) - 1
        else:
            annualized_return = -1.0
        annualized_return_pct = annualized_return * 100

        # Volatilidad
        if len(daily_returns) > 1:
            daily_vol = daily_returns.std()
            annual_vol = daily_vol * np.sqrt(252)
        else:
            daily_vol = 0.0
            annual_vol = 0.0
        annual_vol_pct = annual_vol * 100

        # Sharpe ratio (risk-free rate = 0 para simplificar)
        if daily_vol > 0 and len(daily_returns) > 1:
            sharpe = (daily_returns.mean() / daily_vol) * np.sqrt(252)
        else:
            sharpe = 0.0

        # Max drawdown
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_dd = drawdown.min()
        max_dd_pct = max_dd * 100

        # Metricas de trades
        total_trades = len(trades)
        pnls = [t.pnl for t in trades]
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p <= 0]

        winning_trades = len(winners)
        losing_trades = len(losers)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        gross_profit = sum(winners) if winners else 0.0
        gross_loss = abs(sum(losers)) if losers else 0.0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )

        avg_trade_pnl = np.mean(pnls) if pnls else 0.0
        avg_winner = np.mean(winners) if winners else 0.0
        avg_loser = np.mean(losers) if losers else 0.0

        avg_bars_held = (
            np.mean([t.bars_held for t in trades]) if trades else 0.0
        )

        total_commissions = sum(t.commission for t in trades)

        # Mejor y peor trade
        best_trade = max(pnls) if pnls else 0.0
        worst_trade = min(pnls) if pnls else 0.0

        # Racha maxima de ganadores/perdedores
        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        for p in pnls:
            if p > 0:
                current_streak = current_streak + 1 if current_streak > 0 else 1
                max_win_streak = max(max_win_streak, current_streak)
            else:
                current_streak = current_streak - 1 if current_streak < 0 else -1
                max_loss_streak = max(max_loss_streak, abs(current_streak))

        return {
            # Capital
            "initial_capital": initial,
            "final_equity": final,
            "total_return_pct": round(total_return_pct, 2),
            "annualized_return_pct": round(annualized_return_pct, 2),

            # Riesgo
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "annual_volatility_pct": round(annual_vol_pct, 2),

            # Trades
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": round(win_rate, 1),
            "profit_factor": round(profit_factor, 3),

            # PnL
            "avg_trade_pnl": round(avg_trade_pnl, 2),
            "avg_winner": round(avg_winner, 2),
            "avg_loser": round(avg_loser, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "total_commissions": round(total_commissions, 2),

            # Duracion
            "avg_bars_held": round(avg_bars_held, 1),
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,

            # Meta
            "trading_days": len(equity_curve),
            "trading_years": round(trading_years, 2),
        }
