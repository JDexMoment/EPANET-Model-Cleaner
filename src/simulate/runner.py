"""
SimulationRunner — запуск гидравлической симуляции через WNTR.

Алгоритм
--------
1. Прочитать файл любого формата через ParserFactory.create().
2. Отфильтровать секции — оставить только те, что понимает WNTR.
3. Почистить [OPTIONS] от ключей с нечисловыми значениями.
4. Записать чистый INP через ModelWriter во временный файл.
5. Загрузить WaterNetworkModel из подготовленного INP.
6. Запустить EpanetSimulator.run_sim().
7. Упаковать результаты в SimulationResults и вернуть.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .results import SimulationResults

ProgressCallback = Callable[[str, int], None]


# ── Белый список секций, которые WNTR умеет читать ────────────────────────────
# Всё, чего нет в этом списке (PRESS, LABELS, TAGS, BACKDROP и др.),
# будет отброшено до передачи в WNTR.
WNTR_KNOWN_SECTIONS = {
    '[TITLE]',
    '[JUNCTIONS]',
    '[RESERVOIRS]',
    '[TANKS]',
    '[PIPES]',
    '[PUMPS]',
    '[VALVES]',
    '[TAGS]',           # WNTR читает, но не использует — безопасно оставить
    '[DEMANDS]',
    '[STATUS]',
    '[PATTERNS]',
    '[CURVES]',
    '[CONTROLS]',
    '[RULES]',
    '[ENERGY]',
    '[EMITTERS]',
    '[QUALITY]',
    '[SOURCES]',
    '[REACTIONS]',
    '[MIXING]',
    '[TIMES]',
    '[REPORT]',         # WNTR читает секцию [REPORT] (не ключ REPORT в OPTIONS)
    '[OPTIONS]',        # ОБЯЗАТЕЛЬНА — содержит единицы измерения
    '[COORDINATES]',
    '[VERTICES]',
    '[LABELS]',         # WNTR читает, но не использует — безопасно
    '[BACKDROP]',       # WNTR игнорирует, но не падает
    '[END]',
}

# Ключи в [OPTIONS], значения которых WNTR пытается привести к float,
# но там стоят строки ('No', 'Continue', 'Stop') → ValueError
PROBLEMATIC_OPTION_KEYS = {
    'unbalanced',   # UNBALANCED Continue 10 / No / Stop
    'map',          # MAP <filename.map>
}


class SimulationRunner:
    """
    Запускает гидравлическую симуляцию для INP/NET/EPANET файла.

    Parameters
    ----------
    filepath : str
        Путь к файлу гидравлической модели.
    progress_cb : ProgressCallback | None
        Опциональный колбэк вида (message: str, percent: int) -> None.
    """

    def __init__(
        self,
        filepath: str,
        progress_cb: Optional[ProgressCallback] = None,
    ):
        self.filepath = Path(filepath)
        self._cb = progress_cb or (lambda msg, pct: None)
        self._tmp_dir: Optional[str] = None

    # ── Публичный метод ───────────────────────────────────────────────────────

    def run(self) -> SimulationResults:
        """
        Полный цикл: чтение → фильтрация → запись → расчёт → результаты.
        """
        try:
            import wntr  # noqa
        except ImportError as exc:
            raise ImportError(
                "Библиотека 'wntr' не установлена.\n"
                "Установите её командой:  pip install wntr"
            ) from exc

        self._cb("Чтение файла модели…", 5)
        inp_path = self._extract_to_clean_inp()

        self._cb("Загрузка гидравлической модели в WNTR…", 30)
        wn = self._load_model(inp_path)

        self._cb("Запуск гидравлического расчёта (EPANET)…", 50)
        raw = self._simulate(wn)

        self._cb("Обработка результатов…", 85)
        results = self._pack_results(raw, wn, str(self.filepath))

        self._cb("Готово!", 100)
        self._cleanup()
        return results

    # ── Внутренние методы ─────────────────────────────────────────────────────

    def _extract_to_clean_inp(self) -> str:
        """
        Главный метод подготовки файла:

        1. Читает файл любого формата через ParserFactory (INP/NET/EPANET/ZIP).
        2. Фильтрует секции — оставляет только те, что в WNTR_KNOWN_SECTIONS.
           Это убирает [PRESS], [VERTICES_EXTRA] и любые другие нестандартные
           секции, вызывающие ENSyntaxError 201.
        3. Очищает [OPTIONS] от ключей с нечисловыми значениями
           (UNBALANCED, MAP), вызывающих ValueError в WNTR.
        4. Записывает результат через ModelWriter во временный INP.
        """
        from src.extract.factory import ParserFactory
        from src.load.writer import ModelWriter

        if not self.filepath.exists():
            raise FileNotFoundError(f"Файл не найден: {self.filepath}")

        # ── Шаг 1: читаем файл через фабрику ──────────────────────────────
        self._cb("Парсинг файла модели…", 8)
        try:
            parser = ParserFactory.create(str(self.filepath))
            sections, order = parser.read()
            preamble = parser.get_preamble()
        except Exception as exc:
            raise RuntimeError(
                f"Не удалось прочитать файл '{self.filepath.name}':\n{exc}"
            ) from exc

        # ── Шаг 2: фильтруем секции по белому списку ──────────────────────
        # Убираем всё нестандартное ([PRESS], [BACKDROP] нестандартный и т.д.)
        filtered_sections: Dict[str, List[str]] = {}
        filtered_order: List[str] = []

        skipped = []
        for sec_name in order:
            if sec_name in WNTR_KNOWN_SECTIONS:
                filtered_sections[sec_name] = sections[sec_name]
                filtered_order.append(sec_name)
            else:
                skipped.append(sec_name)

        if skipped:
            self._cb(
                f"Пропущены нестандартные секции: {', '.join(skipped)}", 12
            )

        # ── Шаг 3: чистим [OPTIONS] от проблемных ключей ──────────────────
        if '[OPTIONS]' in filtered_sections:
            filtered_sections['[OPTIONS]'] = self._filter_options(
                filtered_sections['[OPTIONS]']
            )

        # ── Шаг 4: записываем чистый INP во временную папку ───────────────
        self._tmp_dir = tempfile.mkdtemp(prefix='epanet_sim_')
        tmp_inp = os.path.join(self._tmp_dir, 'model_clean.inp')

        self._cb("Запись подготовленного INP-файла…", 18)
        try:
            writer = ModelWriter(tmp_inp)
            writer.write(filtered_sections, filtered_order, preamble)
        except Exception as exc:
            raise RuntimeError(
                f"Ошибка записи временного INP-файла:\n{exc}"
            ) from exc

        return tmp_inp

    def _filter_options(self, lines: List[str]) -> List[str]:
        """
        Фильтрует строки секции [OPTIONS]:
        убирает ключи, чьи значения WNTR не может привести к float.

        Безопасные строковые значения, которые WNTR обрабатывает сам
        (UNITS, QUALITY, HEADLOSS, HYDRAULICS и др.) — не трогаем.
        """
        result = []
        for line in lines:
            stripped = line.strip()

            # Пустые строки и комментарии — оставляем
            if not stripped or stripped.startswith(';'):
                result.append(line)
                continue

            # Убираем inline-комментарий для анализа ключа
            code = stripped.split(';')[0].strip()
            parts = code.split()

            if len(parts) >= 2:
                key = parts[0].lower()
                value = parts[1]

                if key in PROBLEMATIC_OPTION_KEYS:
                    try:
                        float(value)
                        # Значение числовое — WNTR справится, оставляем
                        result.append(line)
                    except ValueError:
                        # Значение строковое — WNTR упадёт, пропускаем
                        # Логируем для отладки
                        result.append(f'; [SIM_SKIP] {line}')
                        continue
                else:
                    result.append(line)
            else:
                result.append(line)

        return result

    def _load_model(self, inp_path: str):
        """
        Загружает WaterNetworkModel из уже подготовленного INP-файла.
        К этому моменту файл уже чистый — дополнительный препроцессинг не нужен.
        """
        import wntr
        try:
            wn = wntr.network.WaterNetworkModel(inp_path)
            return wn
        except Exception as exc:
            raise RuntimeError(f"Ошибка загрузки модели:\n{exc}") from exc

    def _simulate(self, wn) -> object:
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

        Узловые параметры : pressure, head, demand, quality
        Линейные параметры: flowrate, velocity, status, headloss
        """
        node_results: Dict = {}
        link_results: Dict = {}

        for param in ('pressure', 'head', 'demand', 'quality'):
            try:
                df = raw.node[param]
                if df is not None and not df.empty:
                    node_results[param] = df
            except (KeyError, AttributeError):
                pass

        for param in ('flowrate', 'velocity', 'status', 'headloss'):
            try:
                df = raw.link[param]
                if df is not None and not df.empty:
                    link_results[param] = df
            except (KeyError, AttributeError):
                pass

        time_steps: List[float] = []
        if node_results:
            time_steps = list(next(iter(node_results.values())).index.astype(float))
        elif link_results:
            time_steps = list(next(iter(link_results.values())).index.astype(float))

        duration_h = max(time_steps) / 3600.0 if time_steps else 0.0

        return SimulationResults(
            node_results=node_results,
            link_results=link_results,
            node_names=list(wn.node_name_list),
            link_names=list(wn.link_name_list),
            time_steps=time_steps,
            duration_h=duration_h,
            filepath=original_path,
        )

    def _cleanup(self):
        """Удаляет временную директорию со всеми файлами после расчёта."""
        if self._tmp_dir and os.path.isdir(self._tmp_dir):
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            self._tmp_dir = None