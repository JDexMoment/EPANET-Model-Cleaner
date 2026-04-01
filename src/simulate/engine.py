"""
Движок симуляции EPANET моделей.
Обёртка над WNTR для запуска гидравлических расчётов.
"""

import wntr
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass
from enum import Enum

from .results import SimulationResults


class SimulatorType(Enum):
    """Тип симулятора."""
    WNTR = "wntr"  # Чистый Python, медленнее но гибче
    EPANET = "epanet"  # Нативный EPANET, быстрее


@dataclass
class SimulationConfig:
    """Конфигурация симуляции."""
    duration: Optional[int] = None  # Переопределить длительность (секунды)
    hydraulic_timestep: Optional[int] = None  # Шаг расчёта (секунды)
    report_timestep: Optional[int] = None  # Шаг отчёта (секунды)
    simulator: SimulatorType = SimulatorType.EPANET


class SimulationEngine:
    """
    Движок для запуска гидравлических симуляций EPANET.

    Примеры использования:
        >>> engine = SimulationEngine("model.inp")
        >>> results = engine.run()
        >>> print(results.get_node_pressure("Junction-1"))
    """

    def __init__(self, model_path: Union[str, Path]):
        """
        Инициализация движка.

        Args:
            model_path: Путь к файлу модели (.inp)
        """
        self.model_path = Path(model_path)
        self._validate_model_path()
        self._network: Optional[wntr.network.WaterNetworkModel] = None
        self._results: Optional[SimulationResults] = None

    def _validate_model_path(self) -> None:
        """Проверка существования и формата файла."""
        if not self.model_path.exists():
            raise FileNotFoundError(f"Файл модели не найден: {self.model_path}")
        if self.model_path.suffix.lower() != '.inp':
            raise ValueError(f"Ожидается файл .inp, получен: {self.model_path.suffix}")

    def load_network(self) -> wntr.network.WaterNetworkModel:
        """
        Загрузка сети из файла.

        Returns:
            WaterNetworkModel: Объект сети WNTR
        """
        if self._network is None:
            self._network = wntr.network.WaterNetworkModel(str(self.model_path))
        return self._network

    @property
    def network(self) -> wntr.network.WaterNetworkModel:
        """Получение загруженной сети."""
        return self.load_network()

    def configure(self, config: SimulationConfig) -> 'SimulationEngine':
        """
        Применение конфигурации к модели.

        Args:
            config: Объект конфигурации

        Returns:
            self для цепочки вызовов
        """
        network = self.load_network()

        if config.duration is not None:
            network.options.time.duration = config.duration

        if config.hydraulic_timestep is not None:
            network.options.time.hydraulic_timestep = config.hydraulic_timestep

        if config.report_timestep is not None:
            network.options.time.report_timestep = config.report_timestep

        return self

    def run(self, config: Optional[SimulationConfig] = None) -> SimulationResults:
        """
        Запуск гидравлической симуляции.

        Args:
            config: Опциональная конфигурация

        Returns:
            SimulationResults: Результаты расчёта
        """
        if config:
            self.configure(config)

        network = self.load_network()

        # Выбор симулятора
        simulator_type = config.simulator if config else SimulatorType.EPANET

        if simulator_type == SimulatorType.EPANET:
            sim = wntr.sim.EpanetSimulator(network)
        else:
            sim = wntr.sim.WNTRSimulator(network)

        # Запуск расчёта
        raw_results = sim.run_sim()

        # Оборачиваем в наш класс результатов
        self._results = SimulationResults(raw_results, network)

        return self._results

    def get_network_info(self) -> dict:
        """
        Получение информации о сети.

        Returns:
            dict: Статистика по элементам сети
        """
        network = self.load_network()

        return {
            'junctions': len(network.junction_name_list),
            'reservoirs': len(network.reservoir_name_list),
            'tanks': len(network.tank_name_list),
            'pipes': len(network.pipe_name_list),
            'pumps': len(network.pump_name_list),
            'valves': len(network.valve_name_list),
            'duration_hours': network.options.time.duration / 3600,
            'hydraulic_timestep_minutes': network.options.time.hydraulic_timestep / 60,
            'report_timestep_minutes': network.options.time.report_timestep / 60,
        }

    def get_node_names(self) -> list[str]:
        """Список всех узлов."""
        return self.network.node_name_list

    def get_link_names(self) -> list[str]:
        """Список всех связей (трубы, насосы, клапаны)."""
        return self.network.link_name_list