"""
SimulationRunner — запуск гидравлической симуляции через WNTR.

Отвечает исключительно за вычисления; UI-логика сюда не попадает.

Алгоритм
--------
1. Загрузить WaterNetworkModel из INP-файла (wntr).
2. Запустить EpanetSimulator.run_sim().
3. Упаковать результаты в SimulationResults и вернуть.

Все статусные сообщения передаются через callback-функцию `progress_cb`,
которую GUI подключает к своей строке состояния / прогресс-бару.
"""
from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

from .results import SimulationResults


# Тип колбэка: принимает строку сообщения и значение прогресса 0..100
ProgressCallback = Callable[[str, int], None]


class SimulationRunner:
    """
    Запускает гидравлическую симуляцию для INP/NET/EPANET файла.

    Parameters
    ----------
    filepath : str
        Путь к файлу гидравлической модели.
    progress_cb : ProgressCallback | None
        Опциональный колбэк вида (message: str, percent: int) -> None.
        GUI может подключить его к прогресс-бару и текстовому полю.
    """

    def __init__(
        self,
        filepath: str,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.filepath = Path(filepath)
        self._cb = progress_cb or (lambda msg, pct: None)
        self._tmp_inp: Optional[str] = None   # временный INP, если нужен

    # ── Публичный метод ───────────────────────────────────────────────────────

    def run(self) -> SimulationResults:
        """
        Выполняет полный цикл: загрузка → расчёт → упаковка результатов.

        Returns
        -------
        SimulationResults

        Raises
        ------
        ImportError  — если пакет wntr не установлен.
        RuntimeError — если симуляция завершилась с ошибкой.
        """
        try:
            import wntr  # noqa: F401 — проверяем наличие библиотеки
        except ImportError as exc:
            raise ImportError(
                "Библиотека 'wntr' не установлена.\n"
                "Установите её командой:  pip install wntr"
            ) from exc

        self._cb("Подготовка файла модели…", 5)
        inp_path = self._resolve_inp_path()

        self._cb("Загрузка гидравлической модели…", 20)
        wn = self._load_model(inp_path)

        self._cb("Запуск гидравлического расчёта (EPANET)…", 40)
        raw = self._simulate(wn)

        self._cb("Обработка результатов…", 80)
        results = self._pack_results(raw, wn, str(self.filepath))

        self._cb("Готово!", 100)
        self._cleanup()
        return results

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _resolve_inp_path(self) -> str:
        """
        Если файл — ZIP-архив (.epanet), извлечь INP во временную папку.
        Возвращает путь к готовому INP-файлу.
        """
        path = self.filepath
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {path}")

        # .epanet / .zip-архив
        if zipfile.is_zipfile(str(path)):
            with zipfile.ZipFile(str(path), "r") as z:
                inp_files = [f for f in z.namelist() if f.lower().endswith(".inp")]
                if not inp_files:
                    raise ValueError("Внутри архива .epanet не найден .inp файл.")
                tmp_dir = tempfile.mkdtemp(prefix="epanet_sim_")
                extracted = z.extract(inp_files[0], tmp_dir)
                self._tmp_inp = extracted
                return extracted

        # .net — бинарный формат Delphi; нужно сначала сконвертировать
        if path.suffix.lower() == ".net":
            return self._convert_net_to_inp(str(path))

        # .inp — возвращаем как есть
        return str(path)

    def _convert_net_to_inp(self, net_path: str) -> str:
        """
        Конвертирует бинарный .NET во временный .INP через уже
        существующие парсеры проекта (NetParser → ModelWriter).
        """
        from src.extract.net_parser import NetParser
        from src.load.writer import ModelWriter

        self._cb("Конвертация .NET → .INP…", 12)
        parser = NetParser(net_path)
        sections, order = parser.read()
        preamble = parser.get_preamble()

        tmp_dir = tempfile.mkdtemp(prefix="epanet_sim_")
        tmp_inp = os.path.join(tmp_dir, "model.inp")
        writer = ModelWriter(tmp_inp)
        writer.write(sections, order, preamble)
        self._tmp_inp = tmp_inp
        return tmp_inp

    def _load_model(self, inp_path: str):
        """Загружает WaterNetworkModel из INP-файла."""
        import wntr
        try:
            wn = wntr.network.WaterNetworkModel(inp_path)
        except Exception as exc:
            raise RuntimeError(f"Ошибка загрузки модели:\n{exc}") from exc
        return wn

    def _simulate(self, wn):
        """Запускает EpanetSimulator и возвращает сырые результаты."""
        import wntr
        try:
            sim = wntr.sim.EpanetSimulator(wn)
            results = sim.run_sim()
        except Exception as exc:
            raise RuntimeError(f"Ошибка расчёта:\n{exc}") from exc
        return results

    def _pack_results(self, raw, wn, original_path: str) -> SimulationResults:
        """
        Упаковывает сырые результаты WNTR в SimulationResults.

        Параметры узлов  : pressure, head, demand, quality
        Параметры звеньев: flowrate, velocity, status, headloss
        """
        import wntr  # noqa

        node_results = {}
        link_results = {}

        # ── Узловые параметры ─────────────────────────────────────────────
        for param in ("pressure", "head", "demand", "quality"):
            try:
                df = raw.node[param]
                if df is not None and not df.empty:
                    node_results[param] = df
            except (KeyError, AttributeError):
                pass

        # ── Линейные параметры ────────────────────────────────────────────
        for param in ("flowrate", "velocity", "status", "headloss"):
            try:
                df = raw.link[param]
                if df is not None and not df.empty:
                    link_results[param] = df
            except (KeyError, AttributeError):
                pass

        # ── Метаданные ────────────────────────────────────────────────────
        time_steps: List[float] = []
        if node_results:
            first_df = next(iter(node_results.values()))
            time_steps = list(first_df.index.astype(float))
        elif link_results:
            first_df = next(iter(link_results.values()))
            time_steps = list(first_df.index.astype(float))

        duration_h = max(time_steps) / 3600.0 if time_steps else 0.0

        node_names = list(wn.node_name_list)
        link_names = list(wn.link_name_list)

        return SimulationResults(
            node_results=node_results,
            link_results=link_results,
            node_names=node_names,
            link_names=link_names,
            time_steps=time_steps,
            duration_h=duration_h,
            filepath=original_path,
        )

    def _cleanup(self):
        """Удаляет временные файлы после расчёта."""
        if self._tmp_inp and os.path.exists(self._tmp_inp):
            try:
                os.remove(self._tmp_inp)
                tmp_dir = os.path.dirname(self._tmp_inp)
                if os.path.isdir(tmp_dir) and not os.listdir(tmp_dir):
                    os.rmdir(tmp_dir)
            except OSError:
                pass
            self._tmp_inp = None
