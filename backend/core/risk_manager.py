"""
Gestion de riesgo.
Limites de perdida diaria, tamanio maximo de posicion, max operaciones por dia.

El RiskManager actua como guardian antes de cada operacion: el engine le
consulta si una orden es segura antes de enviarla al broker.

Uso:
    from backend.core.risk_manager import RiskManager

    rm = RiskManager()
    check = await rm.evaluate_order(
        symbol="AAPL",
        side="buy",
        qty=10,
        price=150.0,
        strategy_name="sma_crossover",
        broker=broker,
    )
    if check.approved:
        # enviar orden al broker
    else:
        print(check.reason)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from loguru import logger

from backend.broker.broker_interface import (
    AccountInfo,
    BrokerInterface,
    OrderSide,
    Position,
)
from backend.config import settings


# ── Risk check result ─────────────────────────────────────────────


@dataclass
class RiskCheck:
    """Resultado de la evaluacion de riesgo para una orden."""
    approved: bool
    reason: str = ""
    adjusted_qty: Optional[float] = None  # Qty ajustada si se redujo
    details: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def ok(details: Optional[dict[str, Any]] = None) -> RiskCheck:
        """Crea un RiskCheck aprobado."""
        return RiskCheck(approved=True, details=details or {})

    @staticmethod
    def reject(reason: str, details: Optional[dict[str, Any]] = None) -> RiskCheck:
        """Crea un RiskCheck rechazado."""
        return RiskCheck(approved=False, reason=reason, details=details or {})


# ── Risk limits configuration ────────────────────────────────────


@dataclass
class RiskLimits:
    """
    Configuracion de limites de riesgo.
    Valores por defecto se cargan desde settings, pero pueden sobreescribirse.
    """
    max_daily_loss_pct: float = 0.0       # % del equity (ej: 2.0 = 2%)
    max_position_size_pct: float = 0.0    # % del equity por posicion
    max_trades_per_day: int = 0           # Max operaciones por dia
    max_open_positions: int = 20          # Max posiciones simultaneas
    min_buying_power_pct: float = 10.0    # Min % buying power restante

    @classmethod
    def from_settings(cls) -> RiskLimits:
        """Crea limites desde la configuracion global."""
        return cls(
            max_daily_loss_pct=settings.MAX_DAILY_LOSS_PCT,
            max_position_size_pct=settings.MAX_POSITION_SIZE_PCT,
            max_trades_per_day=settings.MAX_TRADES_PER_DAY,
        )


# ── Risk Manager ─────────────────────────────────────────────────


class RiskManager:
    """
    Gestor de riesgo del motor de trading.

    Evalua cada orden propuesta contra multiples reglas de riesgo:
        1. Perdida diaria maxima (% del equity al inicio del dia).
        2. Tamanio maximo de posicion (% del equity actual).
        3. Numero maximo de operaciones por dia.
        4. Limite de posiciones simultaneas abiertas.
        5. Buying power minimo.

    Tambien calcula el tamanio optimo de posicion basado en el equity
    y los limites configurados.

    Counters internos (daily_pnl, trades_today) se resetean al inicio
    de cada dia de trading.
    """

    def __init__(self, limits: Optional[RiskLimits] = None) -> None:
        self._limits = limits or RiskLimits.from_settings()

        # ── Contadores diarios ───────────────────────────────
        self._current_date: Optional[date] = None
        self._daily_pnl: float = 0.0
        self._trades_today: int = 0
        self._equity_start_of_day: float = 0.0

        # ── Estado en cache ──────────────────────────────────
        self._last_account: Optional[AccountInfo] = None
        self._last_positions: list[Position] = []

        logger.info(
            f"RiskManager inicializado | "
            f"max_daily_loss={self._limits.max_daily_loss_pct}% | "
            f"max_position_size={self._limits.max_position_size_pct}% | "
            f"max_trades/dia={self._limits.max_trades_per_day}"
        )

    # ══════════════════════════════════════════════════════════════
    # ── Evaluacion de ordenes ────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def evaluate_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        strategy_name: str,
        broker: BrokerInterface,
    ) -> RiskCheck:
        """
        Evalua si una orden debe ser aprobada o rechazada.

        Ejecuta una cadena de checks de riesgo en orden. Si alguno falla,
        la orden es rechazada inmediatamente.

        Args:
            symbol: Ticker del activo.
            side: "buy" o "sell".
            qty: Cantidad de acciones/unidades.
            price: Precio estimado de ejecucion.
            strategy_name: Nombre de la estrategia que genero la senal.
            broker: Instancia del broker para consultar cuenta/posiciones.

        Returns:
            RiskCheck con el resultado de la evaluacion.
        """
        order_value = qty * price
        logger.debug(
            f"[RiskManager] Evaluando: {side.upper()} {qty:.4f} {symbol} "
            f"@ ${price:.2f} (valor=${order_value:.2f}) | estrategia={strategy_name}"
        )

        # Refrescar datos de cuenta y posiciones
        try:
            await self._refresh_state(broker)
        except Exception as e:
            logger.error(f"[RiskManager] Error refrescando estado: {e}")
            return RiskCheck.reject(
                f"No se pudo obtener estado de la cuenta: {e}"
            )

        # Resetear contadores si cambio el dia
        self._check_day_reset()

        # ── Cadena de checks ─────────────────────────────────
        checks = [
            self._check_daily_loss,
            self._check_trades_limit,
            self._check_position_size,
            self._check_open_positions,
            self._check_buying_power,
        ]

        for check_fn in checks:
            result = check_fn(
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_value=order_value,
            )
            if not result.approved:
                logger.warning(
                    f"[RiskManager] RECHAZADO: {side.upper()} {qty:.4f} {symbol} | "
                    f"Razon: {result.reason}"
                )
                return result

        logger.info(
            f"[RiskManager] APROBADO: {side.upper()} {qty:.4f} {symbol} "
            f"@ ${price:.2f}"
        )
        return RiskCheck.ok(details={
            "equity": self._last_account.equity if self._last_account else 0,
            "daily_pnl": self._daily_pnl,
            "trades_today": self._trades_today,
            "open_positions": len(self._last_positions),
        })

    # ══════════════════════════════════════════════════════════════
    # ── Checks individuales ──────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    def _check_daily_loss(self, **kwargs) -> RiskCheck:
        """Verifica que no se haya excedido la perdida diaria maxima."""
        if self._limits.max_daily_loss_pct <= 0:
            return RiskCheck.ok()

        if self._equity_start_of_day <= 0:
            return RiskCheck.ok()  # Sin referencia, no podemos evaluar

        max_loss = self._equity_start_of_day * (self._limits.max_daily_loss_pct / 100)
        current_loss = abs(min(self._daily_pnl, 0))

        if current_loss >= max_loss:
            return RiskCheck.reject(
                f"Perdida diaria maxima alcanzada: "
                f"${current_loss:.2f} >= ${max_loss:.2f} "
                f"({self._limits.max_daily_loss_pct}% del equity)",
                details={
                    "daily_pnl": self._daily_pnl,
                    "max_daily_loss": max_loss,
                    "equity_start_of_day": self._equity_start_of_day,
                },
            )

        return RiskCheck.ok()

    def _check_trades_limit(self, **kwargs) -> RiskCheck:
        """Verifica que no se haya excedido el numero maximo de trades diarios."""
        if self._limits.max_trades_per_day <= 0:
            return RiskCheck.ok()

        if self._trades_today >= self._limits.max_trades_per_day:
            return RiskCheck.reject(
                f"Limite de operaciones diarias alcanzado: "
                f"{self._trades_today} >= {self._limits.max_trades_per_day}",
                details={"trades_today": self._trades_today},
            )

        return RiskCheck.ok()

    def _check_position_size(
        self,
        symbol: str,
        side: str,
        order_value: float,
        **kwargs,
    ) -> RiskCheck:
        """Verifica que el tamanio de la posicion no exceda el limite."""
        if self._limits.max_position_size_pct <= 0:
            return RiskCheck.ok()

        if not self._last_account:
            return RiskCheck.ok()

        # Solo aplica a compras (las ventas cierran posiciones)
        if side.lower() == "sell":
            return RiskCheck.ok()

        equity = self._last_account.equity
        max_value = equity * (self._limits.max_position_size_pct / 100)

        # Sumar valor de posicion existente si la hay
        existing_value = 0.0
        for pos in self._last_positions:
            if pos.symbol == symbol:
                existing_value = pos.market_value
                break

        total_exposure = existing_value + order_value

        if total_exposure > max_value:
            return RiskCheck.reject(
                f"Posicion excede el limite: "
                f"${total_exposure:.2f} > ${max_value:.2f} "
                f"({self._limits.max_position_size_pct}% del equity)",
                details={
                    "order_value": order_value,
                    "existing_value": existing_value,
                    "total_exposure": total_exposure,
                    "max_position_value": max_value,
                    "equity": equity,
                },
            )

        return RiskCheck.ok()

    def _check_open_positions(self, side: str, **kwargs) -> RiskCheck:
        """Verifica que no se exceda el numero maximo de posiciones abiertas."""
        if self._limits.max_open_positions <= 0:
            return RiskCheck.ok()

        # Solo aplica a compras (nuevas posiciones)
        if side.lower() == "sell":
            return RiskCheck.ok()

        if len(self._last_positions) >= self._limits.max_open_positions:
            return RiskCheck.reject(
                f"Limite de posiciones abiertas alcanzado: "
                f"{len(self._last_positions)} >= {self._limits.max_open_positions}",
                details={"open_positions": len(self._last_positions)},
            )

        return RiskCheck.ok()

    def _check_buying_power(
        self,
        side: str,
        order_value: float,
        **kwargs,
    ) -> RiskCheck:
        """Verifica que hay suficiente buying power para la orden."""
        if not self._last_account:
            return RiskCheck.ok()

        # Solo aplica a compras
        if side.lower() == "sell":
            return RiskCheck.ok()

        buying_power = self._last_account.buying_power

        if order_value > buying_power:
            return RiskCheck.reject(
                f"Buying power insuficiente: "
                f"orden=${order_value:.2f} > disponible=${buying_power:.2f}",
                details={
                    "order_value": order_value,
                    "buying_power": buying_power,
                },
            )

        # Verificar que queda un minimo de buying power despues
        remaining_pct = ((buying_power - order_value) / self._last_account.equity) * 100
        if remaining_pct < self._limits.min_buying_power_pct:
            logger.warning(
                f"[RiskManager] Buying power restante bajo: {remaining_pct:.1f}% "
                f"(minimo recomendado: {self._limits.min_buying_power_pct}%)"
            )
            # Advertencia pero no rechazo
        return RiskCheck.ok()

    # ══════════════════════════════════════════════════════════════
    # ── Position sizing ──────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def calculate_position_size(
        self,
        symbol: str,
        price: float,
        broker: BrokerInterface,
        target_pct: Optional[float] = None,
    ) -> float:
        """
        Calcula el tamanio optimo de posicion en numero de acciones.

        Toma el menor entre:
            1. target_pct del equity (o max_position_size_pct si no se especifica).
            2. Lo que permite el buying power disponible.
            3. Qty que no viole ningun limite de riesgo.

        Args:
            symbol: Ticker del activo.
            price: Precio actual del activo.
            broker: Instancia del broker.
            target_pct: % del equity a asignar. Default: max_position_size_pct.

        Returns:
            Cantidad de acciones (puede ser fraccional). 0.0 si no es posible.
        """
        if price <= 0:
            return 0.0

        try:
            await self._refresh_state(broker)
        except Exception as e:
            logger.error(f"[RiskManager] Error calculando posicion: {e}")
            return 0.0

        if not self._last_account:
            return 0.0

        equity = self._last_account.equity
        buying_power = self._last_account.buying_power
        pct = target_pct if target_pct is not None else self._limits.max_position_size_pct

        # Valor maximo basado en % del equity
        max_by_equity = equity * (pct / 100)

        # Valor maximo basado en buying power (dejar margen)
        max_by_bp = buying_power * 0.95  # 5% de margen

        # Considerar posicion existente
        existing_value = 0.0
        for pos in self._last_positions:
            if pos.symbol == symbol:
                existing_value = pos.market_value
                break

        available_value = min(max_by_equity - existing_value, max_by_bp)
        available_value = max(available_value, 0.0)

        qty = available_value / price

        if qty < 0.01:
            return 0.0

        logger.debug(
            f"[RiskManager] Position size para {symbol}: "
            f"{qty:.4f} acciones (${available_value:.2f}) | "
            f"equity=${equity:.2f} | bp=${buying_power:.2f}"
        )

        return round(qty, 4)

    # ══════════════════════════════════════════════════════════════
    # ── Registro de operaciones (llamado por engine) ─────────────
    # ══════════════════════════════════════════════════════════════

    def record_trade(self, pnl: float = 0.0) -> None:
        """
        Registra que se ejecuto un trade.
        Incrementa el contador diario y acumula P&L.

        Args:
            pnl: P&L realizado del trade (0 si aun no se sabe).
        """
        self._check_day_reset()
        self._trades_today += 1
        self._daily_pnl += pnl
        logger.debug(
            f"[RiskManager] Trade registrado #{self._trades_today} | "
            f"pnl=${pnl:.2f} | daily_pnl=${self._daily_pnl:.2f}"
        )

    def update_daily_pnl(self, pnl: float) -> None:
        """Actualiza el P&L diario acumulado (setea el valor absoluto, no suma)."""
        self._daily_pnl = pnl

    # ══════════════════════════════════════════════════════════════
    # ── Estado y configuracion ───────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    @property
    def limits(self) -> RiskLimits:
        """Retorna los limites de riesgo actuales."""
        return self._limits

    def update_limits(self, **kwargs) -> None:
        """
        Actualiza limites de riesgo en runtime.

        Args:
            **kwargs: Campos de RiskLimits a actualizar.
        """
        for key, value in kwargs.items():
            if hasattr(self._limits, key):
                setattr(self._limits, key, value)
                logger.info(f"[RiskManager] Limite actualizado: {key}={value}")
            else:
                logger.warning(f"[RiskManager] Limite desconocido: {key}")

    def get_status(self) -> dict[str, Any]:
        """Retorna el estado actual del risk manager."""
        return {
            "limits": {
                "max_daily_loss_pct": self._limits.max_daily_loss_pct,
                "max_position_size_pct": self._limits.max_position_size_pct,
                "max_trades_per_day": self._limits.max_trades_per_day,
                "max_open_positions": self._limits.max_open_positions,
                "min_buying_power_pct": self._limits.min_buying_power_pct,
            },
            "daily": {
                "date": self._current_date.isoformat() if self._current_date else None,
                "pnl": self._daily_pnl,
                "trades_count": self._trades_today,
                "equity_start_of_day": self._equity_start_of_day,
            },
            "account": {
                "equity": self._last_account.equity if self._last_account else None,
                "cash": self._last_account.cash if self._last_account else None,
                "buying_power": (
                    self._last_account.buying_power if self._last_account else None
                ),
            },
            "open_positions": len(self._last_positions),
        }

    # ══════════════════════════════════════════════════════════════
    # ── Helpers internos ─────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════

    async def _refresh_state(self, broker: BrokerInterface) -> None:
        """Refresca datos de cuenta y posiciones desde el broker."""
        self._last_account, self._last_positions = await asyncio.gather(
            broker.get_account(),
            broker.get_positions(),
        )

        # Inicializar equity de inicio de dia si es la primera vez
        if (
            self._equity_start_of_day <= 0
            and self._last_account
            and self._last_account.equity > 0
        ):
            self._equity_start_of_day = self._last_account.equity

    def _check_day_reset(self) -> None:
        """Resetea contadores diarios si cambio el dia."""
        today = date.today()

        if self._current_date != today:
            if self._current_date is not None:
                logger.info(
                    f"[RiskManager] Nuevo dia de trading: {today} | "
                    f"Dia anterior: pnl=${self._daily_pnl:.2f}, "
                    f"trades={self._trades_today}"
                )
            self._current_date = today
            self._daily_pnl = 0.0
            self._trades_today = 0

            # Actualizar equity de inicio de dia
            if self._last_account and self._last_account.equity > 0:
                self._equity_start_of_day = self._last_account.equity
