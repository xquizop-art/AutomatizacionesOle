"""
Orquestador principal del motor de trading.
Loop: obtener datos -> calcular senales -> gestionar riesgo -> ejecutar ordenes.

El TradingEngine es el corazon del sistema. Coordina todos los componentes:
    - StrategyRegistry: descubrimiento y gestion de estrategias.
    - BrokerInterface: ejecucion de ordenes.
    - MarketDataService: datos de mercado.
    - RiskManager: gestion de riesgo.
    - Database: persistencia de trades y metricas.

Cada estrategia corre como una tarea asyncio independiente con su propio
intervalo de ejecucion basado en su timeframe.

Uso:
    from backend.core.engine import TradingEngine

    engine = TradingEngine()
    await engine.initialize()
    await engine.start_strategy("sma_crossover")
    # ... el engine corre en background ...
    await engine.stop()
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from loguru import logger
from sqlalchemy.orm import Session

from backend.broker.alpaca_client import AlpacaClient
from backend.broker.broker_interface import (
    BrokerInterface,
    Order,
    OrderSide,
    OrderType,
    TimeInForce,
)
from backend.config import settings
from backend.core.risk_manager import RiskCheck, RiskManager
from backend.data.market_data import MarketDataService
from backend.models.database import SessionLocal
from backend.models.trade import Trade
from backend.models.strategy_state import StrategyRun
from backend.strategies.base_strategy import BaseStrategy, Signal, StrategyStatus
from backend.strategies.registry import StrategyRegistry


# ── Engine state ──────────────────────────────────────────────────


class EngineStatus(str, Enum):
    """Estado del motor de trading."""
    STOPPED = "stopped"
    INITIALIZING = "initializing"
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"


# ── Timeframe to seconds mapping ─────────────────────────────────

_TIMEFRAME_SECONDS: dict[str, int] = {
    "1Min": 60,
    "5Min": 300,
    "15Min": 900,
    "30Min": 1800,
    "1Hour": 3600,
    "4Hour": 14400,
    "1Day": 86400,
}

# Numero de barras historicas a solicitar por timeframe
_BARS_LIMIT: dict[str, int] = {
    "1Min": 200,
    "5Min": 200,
    "15Min": 200,
    "30Min": 150,
    "1Hour": 150,
    "4Hour": 100,
    "1Day": 100,
}


# ── Event types ──────────────────────────────────────────────────


class EngineEvent(str, Enum):
    """Tipos de eventos emitidos por el engine."""
    ENGINE_STARTED = "engine_started"
    ENGINE_STOPPED = "engine_stopped"
    STRATEGY_STARTED = "strategy_started"
    STRATEGY_STOPPED = "strategy_stopped"
    STRATEGY_ERROR = "strategy_error"
    SIGNAL_GENERATED = "signal_generated"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    RISK_REJECTED = "risk_rejected"
    CYCLE_COMPLETED = "cycle_completed"


# ── Callback type ────────────────────────────────────────────────

EventCallback = Callable[[EngineEvent, dict[str, Any]], Any]


# ── Trading Engine ───────────────────────────────────────────────


class TradingEngine:
    """
    Motor principal de trading en vivo.

    Orquesta el ciclo completo:
        1. Obtener datos de mercado para los simbolos de cada estrategia.
        2. Ejecutar la estrategia para generar senales (BUY/SELL/HOLD).
        3. Evaluar riesgo de cada senal con el RiskManager.
        4. Enviar ordenes al broker para las senales aprobadas.
        5. Registrar trades en base de datos.
        6. Notificar via callbacks (para WebSocket, etc.).

    Cada estrategia activa corre en su propia tarea asyncio,
    con un intervalo de ejecucion basado en su timeframe.
    """

    def __init__(
        self,
        broker: Optional[BrokerInterface] = None,
        market_data: Optional[MarketDataService] = None,
        registry: Optional[StrategyRegistry] = None,
        risk_manager: Optional[RiskManager] = None,
    ) -> None:
        """
        Inicializa el engine con los componentes necesarios.

        Args:
            broker: Instancia del broker. Default: AlpacaClient.
            market_data: Servicio de datos de mercado. Default: crea uno nuevo.
            registry: Registro de estrategias. Default: crea uno nuevo.
            risk_manager: Gestor de riesgo. Default: crea uno nuevo.
        """
        self._broker = broker or AlpacaClient()
        self._market_data = market_data or MarketDataService(client=self._broker)
        self._registry = registry or StrategyRegistry()
        self._risk_manager = risk_manager or RiskManager()

        # ── Estado del engine ────────────────────────────────
        self._status: EngineStatus = EngineStatus.STOPPED
        self._started_at: Optional[datetime] = None

        # ── Tareas asyncio activas por estrategia ────────────
        self._strategy_tasks: dict[str, asyncio.Task] = {}

        # ── Callbacks para eventos ───────────────────────────
        self._event_callbacks: list[EventCallback] = []

        # ── Contadores ───────────────────────────────────────
        self._total_orders_submitted: int = 0
        self._total_cycles: int = 0

        logger.info("TradingEngine creado")

    # ══════════════════════════════════════════════════════════════
    # ── Inicializacion ───────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        """
        Inicializa el engine: descubre estrategias y verifica conexion
        con el broker.

        Debe llamarse antes de start_strategy().
        """
        self._status = EngineStatus.INITIALIZING
        logger.info("═══ Inicializando TradingEngine ═══")

        # 1. Descubrir estrategias
        discovered = self._registry.discover()
        logger.info(f"Estrategias descubiertas: {discovered}")

        # 2. Verificar conexion con broker
        try:
            account = await self._broker.get_account()
            market_open = await self._broker.is_market_open()
            logger.info(
                f"Broker conectado | Account: {account.account_id} | "
                f"Equity: ${account.equity:,.2f} | Cash: ${account.cash:,.2f} | "
                f"Mercado abierto: {market_open}"
            )
        except Exception as e:
            logger.error(f"Error conectando al broker: {e}")
            self._status = EngineStatus.ERROR
            raise RuntimeError(f"No se pudo conectar al broker: {e}") from e

        self._status = EngineStatus.RUNNING
        self._started_at = datetime.now()
        logger.info("═══ TradingEngine inicializado y listo ═══")

        await self._emit_event(EngineEvent.ENGINE_STARTED, {
            "account_id": account.account_id,
            "equity": account.equity,
            "strategies_available": discovered,
            "market_open": market_open,
        })

    # ══════════════════════════════════════════════════════════════
    # ── Gestion de estrategias ───────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def start_strategy(self, name: str) -> dict[str, Any]:
        """
        Arranca una estrategia y crea su tarea asyncio.

        Args:
            name: Nombre de la estrategia registrada.

        Returns:
            Diccionario con info de la estrategia arrancada.

        Raises:
            RuntimeError: Si el engine no esta corriendo.
            KeyError: Si la estrategia no esta registrada.
            ValueError: Si la estrategia ya esta corriendo.
        """
        if self._status != EngineStatus.RUNNING:
            raise RuntimeError(
                f"Engine no esta corriendo (status={self._status.value}). "
                "Llama a initialize() primero."
            )

        if name in self._strategy_tasks and not self._strategy_tasks[name].done():
            raise ValueError(f"Estrategia '{name}' ya esta corriendo")

        # Obtener instancia de la estrategia
        strategy = self._registry.get_strategy(name)
        strategy.start()

        # Registrar el run en base de datos
        run_id = self._record_strategy_start(strategy)

        # Crear tarea asyncio para el loop de la estrategia
        task = asyncio.create_task(
            self._strategy_loop(strategy, run_id),
            name=f"strategy_{name}",
        )
        self._strategy_tasks[name] = task

        logger.info(
            f"Estrategia '{name}' arrancada | "
            f"symbols={strategy.symbols} | timeframe={strategy.timeframe} | "
            f"run_id={run_id}"
        )

        await self._emit_event(EngineEvent.STRATEGY_STARTED, {
            "strategy": name,
            "symbols": strategy.symbols,
            "timeframe": strategy.timeframe,
            "run_id": run_id,
        })

        return {
            "name": name,
            "status": "running",
            "symbols": strategy.symbols,
            "timeframe": strategy.timeframe,
            "run_id": run_id,
        }

    async def stop_strategy(self, name: str) -> dict[str, Any]:
        """
        Detiene una estrategia y cancela su tarea asyncio.

        Args:
            name: Nombre de la estrategia a detener.

        Returns:
            Diccionario con info del estado final.
        """
        if name not in self._strategy_tasks:
            raise ValueError(f"Estrategia '{name}' no tiene tarea activa")

        task = self._strategy_tasks[name]

        # Cancelar la tarea asyncio
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Detener la estrategia
        strategy = self._registry.get_strategy(name)
        if strategy.is_running:
            strategy.stop()

        # Actualizar en base de datos
        self._record_strategy_stop(name)

        del self._strategy_tasks[name]

        logger.info(f"Estrategia '{name}' detenida")

        await self._emit_event(EngineEvent.STRATEGY_STOPPED, {
            "strategy": name,
        })

        return {
            "name": name,
            "status": "stopped",
        }

    async def stop(self) -> None:
        """
        Detiene el engine y todas las estrategias activas.
        Shutdown graceful: espera a que los ciclos actuales terminen.
        """
        if self._status == EngineStatus.STOPPED:
            logger.warning("Engine ya esta detenido")
            return

        logger.info("═══ Deteniendo TradingEngine ═══")
        self._status = EngineStatus.SHUTTING_DOWN

        # Detener todas las estrategias
        strategy_names = list(self._strategy_tasks.keys())
        for name in strategy_names:
            try:
                await self.stop_strategy(name)
            except Exception as e:
                logger.error(f"Error deteniendo estrategia '{name}': {e}")

        self._status = EngineStatus.STOPPED
        logger.info("═══ TradingEngine detenido ═══")

        await self._emit_event(EngineEvent.ENGINE_STOPPED, {
            "total_cycles": self._total_cycles,
            "total_orders": self._total_orders_submitted,
        })

    # ══════════════════════════════════════════════════════════════
    # ── Loop principal por estrategia ────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def _strategy_loop(
        self,
        strategy: BaseStrategy,
        run_id: int,
    ) -> None:
        """
        Loop asyncio principal para una estrategia individual.

        Ejecuta el ciclo: datos -> senales -> riesgo -> ordenes
        en intervalos determinados por el timeframe de la estrategia.

        Args:
            strategy: Instancia de la estrategia.
            run_id: ID del StrategyRun en base de datos.
        """
        name = strategy.name
        timeframe = strategy.timeframe
        interval = _TIMEFRAME_SECONDS.get(timeframe, 60)
        bars_limit = _BARS_LIMIT.get(timeframe, 100)

        logger.info(
            f"[{name}] Loop iniciado | intervalo={interval}s | "
            f"timeframe={timeframe} | bars_limit={bars_limit}"
        )

        consecutive_errors = 0
        max_consecutive_errors = 5

        try:
            while strategy.is_running and self._status == EngineStatus.RUNNING:
                cycle_start = datetime.now()

                try:
                    await self._execute_cycle(
                        strategy=strategy,
                        run_id=run_id,
                        bars_limit=bars_limit,
                    )
                    consecutive_errors = 0
                    self._total_cycles += 1

                except asyncio.CancelledError:
                    logger.info(f"[{name}] Loop cancelado")
                    raise

                except Exception as e:
                    consecutive_errors += 1
                    logger.error(
                        f"[{name}] Error en ciclo ({consecutive_errors}/"
                        f"{max_consecutive_errors}): {e}"
                    )

                    if consecutive_errors >= max_consecutive_errors:
                        logger.critical(
                            f"[{name}] Demasiados errores consecutivos. "
                            "Deteniendo estrategia."
                        )
                        strategy.set_error(
                            f"Detenida por {max_consecutive_errors} errores "
                            f"consecutivos. Ultimo: {e}"
                        )
                        self._record_strategy_error(name, str(e))
                        await self._emit_event(EngineEvent.STRATEGY_ERROR, {
                            "strategy": name,
                            "error": str(e),
                            "consecutive_errors": consecutive_errors,
                        })
                        break

                    # Espera progresiva antes de reintentar
                    error_wait = min(interval, 30) * consecutive_errors
                    logger.info(
                        f"[{name}] Esperando {error_wait}s antes de reintentar"
                    )
                    await asyncio.sleep(error_wait)
                    continue

                # ── Esperar hasta el proximo ciclo ────────────
                elapsed = (datetime.now() - cycle_start).total_seconds()
                sleep_time = max(interval - elapsed, 1.0)

                logger.debug(
                    f"[{name}] Ciclo completado en {elapsed:.1f}s. "
                    f"Proximo en {sleep_time:.1f}s"
                )
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info(f"[{name}] Tarea cancelada — limpiando")

        finally:
            logger.info(f"[{name}] Loop finalizado")

    # ══════════════════════════════════════════════════════════════
    # ── Ciclo de ejecucion ───────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def _execute_cycle(
        self,
        strategy: BaseStrategy,
        run_id: int,
        bars_limit: int,
    ) -> None:
        """
        Ejecuta un ciclo completo del motor de trading para una estrategia.

        Pasos:
            1. Verificar si el mercado esta abierto.
            2. Obtener datos de mercado para los simbolos de la estrategia.
            3. Ejecutar la estrategia para generar senales.
            4. Para cada senal activa (BUY/SELL):
                a. Evaluar riesgo.
                b. Ejecutar orden si es aprobada.
                c. Registrar trade en DB.
            5. Emitir evento de ciclo completado.

        Args:
            strategy: Instancia de la estrategia.
            run_id: ID del StrategyRun en base de datos.
            bars_limit: Numero de barras historicas a solicitar.
        """
        name = strategy.name

        # ── 1. Verificar mercado ─────────────────────────────
        # Estrategias con skip_market_check=True (e.g. crypto) no dependen
        # del horario del mercado de acciones de EEUU.
        if not strategy.skip_market_check:
            market_open = await self._market_data.is_market_open()
            if not market_open:
                logger.debug(f"[{name}] Mercado cerrado — saltando ciclo")
                return

        # ── 2. Obtener datos ─────────────────────────────────
        data = await self._market_data.get_bars_for_symbols(
            symbols=strategy.symbols,
            timeframe=strategy.timeframe,
            limit=bars_limit,
        )

        if not data:
            logger.warning(f"[{name}] Sin datos de mercado — saltando ciclo")
            return

        # ── 3. Generar senales ───────────────────────────────
        signals = strategy.run(data)

        # Filtrar solo senales activas (no HOLD)
        active_signals = {
            sym: sig for sym, sig in signals.items()
            if sig != Signal.HOLD
        }

        if not active_signals:
            logger.debug(f"[{name}] Sin senales activas en este ciclo")
            await self._emit_event(EngineEvent.CYCLE_COMPLETED, {
                "strategy": name,
                "signals": {s: sig.value for s, sig in signals.items()},
                "orders_submitted": 0,
            })
            return

        await self._emit_event(EngineEvent.SIGNAL_GENERATED, {
            "strategy": name,
            "signals": {s: sig.value for s, sig in active_signals.items()},
        })

        # ── 4. Procesar senales ──────────────────────────────
        orders_submitted = 0

        for symbol, signal in active_signals.items():
            try:
                order = await self._process_signal(
                    strategy=strategy,
                    symbol=symbol,
                    signal=signal,
                    run_id=run_id,
                )
                if order is not None:
                    orders_submitted += 1
            except Exception as e:
                logger.error(
                    f"[{name}] Error procesando senal {signal.value} "
                    f"para {symbol}: {e}"
                )

        # ── 5. Actualizar metricas del run en DB ─────────────
        self._update_strategy_run(name, signals)

        await self._emit_event(EngineEvent.CYCLE_COMPLETED, {
            "strategy": name,
            "signals": {s: sig.value for s, sig in signals.items()},
            "orders_submitted": orders_submitted,
        })

    # ══════════════════════════════════════════════════════════════
    # ── Procesamiento de senales ─────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def _process_signal(
        self,
        strategy: BaseStrategy,
        symbol: str,
        signal: Signal,
        run_id: int,
    ) -> Optional[Order]:
        """
        Procesa una senal individual: evalua riesgo y ejecuta orden.

        Args:
            strategy: Estrategia que genero la senal.
            symbol: Ticker del activo.
            signal: Senal generada (BUY o SELL).
            run_id: ID del StrategyRun.

        Returns:
            Orden ejecutada, o None si fue rechazada o fallo.
        """
        name = strategy.name

        # Determinar lado de la orden
        if signal == Signal.BUY:
            side = OrderSide.BUY
        elif signal == Signal.SELL:
            side = OrderSide.SELL
        else:
            return None

        # Obtener precio actual
        price = await self._market_data.get_latest_price(symbol)
        if price is None or price <= 0:
            logger.warning(f"[{name}] No se pudo obtener precio para {symbol}")
            return None

        # Calcular cantidad
        if side == OrderSide.BUY:
            qty = await self._risk_manager.calculate_position_size(
                symbol=symbol,
                price=price,
                broker=self._broker,
            )
            if qty <= 0:
                logger.info(
                    f"[{name}] Position size = 0 para {symbol} — no se opera"
                )
                return None
        else:
            # Para SELL, cerrar la posicion existente
            position = await self._broker.get_position(symbol)
            if position is None:
                logger.debug(
                    f"[{name}] No hay posicion abierta en {symbol} — "
                    "ignorando senal SELL"
                )
                return None
            qty = abs(position.qty)

        # ── Evaluar riesgo ───────────────────────────────────
        risk_check = await self._risk_manager.evaluate_order(
            symbol=symbol,
            side=side.value,
            qty=qty,
            price=price,
            strategy_name=name,
            broker=self._broker,
        )

        if not risk_check.approved:
            logger.warning(
                f"[{name}] Orden rechazada por riesgo: "
                f"{side.value} {qty:.4f} {symbol} — {risk_check.reason}"
            )
            self._record_trade_to_db(
                strategy_name=name,
                symbol=symbol,
                side=side.value,
                qty=qty,
                order_type="market",
                signal=signal.value,
                status="rejected",
                notes=f"Risk rejected: {risk_check.reason}",
            )
            await self._emit_event(EngineEvent.RISK_REJECTED, {
                "strategy": name,
                "symbol": symbol,
                "side": side.value,
                "qty": qty,
                "reason": risk_check.reason,
            })
            return None

        # ── Ejecutar orden ───────────────────────────────────
        # Verificar si la estrategia provee SL/TP (bracket order)
        bracket_params = getattr(strategy, '_bracket_params', None)
        tp_price = bracket_params.get('take_profit') if bracket_params else None
        sl_price = bracket_params.get('stop_loss') if bracket_params else None

        # Crypto usa GTC; stocks usan DAY
        is_crypto = "/" in symbol
        tif = TimeInForce.GTC if is_crypto else TimeInForce.DAY

        try:
            order = await self._broker.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                order_type=OrderType.MARKET,
                time_in_force=tif,
                take_profit_price=tp_price,
                stop_loss_price=sl_price,
            )

            # Limpiar bracket params despues de usar
            if bracket_params:
                strategy._bracket_params = None
                logger.info(
                    f"[{name}] Bracket order: TP={tp_price} | SL={sl_price}"
                )

            self._total_orders_submitted += 1
            self._risk_manager.record_trade()

            logger.info(
                f"[{name}] Orden ejecutada: {side.value} {qty:.4f} {symbol} | "
                f"order_id={order.order_id} | status={order.status.value}"
            )

            # Registrar en base de datos
            self._record_trade_to_db(
                strategy_name=name,
                symbol=symbol,
                side=side.value,
                qty=qty,
                order_type="market",
                signal=signal.value,
                status=order.status.value,
                alpaca_order_id=order.order_id,
                filled_avg_price=order.filled_avg_price,
                filled_qty=order.filled_qty,
                submitted_at=datetime.now(),
                filled_at=order.filled_at,
            )

            # Notificar a la estrategia
            strategy.on_trade_executed({
                "symbol": symbol,
                "side": side.value,
                "qty": qty,
                "price": order.filled_avg_price or price,
                "order_id": order.order_id,
                "status": order.status.value,
            })

            await self._emit_event(EngineEvent.ORDER_SUBMITTED, {
                "strategy": name,
                "symbol": symbol,
                "side": side.value,
                "qty": qty,
                "price": order.filled_avg_price or price,
                "order_id": order.order_id,
                "status": order.status.value,
            })

            return order

        except Exception as e:
            logger.error(
                f"[{name}] Error enviando orden: "
                f"{side.value} {qty:.4f} {symbol} — {e}"
            )

            self._record_trade_to_db(
                strategy_name=name,
                symbol=symbol,
                side=side.value,
                qty=qty,
                order_type="market",
                signal=signal.value,
                status="error",
                notes=f"Broker error: {e}",
            )
            return None

    # ══════════════════════════════════════════════════════════════
    # ── Persistencia en base de datos ────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def _record_trade_to_db(
        self,
        strategy_name: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "market",
        signal: Optional[str] = None,
        status: str = "pending",
        alpaca_order_id: Optional[str] = None,
        filled_avg_price: Optional[float] = None,
        filled_qty: Optional[float] = None,
        submitted_at: Optional[datetime] = None,
        filled_at: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Optional[int]:
        """Registra un trade en la base de datos."""
        try:
            db: Session = SessionLocal()
            trade = Trade(
                strategy_name=strategy_name,
                symbol=symbol,
                side=side,
                qty=qty,
                order_type=order_type,
                signal=signal,
                status=status,
                alpaca_order_id=alpaca_order_id,
                filled_avg_price=filled_avg_price,
                filled_qty=filled_qty,
                submitted_at=submitted_at,
                filled_at=filled_at,
                notes=notes,
            )
            db.add(trade)
            db.commit()
            trade_id = trade.id
            db.close()
            logger.debug(f"Trade registrado en DB: id={trade_id}")
            return trade_id
        except Exception as e:
            logger.error(f"Error registrando trade en DB: {e}")
            return None

    def _record_strategy_start(self, strategy: BaseStrategy) -> int:
        """Crea un registro de StrategyRun al iniciar una estrategia."""
        try:
            db: Session = SessionLocal()
            run = StrategyRun(
                strategy_name=strategy.name,
                status="running",
                symbols=",".join(strategy.symbols),
                timeframe=strategy.timeframe,
                parameters=json.dumps(strategy.get_parameters()),
                started_at=datetime.now(),
            )
            db.add(run)
            db.commit()
            run_id = run.id
            db.close()
            logger.debug(f"StrategyRun registrado: id={run_id}")
            return run_id
        except Exception as e:
            logger.error(f"Error registrando StrategyRun: {e}")
            return -1

    def _record_strategy_stop(self, name: str) -> None:
        """Actualiza el StrategyRun al detener una estrategia."""
        try:
            db: Session = SessionLocal()
            run = (
                db.query(StrategyRun)
                .filter(
                    StrategyRun.strategy_name == name,
                    StrategyRun.status == "running",
                )
                .order_by(StrategyRun.id.desc())
                .first()
            )
            if run:
                run.status = "stopped"
                run.stopped_at = datetime.now()
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Error actualizando StrategyRun stop: {e}")

    def _record_strategy_error(self, name: str, error_message: str) -> None:
        """Registra un error en el StrategyRun."""
        try:
            db: Session = SessionLocal()
            run = (
                db.query(StrategyRun)
                .filter(
                    StrategyRun.strategy_name == name,
                    StrategyRun.status == "running",
                )
                .order_by(StrategyRun.id.desc())
                .first()
            )
            if run:
                run.status = "error"
                run.error_message = error_message
                run.stopped_at = datetime.now()
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Error registrando error en StrategyRun: {e}")

    def _update_strategy_run(
        self,
        name: str,
        signals: dict[str, Signal],
    ) -> None:
        """Actualiza las senales y metricas del StrategyRun actual."""
        try:
            db: Session = SessionLocal()
            run = (
                db.query(StrategyRun)
                .filter(
                    StrategyRun.strategy_name == name,
                    StrategyRun.status == "running",
                )
                .order_by(StrategyRun.id.desc())
                .first()
            )
            if run:
                run.last_signal = json.dumps(
                    {s: sig.value for s, sig in signals.items()}
                )
                # Contar trades asociados a este run
                total = (
                    db.query(Trade)
                    .filter(
                        Trade.strategy_name == name,
                        Trade.created_at >= run.started_at,
                    )
                    .count()
                )
                run.total_trades = total
                db.commit()
            db.close()
        except Exception as e:
            logger.error(f"Error actualizando StrategyRun metricas: {e}")

    # ══════════════════════════════════════════════════════════════
    # ── Eventos / callbacks ──────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def on_event(self, callback: EventCallback) -> None:
        """
        Registra un callback para eventos del engine.

        El callback recibe (event_type, data_dict). Ideal para
        reenviar eventos via WebSocket al frontend.

        Args:
            callback: Funcion o coroutine que recibe (EngineEvent, dict).
        """
        self._event_callbacks.append(callback)

    async def _emit_event(
        self,
        event: EngineEvent,
        data: dict[str, Any],
    ) -> None:
        """Emite un evento a todos los callbacks registrados."""
        data["event"] = event.value
        data["timestamp"] = datetime.now().isoformat()

        for callback in self._event_callbacks:
            try:
                result = callback(event, data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Error en callback de evento {event.value}: {e}")

    # ══════════════════════════════════════════════════════════════
    # ── Consultas de estado ──────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    @property
    def status(self) -> EngineStatus:
        """Estado actual del engine."""
        return self._status

    @property
    def is_running(self) -> bool:
        """True si el engine esta corriendo."""
        return self._status == EngineStatus.RUNNING

    @property
    def broker(self) -> BrokerInterface:
        """Acceso al broker."""
        return self._broker

    @property
    def market_data(self) -> MarketDataService:
        """Acceso al servicio de datos de mercado."""
        return self._market_data

    @property
    def registry(self) -> StrategyRegistry:
        """Acceso al registro de estrategias."""
        return self._registry

    @property
    def risk_manager(self) -> RiskManager:
        """Acceso al gestor de riesgo."""
        return self._risk_manager

    def get_active_strategies(self) -> list[str]:
        """Retorna nombres de estrategias con tareas activas."""
        return [
            name for name, task in self._strategy_tasks.items()
            if not task.done()
        ]

    def get_status(self) -> dict[str, Any]:
        """Retorna un resumen completo del estado del engine."""
        active = self.get_active_strategies()

        return {
            "engine_status": self._status.value,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "active_strategies": active,
            "total_strategies_available": len(self._registry),
            "total_cycles": self._total_cycles,
            "total_orders_submitted": self._total_orders_submitted,
            "risk_manager": self._risk_manager.get_status(),
        }

    async def get_account_summary(self) -> dict[str, Any]:
        """Obtiene resumen de la cuenta del broker."""
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            return {
                "account_id": account.account_id,
                "equity": account.equity,
                "cash": account.cash,
                "buying_power": account.buying_power,
                "portfolio_value": account.portfolio_value,
                "status": account.status,
                "open_positions": len(positions),
                "positions": [
                    {
                        "symbol": p.symbol,
                        "qty": p.qty,
                        "side": p.side,
                        "market_value": p.market_value,
                        "avg_entry_price": p.avg_entry_price,
                        "current_price": p.current_price,
                        "unrealized_pl": p.unrealized_pl,
                        "unrealized_plpc": p.unrealized_plpc,
                    }
                    for p in positions
                ],
            }
        except Exception as e:
            logger.error(f"Error obteniendo resumen de cuenta: {e}")
            return {"error": str(e)}

    def __repr__(self) -> str:
        active = len(self.get_active_strategies())
        return (
            f"<TradingEngine "
            f"status={self._status.value} "
            f"strategies={active}/{len(self._registry)} "
            f"cycles={self._total_cycles}>"
        )
