"""
SimulationResults — контейнер результатов гидравлического расчёта.

Хранит pandas DataFrames для узловых (node) и линейных (link) параметров.
Предоставляет удобный API для выборки по элементу/параметру/времени.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd


# ─── Константы русских меток ─────────────────────────────────────────────────

NODE_PARAM_LABELS: Dict[str, str] = {
    "pressure": "Давление, м",
    "head":     "Напор, м",
    "demand":   "Отбор, л/с",
    "quality":  "Качество",
}

LINK_PARAM_LABELS: Dict[str, str] = {
    "flowrate": "Расход, л/с",
    "velocity": "Скорость, м/с",
    "status":   "Статус",
    "headloss": "Потери напора, м",
}

ALL_PARAM_LABELS: Dict[str, str] = {**NODE_PARAM_LABELS, **LINK_PARAM_LABELS}


@dataclass
class SimulationResults:
    """
    Контейнер результатов одной гидравлической симуляции.

    Атрибуты
    --------
    node_results : dict[str, DataFrame]
        Ключ — название параметра (pressure, head, demand, quality).
        DataFrame: index=время_секунды, columns=имена_узлов.

    link_results : dict[str, DataFrame]
        Ключ — название параметра (flowrate, velocity, status, headloss).
        DataFrame: index=время_секунды, columns=имена_звеньев.

    node_names : list[str]   — все узлы (junctions + reservoirs + tanks).
    link_names : list[str]   — все звенья (pipes + pumps + valves).
    time_steps : list[float] — временны́е метки в секундах.
    duration_h : float       — длительность симуляции в часах.
    filepath   : str         — путь к INP-файлу.
    """

    node_results: Dict[str, pd.DataFrame] = field(default_factory=dict)
    link_results: Dict[str, pd.DataFrame] = field(default_factory=dict)
    node_names:   List[str] = field(default_factory=list)
    link_names:   List[str] = field(default_factory=list)
    time_steps:   List[float] = field(default_factory=list)
    duration_h:   float = 0.0
    filepath:     str = ""

    # ── Вспомогательные свойства ──────────────────────────────────────────────

    @property
    def node_params(self) -> List[str]:
        """Список доступных узловых параметров."""
        return list(self.node_results.keys())

    @property
    def link_params(self) -> List[str]:
        """Список доступных линейных параметров."""
        return list(self.link_results.keys())

    @property
    def all_params(self) -> List[str]:
        return self.node_params + self.link_params

    @property
    def time_steps_hours(self) -> List[float]:
        """Временны́е метки в часах."""
        return [t / 3600.0 for t in self.time_steps]

    # ── Методы выборки ────────────────────────────────────────────────────────

    def get_node_series(self, param: str, node_id: str) -> pd.Series:
        """
        Временно́й ряд параметра для одного узла.

        Parameters
        ----------
        param   : str  — ключ параметра ('pressure', 'head', …)
        node_id : str  — ID узла

        Returns
        -------
        pd.Series (index = время в часах)
        """
        if param not in self.node_results:
            raise KeyError(f"Параметр '{param}' не найден в узловых результатах.")
        df = self.node_results[param]
        if node_id not in df.columns:
            raise KeyError(f"Узел '{node_id}' не найден.")
        series = df[node_id].copy()
        series.index = series.index / 3600.0
        series.name = f"{node_id} — {NODE_PARAM_LABELS.get(param, param)}"
        return series

    def get_link_series(self, param: str, link_id: str) -> pd.Series:
        """
        Временно́й ряд параметра для одного звена (трубы/насоса/задвижки).
        """
        if param not in self.link_results:
            raise KeyError(f"Параметр '{param}' не найден в линейных результатах.")
        df = self.link_results[param]
        if link_id not in df.columns:
            raise KeyError(f"Звено '{link_id}' не найдено.")
        series = df[link_id].copy()
        series.index = series.index / 3600.0
        series.name = f"{link_id} — {LINK_PARAM_LABELS.get(param, param)}"
        return series

    def get_snapshot(self, param: str, time_sec: float) -> pd.Series:
        """
        Снимок параметра для всех узлов/звеньев в заданный момент времени.
        Ищет ближайшую временну́ю метку.
        """
        if param in self.node_results:
            df = self.node_results[param]
        elif param in self.link_results:
            df = self.link_results[param]
        else:
            raise KeyError(f"Параметр '{param}' не найден.")
        idx = df.index.get_indexer([time_sec], method="nearest")[0]
        return df.iloc[idx]

    def get_matrix_for_element(self, element_id: str) -> pd.DataFrame:
        """
        Сводная таблица всех доступных параметров для заданного
        узла или звена: строки = время (часы), столбцы = параметры.
        """
        frames: Dict[str, pd.Series] = {}

        for param, df in self.node_results.items():
            if element_id in df.columns:
                s = df[element_id].copy()
                s.index = s.index / 3600.0
                frames[NODE_PARAM_LABELS.get(param, param)] = s

        for param, df in self.link_results.items():
            if element_id in df.columns:
                s = df[element_id].copy()
                s.index = s.index / 3600.0
                frames[LINK_PARAM_LABELS.get(param, param)] = s

        if not frames:
            raise KeyError(f"Элемент '{element_id}' не найден в результатах.")

        result = pd.DataFrame(frames)
        result.index.name = "Время, ч"
        return result

    def summary(self) -> str:
        """Текстовое резюме расчёта."""
        lines = [
            f"Файл       : {self.filepath}",
            f"Длительность: {self.duration_h:.1f} ч",
            f"Шагов      : {len(self.time_steps)}",
            f"Узлов      : {len(self.node_names)}",
            f"Звеньев    : {len(self.link_names)}",
            f"Узловые параметры: {', '.join(self.node_params)}",
            f"Линейные параметры: {', '.join(self.link_params)}",
        ]
        return "\n".join(lines)
