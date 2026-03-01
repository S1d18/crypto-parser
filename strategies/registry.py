"""
Strategy Registry - система авто-обнаружения стратегий.

Автоматически находит и регистрирует все стратегии в директориях:
- strategies/live/
- strategies/paper/
- strategies/arbitrage/

Использует plugin pattern для динамической загрузки.
"""
import logging
import inspect
import importlib
from pathlib import Path
from typing import Dict, Type, List, Optional

from strategies.base import Strategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Реестр всех доступных торговых стратегий."""

    def __init__(self):
        self._strategies: Dict[str, Type[Strategy]] = {}
        self._instances: Dict[str, Strategy] = {}
        self._auto_discover()

    def register(self, strategy_class: Type[Strategy]):
        """
        Зарегистрировать класс стратегии.

        Args:
            strategy_class: класс наследующий Strategy
        """
        if not issubclass(strategy_class, Strategy):
            raise TypeError(f"{strategy_class.__name__} must inherit from Strategy")

        name = strategy_class.__name__
        self._strategies[name] = strategy_class
        logger.info(f"✓ Registered strategy: {name}")

    def get(self, name: str) -> Optional[Type[Strategy]]:
        """
        Получить класс стратегии по имени.

        Args:
            name: имя класса стратегии

        Returns:
            Strategy class или None
        """
        return self._strategies.get(name)

    def get_all(self) -> Dict[str, Type[Strategy]]:
        """Получить все зарегистрированные стратегии."""
        return self._strategies.copy()

    def get_by_category(self, category: str) -> Dict[str, Type[Strategy]]:
        """
        Получить стратегии по категории.

        Args:
            category: 'live', 'paper', 'arbitrage'

        Returns:
            dict с стратегиями этой категории
        """
        result = {}
        for name, cls in self._strategies.items():
            # Определить категорию по модулю
            module_path = cls.__module__
            if f'.{category}.' in module_path or module_path.endswith(f'.{category}'):
                result[name] = cls
        return result

    def list_strategies(self) -> List[str]:
        """Получить список имён всех стратегий."""
        return list(self._strategies.keys())

    def count(self) -> int:
        """Получить количество зарегистрированных стратегий."""
        return len(self._strategies)

    def create_instance(self, name: str, symbol: str, timeframe: str, config: dict) -> Strategy:
        """
        Создать экземпляр стратегии.

        Args:
            name: имя класса стратегии
            symbol: торговый символ
            timeframe: таймфрейм
            config: конфигурация стратегии

        Returns:
            Strategy instance
        """
        strategy_class = self.get(name)
        if not strategy_class:
            raise ValueError(f"Strategy '{name}' not found in registry")

        instance = strategy_class(symbol, timeframe, config)
        self._instances[name] = instance
        return instance

    def _auto_discover(self):
        """Автоматически обнаружить все стратегии."""
        base_path = Path(__file__).parent
        logger.info("Starting strategy auto-discovery...")

        categories = ['live', 'paper', 'arbitrage']
        total_found = 0

        for category in categories:
            category_path = base_path / category
            if not category_path.exists():
                logger.warning(f"Category path does not exist: {category_path}")
                continue

            found = self._discover_in_directory(category_path, category)
            total_found += found

        logger.info(f"✓ Auto-discovery complete: {total_found} strategies found")

    def _discover_in_directory(self, directory: Path, category: str) -> int:
        """
        Обнаружить стратегии в директории.

        Args:
            directory: путь к директории
            category: категория ('live', 'paper', 'arbitrage')

        Returns:
            количество найденных стратегий
        """
        found_count = 0

        for py_file in directory.glob('*.py'):
            # Пропустить __init__ и приватные файлы
            if py_file.stem.startswith('_'):
                continue

            try:
                # Импортировать модуль
                module_name = f"strategies.{category}.{py_file.stem}"
                module = importlib.import_module(module_name)

                # Найти все классы Strategy в модуле
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Проверить что это подкласс Strategy (но не сам Strategy)
                    if issubclass(obj, Strategy) and obj != Strategy:
                        # Проверить что класс определён в этом модуле (не импортирован)
                        if obj.__module__ == module_name:
                            self.register(obj)
                            found_count += 1

            except Exception as e:
                logger.error(f"Error loading {py_file}: {e}")

        return found_count


# Singleton instance
_registry_instance: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Получить singleton instance реестра стратегий."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = StrategyRegistry()
    return _registry_instance
