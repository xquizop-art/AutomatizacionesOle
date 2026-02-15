"""
Auto-descubrimiento de estrategias.
Escanea el directorio strategies/ y registra todas las clases que hereden de BaseStrategy.

Uso:
    from backend.strategies.registry import StrategyRegistry

    registry = StrategyRegistry()
    registry.discover()                        # Escanea y registra automaticamente
    names = registry.list_strategies()          # ["sma_crossover", "rsi_strategy"]
    strat = registry.get_strategy("sma_crossover")  # Instancia de SMA Crossover
"""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Optional, Type

from loguru import logger

from backend.strategies.base_strategy import BaseStrategy


class StrategyRegistry:
    """
    Registro central de estrategias.

    Descubre automaticamente todas las clases que hereden de BaseStrategy
    en el directorio backend/strategies/ y las registra por nombre.

    Tambien permite registro manual para estrategias definidas fuera
    del directorio estandar.
    """

    def __init__(self) -> None:
        # {strategy_name: strategy_class}
        self._registry: dict[str, Type[BaseStrategy]] = {}
        # {strategy_name: strategy_instance} — instancias activas
        self._instances: dict[str, BaseStrategy] = {}

    # ── Auto-descubrimiento ──────────────────────────────────

    def discover(self) -> list[str]:
        """
        Escanea el paquete backend.strategies y registra todas las
        subclases de BaseStrategy encontradas.

        Ignora:
            - base_strategy.py (la clase abstracta misma)
            - registry.py (este modulo)
            - __init__.py
            - Clases abstractas (que no implementan todos los metodos)

        Returns:
            Lista de nombres de estrategias descubiertas.
        """
        strategies_dir = Path(__file__).parent
        package_name = "backend.strategies"
        discovered: list[str] = []

        logger.info(f"Escaneando estrategias en {strategies_dir} ...")

        # Iterar sobre todos los modulos .py en el directorio
        for module_info in pkgutil.iter_modules([str(strategies_dir)]):
            module_name = module_info.name

            # Ignorar modulos internos del sistema
            if module_name in ("base_strategy", "registry", "__init__"):
                continue

            full_module_name = f"{package_name}.{module_name}"

            try:
                module = importlib.import_module(full_module_name)
            except Exception as e:
                logger.error(
                    f"Error importando modulo '{full_module_name}': {e}"
                )
                continue

            # Buscar clases que hereden de BaseStrategy
            for attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(attr_value, BaseStrategy)
                    and attr_value is not BaseStrategy
                    and not inspect.isabstract(attr_value)
                ):
                    self._register_class(attr_value)
                    discovered.append(attr_value.name)

        logger.info(
            f"Descubrimiento completado: {len(discovered)} estrategia(s) "
            f"encontrada(s): {discovered}"
        )
        return discovered

    # ── Registro manual ──────────────────────────────────────

    def register(self, strategy_class: Type[BaseStrategy]) -> None:
        """
        Registra manualmente una clase de estrategia.

        Args:
            strategy_class: Clase que hereda de BaseStrategy.

        Raises:
            TypeError: Si la clase no hereda de BaseStrategy.
            ValueError: Si la clase es abstracta.
        """
        if not issubclass(strategy_class, BaseStrategy):
            raise TypeError(
                f"{strategy_class.__name__} no hereda de BaseStrategy"
            )
        if inspect.isabstract(strategy_class):
            raise ValueError(
                f"{strategy_class.__name__} es abstracta y no se puede registrar"
            )
        self._register_class(strategy_class)

    def _register_class(self, strategy_class: Type[BaseStrategy]) -> None:
        """Registra una clase internamente."""
        name = strategy_class.name
        if not name:
            logger.warning(
                f"Clase {strategy_class.__name__} no tiene 'name' definido, ignorada"
            )
            return

        if name in self._registry:
            existing = self._registry[name].__name__
            logger.warning(
                f"Estrategia '{name}' ya registrada ({existing}), "
                f"sobreescribiendo con {strategy_class.__name__}"
            )

        self._registry[name] = strategy_class
        logger.debug(
            f"Registrada: '{name}' -> {strategy_class.__name__}"
        )

    # ── Consultas ────────────────────────────────────────────

    def list_strategies(self) -> list[str]:
        """Retorna la lista de nombres de estrategias registradas."""
        return sorted(self._registry.keys())

    def list_strategy_classes(self) -> dict[str, Type[BaseStrategy]]:
        """Retorna el diccionario completo {nombre: clase}."""
        return dict(self._registry)

    def get_strategy_class(self, name: str) -> Type[BaseStrategy]:
        """
        Retorna la clase de una estrategia por nombre.

        Args:
            name: Nombre de la estrategia.

        Raises:
            KeyError: Si la estrategia no esta registrada.
        """
        if name not in self._registry:
            available = ", ".join(self.list_strategies()) or "(ninguna)"
            raise KeyError(
                f"Estrategia '{name}' no encontrada. "
                f"Disponibles: {available}"
            )
        return self._registry[name]

    # ── Instancias ───────────────────────────────────────────

    def get_strategy(self, name: str) -> BaseStrategy:
        """
        Retorna una instancia de la estrategia. Si ya existe una instancia
        previa, la reutiliza (singleton por nombre).

        Args:
            name: Nombre de la estrategia.

        Returns:
            Instancia de la estrategia.

        Raises:
            KeyError: Si la estrategia no esta registrada.
        """
        if name in self._instances:
            return self._instances[name]

        strategy_class = self.get_strategy_class(name)
        instance = strategy_class()
        self._instances[name] = instance
        logger.info(f"Instancia creada para estrategia '{name}'")
        return instance

    def create_strategy(self, name: str, **kwargs) -> BaseStrategy:
        """
        Crea una nueva instancia de la estrategia (sin cache).

        Util cuando quieres multiples instancias con distintos parametros.

        Args:
            name: Nombre de la estrategia registrada.
            **kwargs: Parametros para pasar a update_parameters() despues de crear.

        Returns:
            Nueva instancia de la estrategia.
        """
        strategy_class = self.get_strategy_class(name)
        instance = strategy_class()

        if kwargs:
            instance.update_parameters(kwargs)

        return instance

    def get_active_strategies(self) -> dict[str, BaseStrategy]:
        """Retorna todas las instancias que estan en estado RUNNING."""
        return {
            name: strat
            for name, strat in self._instances.items()
            if strat.is_running
        }

    def get_all_instances(self) -> dict[str, BaseStrategy]:
        """Retorna todas las instancias creadas."""
        return dict(self._instances)

    def remove_instance(self, name: str) -> None:
        """
        Elimina una instancia del cache.
        Si la estrategia esta corriendo, la detiene primero.

        Args:
            name: Nombre de la estrategia.
        """
        if name in self._instances:
            instance = self._instances[name]
            if instance.is_running:
                instance.stop()
            del self._instances[name]
            logger.info(f"Instancia de '{name}' eliminada")

    # ── Informacion ──────────────────────────────────────────

    def get_all_info(self) -> list[dict]:
        """
        Retorna informacion de todas las estrategias registradas.
        Incluye tanto las instanciadas como las que solo estan registradas.
        """
        info_list = []
        for name, strategy_class in self._registry.items():
            if name in self._instances:
                info = self._instances[name].get_info()
                info_list.append({
                    "name": info.name,
                    "description": info.description,
                    "symbols": info.symbols,
                    "timeframe": info.timeframe,
                    "parameters": info.parameters,
                    "status": info.status.value,
                    "last_run": info.last_run.isoformat() if info.last_run else None,
                    "total_signals": info.total_signals,
                    "instantiated": True,
                })
            else:
                # Crear instancia temporal solo para obtener info
                try:
                    temp = strategy_class()
                    info = temp.get_info()
                    info_list.append({
                        "name": info.name,
                        "description": info.description,
                        "symbols": info.symbols,
                        "timeframe": info.timeframe,
                        "parameters": info.parameters,
                        "status": info.status.value,
                        "last_run": None,
                        "total_signals": 0,
                        "instantiated": False,
                    })
                except Exception as e:
                    logger.error(
                        f"Error obteniendo info de '{name}': {e}"
                    )
                    info_list.append({
                        "name": name,
                        "description": f"Error: {e}",
                        "symbols": [],
                        "timeframe": "unknown",
                        "parameters": {},
                        "status": "error",
                        "last_run": None,
                        "total_signals": 0,
                        "instantiated": False,
                    })

        return info_list

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, name: str) -> bool:
        return name in self._registry

    def __repr__(self) -> str:
        return (
            f"<StrategyRegistry "
            f"registered={len(self._registry)} "
            f"instances={len(self._instances)}>"
        )
