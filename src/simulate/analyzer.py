"""
Анализатор результатов симуляции и построение графиков.
"""

import pandas as pd
import numpy as np
from typing import List, Optional, Union, Tuple
from dataclasses import dataclass
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

from .results import SimulationResults, NodeParameter, LinkParameter, TimeSeriesData


@dataclass
class PlotConfig:
    """Конфигурация графика."""
    figsize: Tuple[int, int] = (12, 6)
    dpi: int = 100
    grid: bool = True
    legend: bool = True
    title: Optional[str] = None
    xlabel: str = "Время (часы)"
    ylabel: Optional[str] = None
    style: str = 'seaborn-v0_8-whitegrid'


class ResultsAnalyzer:
    """
    Анализатор результатов симуляции.

    Предоставляет методы для:
    - Построения графиков
    - Сравнительного анализа
    - Поиска критических точек
    """

    def __init__(self, results: SimulationResults):
        """
        Args:
            results: Результаты симуляции
        """
        self.results = results

    # ==================== Построение графиков ====================

    def plot_node_parameter(
            self,
            node_names: Union[str, List[str]],
            parameter: Union[str, NodeParameter],
            config: Optional[PlotConfig] = None,
            ax: Optional[plt.Axes] = None
    ) -> plt.Figure:
        """
        График параметра для одного или нескольких узлов.

        Args:
            node_names: Название узла или список узлов
            parameter: Параметр для отображения
            config: Конфигурация графика
            ax: Существующие оси (опционально)

        Returns:
            Figure: Объект графика matplotlib
        """
        if config is None:
            config = PlotConfig()

        if isinstance(node_names, str):
            node_names = [node_names]

        if isinstance(parameter, NodeParameter):
            parameter = parameter.value

        # Создание или использование существующих осей
        if ax is None:
            plt.style.use(config.style)
            fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi)
        else:
            fig = ax.get_figure()

        # Построение линий
        for node_name in node_names:
            ts = self.results.get_node_parameter(node_name, parameter)
            ax.plot(ts.times / 3600, ts.values, label=node_name, linewidth=1.5)

        # Оформление
        ax.set_xlabel(config.xlabel)
        ax.set_ylabel(config.ylabel or f"{parameter.capitalize()} ({ts.units})")
        ax.set_title(config.title or f"{parameter.capitalize()} по времени")

        if config.grid:
            ax.grid(True, alpha=0.3)
        if config.legend and len(node_names) > 1:
            ax.legend(loc='best')

        plt.tight_layout()
        return fig

    def plot_link_parameter(
            self,
            link_names: Union[str, List[str]],
            parameter: Union[str, LinkParameter],
            config: Optional[PlotConfig] = None,
            ax: Optional[plt.Axes] = None
    ) -> plt.Figure:
        """
        График параметра для связей.
        """
        if config is None:
            config = PlotConfig()

        if isinstance(link_names, str):
            link_names = [link_names]

        if isinstance(parameter, LinkParameter):
            parameter = parameter.value

        if ax is None:
            plt.style.use(config.style)
            fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi)
        else:
            fig = ax.get_figure()

        for link_name in link_names:
            ts = self.results.get_link_parameter(link_name, parameter)
            ax.plot(ts.times / 3600, ts.values, label=link_name, linewidth=1.5)

        ax.set_xlabel(config.xlabel)
        ax.set_ylabel(config.ylabel or f"{parameter.capitalize()} ({ts.units})")
        ax.set_title(config.title or f"{parameter.capitalize()} по времени")

        if config.grid:
            ax.grid(True, alpha=0.3)
        if config.legend and len(link_names) > 1:
            ax.legend(loc='best')

        plt.tight_layout()
        return fig

    def plot_comparison(
            self,
            elements: List[str],
            parameter: Union[str, NodeParameter, LinkParameter],
            element_type: str = 'node',
            config: Optional[PlotConfig] = None
    ) -> plt.Figure:
        """
        Сравнительный график для нескольких элементов.

        Args:
            elements: Список названий элементов
            parameter: Параметр
            element_type: 'node' или 'link'
            config: Конфигурация
        """
        if element_type == 'node':
            return self.plot_node_parameter(elements, parameter, config)
        else:
            return self.plot_link_parameter(elements, parameter, config)

    def plot_multiple_parameters(
            self,
            element_name: str,
            parameters: List[Union[str, NodeParameter]],
            element_type: str = 'node',
            config: Optional[PlotConfig] = None
    ) -> plt.Figure:
        """
        График нескольких параметров для одного элемента.

        Args:
            element_name: Название элемента
            parameters: Список параметров
            element_type: 'node' или 'link'
        """
        if config is None:
            config = PlotConfig()

        n_params = len(parameters)
        fig, axes = plt.subplots(n_params, 1, figsize=(config.figsize[0], 4 * n_params),
                                 dpi=config.dpi, sharex=True)

        if n_params == 1:
            axes = [axes]

        for ax, param in zip(axes, parameters):
            if element_type == 'node':
                ts = self.results.get_node_parameter(element_name, param)
            else:
                ts = self.results.get_link_parameter(element_name, param)

            param_name = param.value if hasattr(param, 'value') else param
            ax.plot(ts.times / 3600, ts.values, linewidth=1.5, color='steelblue')
            ax.set_ylabel(f"{param_name}\n({ts.units})")
            ax.grid(True, alpha=0.3)

        axes[-1].set_xlabel(config.xlabel)
        fig.suptitle(f"Параметры элемента: {element_name}", fontsize=12)

        plt.tight_layout()
        return fig

    def plot_pressure_profile(
            self,
            time_seconds: float,
            node_names: Optional[List[str]] = None,
            config: Optional[PlotConfig] = None
    ) -> plt.Figure:
        """
        Профиль давления в узлах в заданный момент времени.

        Args:
            time_seconds: Момент времени
            node_names: Список узлов (все если None)
        """
        if config is None:
            config = PlotConfig()

        snapshot = self.results.at_time(time_seconds)
        pressures = snapshot['nodes']['pressure']

        if node_names is not None:
            pressures = pressures[node_names]

        fig, ax = plt.subplots(figsize=config.figsize, dpi=config.dpi)

        x = range(len(pressures))
        bars = ax.bar(x, pressures.values, color='steelblue', alpha=0.7)

        ax.set_xticks(x)
        ax.set_xticklabels(pressures.index, rotation=45, ha='right')
        ax.set_xlabel("Узел")
        ax.set_ylabel("Давление (м)")
        ax.set_title(f"Профиль давления в t = {time_seconds / 3600:.1f} ч")

        if config.grid:
            ax.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()
        return fig

    # ==================== Анализ ====================

    def find_min_pressure_nodes(self, n: int = 5) -> pd.DataFrame:
        """
        Найти узлы с минимальным давлением.

        Args:
            n: Количество узлов

        Returns:
            DataFrame с узлами и их минимальными давлениями
        """
        pressure_df = self.results.get_node_dataframe('pressure')
        min_pressures = pressure_df.min()

        return min_pressures.nsmallest(n).to_frame('min_pressure')

    def find_max_velocity_links(self, n: int = 5) -> pd.DataFrame:
        """
        Найти связи с максимальной скоростью.
        """
        velocity_df = self.results.get_link_dataframe('velocity')
        max_velocities = velocity_df.max()

        return max_velocities.nlargest(n).to_frame('max_velocity')

    def check_pressure_violations(
            self,
            min_pressure: float = 10.0,
            max_pressure: float = 80.0
    ) -> pd.DataFrame:
        """
        Найти нарушения ограничений по давлению.

        Args:
            min_pressure: Минимально допустимое давление (м)
            max_pressure: Максимально допустимое давление (м)

        Returns:
            DataFrame с нарушениями
        """
        pressure_df = self.results.get_node_dataframe('pressure')

        violations = []

        for node in pressure_df.columns:
            series = pressure_df[node]

            low_mask = series < min_pressure
            if low_mask.any():
                violations.append({
                    'node': node,
                    'type': 'low_pressure',
                    'value': series[low_mask].min(),
                    'time_hours': series[low_mask].idxmin() / 3600,
                })

            high_mask = series > max_pressure
            if high_mask.any():
                violations.append({
                    'node': node,
                    'type': 'high_pressure',
                    'value': series[high_mask].max(),
                    'time_hours': series[high_mask].idxmax() / 3600,
                })

        return pd.DataFrame(violations)

    def check_velocity_violations(self, max_velocity: float = 2.0) -> pd.DataFrame:
        """
        Найти нарушения ограничений по скорости.

        Args:
            max_velocity: Максимально допустимая скорость (м/с)
        """
        velocity_df = self.results.get_link_dataframe('velocity')

        violations = []

        for link in velocity_df.columns:
            series = velocity_df[link].abs()  # Абсолютное значение

            if (series > max_velocity).any():
                violations.append({
                    'link': link,
                    'max_velocity': series.max(),
                    'time_hours': series.idxmax() / 3600,
                })

        return pd.DataFrame(violations)

    def get_statistics(self, element_name: str,
                       parameter: str,
                       element_type: str = 'node') -> dict:
        """
        Получить статистику по элементу.
        """
        if element_type == 'node':
            ts = self.results.get_node_parameter(element_name, parameter)
        else:
            ts = self.results.get_link_parameter(element_name, parameter)

        return ts.statistics()