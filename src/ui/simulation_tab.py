"""
SimulationTab — вкладка гидравлического расчёта.

Архитектура
-----------
* SimulationTab строится как отдельный фрейм и встраивается в главное окно.
* Вся UI-логика (кнопки, прогресс-бар, таблица, графики) сосредоточена здесь.
* Вычисления делегируются SimulationRunner (src/simulate/runner.py).
* Результаты хранятся в SimulationResults (src/simulate/results.py).

Функционал
----------
1. Кнопка «Выбрать файл и запустить расчёт».
2. Прогресс-бар + статусная строка.
3. Матрица результатов: Treeview (узел → параметры по шагам времени).
4. Панель фильтра: выбор элемента и параметра.
5. Кнопка «Построить график» — открывает окно matplotlib.
6. Кнопка «Экспорт в CSV».
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from src.simulate.results import (
    ALL_PARAM_LABELS,
    NODE_PARAM_LABELS,
    LINK_PARAM_LABELS,
    SimulationResults,
)
from src.simulate.runner import SimulationRunner


class SimulationTab(tk.Frame):
    """
    Фрейм-вкладка расчёта. Встраивается в notebook или напрямую в окно.
    """

    _COL_TIME   = "Время, ч"
    _TREE_WIDTH = 100          # ширина числового столбца в пикселях
    _MAX_COLS   = 12           # максимум столбцов в таблице (защита от широких моделей)

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(parent, **kwargs)
        self._results: Optional[SimulationResults] = None
        self._current_file: str = ""
        self._build_ui()

    # ═══════════════════════════════════════════════════════════════════════════
    #  Построение UI
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)   # таблица растягивается

        # ── Верхняя панель управления ─────────────────────────────────────────
        top = tk.Frame(self, pady=6)
        top.grid(row=0, column=0, sticky="ew", padx=8)

        tk.Button(
            top, text="📂  Выбрать файл и запустить расчёт",
            font=("Arial", 11, "bold"), bg="#2563eb", fg="white",
            activebackground="#1d4ed8", activeforeground="white",
            relief="flat", padx=14, pady=6,
            command=self._on_run,
        ).pack(side=tk.LEFT, padx=(0, 10))

        self._file_label = tk.Label(top, text="Файл не выбран", fg="#555",
                                    font=("Arial", 9), anchor="w")
        self._file_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Прогресс-бар ──────────────────────────────────────────────────────
        prog_frame = tk.Frame(self)
        prog_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        prog_frame.columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="Готов к расчёту.")
        tk.Label(prog_frame, textvariable=self._status_var,
                 font=("Arial", 9), fg="#333", anchor="w").grid(
            row=0, column=0, sticky="w")

        self._progress = ttk.Progressbar(prog_frame, mode="determinate",
                                         maximum=100, length=400)
        self._progress.grid(row=1, column=0, sticky="ew", pady=2)

        # ── Средняя область: фильтр + таблица ────────────────────────────────
        mid = tk.Frame(self)
        mid.grid(row=2, column=0, sticky="nsew", padx=8)
        mid.columnconfigure(1, weight=1)
        mid.rowconfigure(0, weight=1)

        # Левая панель фильтров
        self._build_filter_panel(mid)

        # Правая панель: таблица
        self._build_table_panel(mid)

        # ── Нижняя панель кнопок ──────────────────────────────────────────────
        self._build_action_panel()

    # ── Панель фильтров ───────────────────────────────────────────────────────

    def _build_filter_panel(self, parent: tk.Frame):
        panel = tk.LabelFrame(parent, text="Фильтр", font=("Arial", 9, "bold"),
                               padx=6, pady=6)
        panel.grid(row=0, column=0, sticky="ns", padx=(0, 6))

        # Тип элемента
        tk.Label(panel, text="Тип:", font=("Arial", 9)).pack(anchor="w")
        self._elem_type_var = tk.StringVar(value="Узлы")
        type_cb = ttk.Combobox(panel, textvariable=self._elem_type_var,
                                state="readonly", width=14,
                                values=["Узлы", "Звенья"])
        type_cb.pack(fill=tk.X, pady=(0, 6))
        type_cb.bind("<<ComboboxSelected>>", self._on_type_changed)

        # Элемент
        tk.Label(panel, text="Элемент:", font=("Arial", 9)).pack(anchor="w")
        self._element_var = tk.StringVar()
        self._element_cb = ttk.Combobox(panel, textvariable=self._element_var,
                                         state="readonly", width=14)
        self._element_cb.pack(fill=tk.X, pady=(0, 6))
        self._element_cb.bind("<<ComboboxSelected>>", self._on_element_selected)

        # Параметр
        tk.Label(panel, text="Параметр:", font=("Arial", 9)).pack(anchor="w")
        self._param_var = tk.StringVar()
        self._param_cb = ttk.Combobox(panel, textvariable=self._param_var,
                                       state="readonly", width=14)
        self._param_cb.pack(fill=tk.X, pady=(0, 6))

        # Кнопка применить
        tk.Button(panel, text="Показать таблицу",
                  font=("Arial", 9), command=self._on_show_table,
                  bg="#0ea5e9", fg="white", relief="flat",
                  padx=6, pady=3).pack(fill=tk.X, pady=(4, 0))

        tk.Button(panel, text="📊  График",
                  font=("Arial", 9), command=self._on_plot,
                  bg="#7c3aed", fg="white", relief="flat",
                  padx=6, pady=3).pack(fill=tk.X, pady=(4, 0))

        tk.Button(panel, text="💾  Экспорт CSV",
                  font=("Arial", 9), command=self._on_export_csv,
                  bg="#059669", fg="white", relief="flat",
                  padx=6, pady=3).pack(fill=tk.X, pady=(4, 0))

        # Разделитель
        ttk.Separator(panel, orient="horizontal").pack(fill=tk.X, pady=8)

        # Кнопка "сводная матрица по элементу"
        tk.Label(panel, text="Сводная матрица\nпо элементу:",
                 font=("Arial", 9)).pack(anchor="w")
        tk.Button(panel, text="Все параметры →",
                  font=("Arial", 9), command=self._on_show_element_matrix,
                  bg="#d97706", fg="white", relief="flat",
                  padx=6, pady=3).pack(fill=tk.X, pady=(4, 0))

    # ── Таблица ───────────────────────────────────────────────────────────────

    def _build_table_panel(self, parent: tk.Frame):
        frame = tk.Frame(parent)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # Treeview + скроллбары
        self._tree = ttk.Treeview(frame, show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # Placeholder
        self._show_placeholder()

    # ── Нижние кнопки ────────────────────────────────────────────────────────

    def _build_action_panel(self):
        bottom = tk.Frame(self, pady=4)
        bottom.grid(row=3, column=0, sticky="ew", padx=8)

        self._summary_var = tk.StringVar(value="")
        tk.Label(bottom, textvariable=self._summary_var,
                 font=("Courier", 9), fg="#444", justify="left").pack(side=tk.LEFT)

    # ═══════════════════════════════════════════════════════════════════════════
    #  Обработчики событий
    # ═══════════════════════════════════════════════════════════════════════════

    def _on_run(self):
        """Выбор файла и запуск расчёта в отдельном потоке."""
        filepath = filedialog.askopenfilename(
            parent=self,
            title="Выберите файл гидравлической модели",
            filetypes=[
                ("Все форматы EPANET", "*.inp *.net *.epanet"),
                ("INP файлы", "*.inp"),
                ("NET файлы", "*.net"),
                ("EPANET архивы", "*.epanet"),
                ("Все файлы", "*.*"),
            ],
        )
        if not filepath:
            return

        self._current_file = filepath
        self._file_label.config(text=filepath)
        self._set_status("Инициализация…", 0)
        self._results = None
        self._summary_var.set("")
        self._show_placeholder()

        # Запуск в потоке, чтобы не блокировать UI
        thread = threading.Thread(target=self._run_simulation, daemon=True)
        thread.start()

    def _run_simulation(self):
        """Выполняется в фоновом потоке."""
        def progress(msg: str, pct: int):
            # Обновление UI только из главного потока через after()
            self.after(0, lambda: self._set_status(msg, pct))

        try:
            runner = SimulationRunner(self._current_file, progress_cb=progress)
            results = runner.run()
            # Возврат в главный поток
            self.after(0, lambda: self._on_simulation_done(results))
        except ImportError as exc:
            self.after(0, lambda: self._on_simulation_error(str(exc)))
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            self.after(0, lambda: self._on_simulation_error(tb))

    def _on_simulation_done(self, results: SimulationResults):
        self._results = results
        self._set_status(
            f"✓ Расчёт завершён: {len(results.time_steps)} шагов, "
            f"{len(results.node_names)} узлов, {len(results.link_names)} звеньев.",
            100,
        )
        self._summary_var.set(results.summary())
        self._populate_filter_combos()
        self._on_show_table()   # показать таблицу сразу

    def _on_simulation_error(self, error_text: str):
        self._set_status("❌ Ошибка расчёта.", 0)
        messagebox.showerror(
            "Ошибка симуляции",
            error_text[:2000],   # обрезаем для окна
            parent=self,
        )

    def _on_type_changed(self, _event=None):
        """Переключение между узлами и звеньями — обновляем список элементов."""
        if not self._results:
            return
        self._populate_element_combo()
        self._populate_param_combo()

    def _on_element_selected(self, _event=None):
        """При смене элемента подсказать доступные параметры."""
        self._populate_param_combo()

    def _on_show_table(self):
        """Показать матрицу параметра для выбранного элемента."""
        if not self._results:
            messagebox.showinfo("Нет данных", "Сначала запустите расчёт.", parent=self)
            return

        param_label = self._param_var.get()
        param_key = self._label_to_key(param_label)
        elem = self._element_var.get()

        if not param_key or not elem:
            messagebox.showinfo("Выберите параметры",
                                "Укажите элемент и параметр.", parent=self)
            return

        # DataFrame: index=время_часы, один столбец
        try:
            is_node = param_key in self._results.node_results
            if is_node:
                series = self._results.get_node_series(param_key, elem)
            else:
                series = self._results.get_link_series(param_key, elem)
        except KeyError as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
            return

        import pandas as pd
        df = series.to_frame(name=ALL_PARAM_LABELS.get(param_key, param_key))
        df.index = [f"{t:.2f}" for t in df.index]
        df.index.name = self._COL_TIME
        self._render_table(df.reset_index())

    def _on_show_element_matrix(self):
        """Сводная матрица всех параметров для элемента."""
        if not self._results:
            messagebox.showinfo("Нет данных", "Сначала запустите расчёт.", parent=self)
            return
        elem = self._element_var.get()
        if not elem:
            messagebox.showinfo("Выберите элемент", "Укажите элемент.", parent=self)
            return
        try:
            df = self._results.get_matrix_for_element(elem)
        except KeyError as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
            return

        df.index = [f"{t:.2f}" for t in df.index]
        self._render_table(df.reset_index())

    def _on_plot(self):
        """Открыть окно matplotlib с временны́м графиком."""
        if not self._results:
            messagebox.showinfo("Нет данных", "Сначала запустите расчёт.", parent=self)
            return

        param_label = self._param_var.get()
        param_key = self._label_to_key(param_label)
        elem = self._element_var.get()

        if not param_key or not elem:
            messagebox.showinfo("Выберите параметры",
                                "Укажите элемент и параметр для графика.", parent=self)
            return

        try:
            is_node = param_key in self._results.node_results
            if is_node:
                series = self._results.get_node_series(param_key, elem)
            else:
                series = self._results.get_link_series(param_key, elem)
        except KeyError as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
            return

        self._show_plot_window(
            x=list(series.index),
            y=list(series.values),
            xlabel="Время, ч",
            ylabel=ALL_PARAM_LABELS.get(param_key, param_key),
            title=f"{elem}  —  {ALL_PARAM_LABELS.get(param_key, param_key)}",
        )

    def _on_export_csv(self):
        """Экспорт текущего вида таблицы в CSV."""
        if not self._results:
            messagebox.showinfo("Нет данных", "Сначала запустите расчёт.", parent=self)
            return

        elem = self._element_var.get()
        if not elem:
            messagebox.showinfo("Выберите элемент", "Укажите элемент.", parent=self)
            return

        try:
            df = self._results.get_matrix_for_element(elem)
        except KeyError as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
            return

        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Сохранить результаты как CSV",
            defaultextension=".csv",
            initialfile=f"{elem}_results.csv",
            filetypes=[("CSV файлы", "*.csv"), ("Все файлы", "*.*")],
        )
        if not save_path:
            return

        try:
            df.index.name = "Время, ч"
            df.to_csv(save_path, encoding="utf-8-sig", float_format="%.4f")
            messagebox.showinfo("Готово", f"Файл сохранён:\n{save_path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Ошибка записи", str(exc), parent=self)

    # ═══════════════════════════════════════════════════════════════════════════
    #  Вспомогательные методы
    # ═══════════════════════════════════════════════════════════════════════════

    def _set_status(self, message: str, percent: int):
        self._status_var.set(message)
        self._progress["value"] = max(0, min(100, percent))
        self.update_idletasks()

    def _show_placeholder(self):
        """Очищает таблицу и показывает заглушку."""
        tree = self._tree
        for col in tree["columns"]:
            tree.heading(col, text="")
        tree.delete(*tree.get_children())
        tree["columns"] = ("info",)
        tree.heading("info", text="Результаты расчёта появятся здесь")
        tree.column("info", width=500)
        tree.insert("", "end", values=("Выберите файл и нажмите «Запустить расчёт»",))

    def _render_table(self, df):
        """Отображает pandas DataFrame в Treeview."""
        tree = self._tree
        tree.delete(*tree.get_children())

        cols = list(df.columns)
        if len(cols) > self._MAX_COLS:
            cols = cols[:self._MAX_COLS]

        tree["columns"] = cols
        tree["show"] = "headings"

        for col in cols:
            tree.heading(col, text=str(col))
            tree.column(col, width=self._TREE_WIDTH, anchor="center", minwidth=60)

        # Первый столбец — время — чуть шире
        tree.column(cols[0], width=90, anchor="center")

        for _, row in df.iterrows():
            values = []
            for col in cols:
                val = row[col]
                try:
                    values.append(f"{float(val):.3f}")
                except (ValueError, TypeError):
                    values.append(str(val))
            tree.insert("", "end", values=values)

    def _populate_filter_combos(self):
        if not self._results:
            return
        self._populate_element_combo()
        self._populate_param_combo()

    def _populate_element_combo(self):
        if not self._results:
            return
        is_nodes = self._elem_type_var.get() == "Узлы"
        names = self._results.node_names if is_nodes else self._results.link_names
        self._element_cb["values"] = names
        if names:
            self._element_cb.set(names[0])

    def _populate_param_combo(self):
        if not self._results:
            return
        is_nodes = self._elem_type_var.get() == "Узлы"
        if is_nodes:
            keys = self._results.node_params
            labels = [NODE_PARAM_LABELS.get(k, k) for k in keys]
        else:
            keys = self._results.link_params
            labels = [LINK_PARAM_LABELS.get(k, k) for k in keys]

        self._param_cb["values"] = labels
        if labels:
            self._param_cb.set(labels[0])

    def _label_to_key(self, label: str) -> str:
        """Обратное преобразование: русская метка → ключ параметра."""
        reverse = {v: k for k, v in ALL_PARAM_LABELS.items()}
        return reverse.get(label, label)

    def _show_plot_window(
        self,
        x: list,
        y: list,
        xlabel: str,
        ylabel: str,
        title: str,
    ):
        """Открывает окно Toplevel с встроенным matplotlib-графиком."""
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from matplotlib.figure import Figure
        except ImportError:
            messagebox.showerror(
                "matplotlib не установлен",
                "Установите matplotlib:\n  pip install matplotlib",
                parent=self,
            )
            return

        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("900x550")
        win.resizable(True, True)

        fig = Figure(figsize=(9, 5), dpi=100)
        ax = fig.add_subplot(111)

        ax.plot(x, y, color="#2563eb", linewidth=1.8, marker="o",
                markersize=3, markerfacecolor="#1d4ed8")
        ax.set_xlabel(xlabel, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.grid(True, linestyle="--", alpha=0.5)
        ax.fill_between(x, y, alpha=0.08, color="#2563eb")
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()

        toolbar = NavigationToolbar2Tk(canvas, win)
        toolbar.update()

        toolbar.pack(side=tk.TOP, fill=tk.X)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Диалог сравнения нескольких элементов (открывается из контекстного меню)
# ─────────────────────────────────────────────────────────────────────────────

class MultiPlotDialog(tk.Toplevel):
    """
    Окно для сравнительного графика нескольких элементов по одному параметру.
    Вызывается из меню или кнопки в SimulationTab.
    """

    def __init__(self, parent, results: SimulationResults):
        super().__init__(parent)
        self.title("Сравнительный график")
        self.geometry("1000x620")
        self.resizable(True, True)
        self._results = results
        self._build_ui()

    def _build_ui(self):
        top = tk.Frame(self, pady=6)
        top.pack(fill=tk.X, padx=8)

        # Параметр
        tk.Label(top, text="Параметр:", font=("Arial", 10)).pack(side=tk.LEFT)
        self._param_var = tk.StringVar()
        all_labels = [NODE_PARAM_LABELS.get(k, k) for k in self._results.node_params] + \
                     [LINK_PARAM_LABELS.get(k, k) for k in self._results.link_params]
        param_cb = ttk.Combobox(top, textvariable=self._param_var,
                                 values=all_labels, state="readonly", width=20)
        param_cb.pack(side=tk.LEFT, padx=6)
        if all_labels:
            param_cb.set(all_labels[0])

        # Кнопка
        tk.Button(top, text="Построить", command=self._plot,
                  bg="#7c3aed", fg="white", relief="flat",
                  padx=8, pady=4).pack(side=tk.LEFT, padx=6)

        # Список элементов
        tk.Label(top, text="Элементы (Ctrl+клик):", font=("Arial", 10)).pack(
            side=tk.LEFT, padx=(16, 0))

        self._listbox = tk.Listbox(top, selectmode="extended", width=18, height=5,
                                   exportselection=False)
        self._listbox.pack(side=tk.LEFT, padx=6)

        all_names = self._results.node_names + self._results.link_names
        for name in all_names:
            self._listbox.insert(tk.END, name)
        if all_names:
            self._listbox.select_set(0, min(4, len(all_names) - 1))

        # Canvas для графика
        self._canvas_frame = tk.Frame(self)
        self._canvas_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    def _plot(self):
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from matplotlib.figure import Figure
        except ImportError:
            messagebox.showerror("Ошибка", "Установите matplotlib: pip install matplotlib")
            return

        # Убираем старый canvas
        for w in self._canvas_frame.winfo_children():
            w.destroy()

        param_label = self._param_var.get()
        reverse = {v: k for k, v in ALL_PARAM_LABELS.items()}
        param_key = reverse.get(param_label, param_label)

        selected_indices = self._listbox.curselection()
        all_names = self._results.node_names + self._results.link_names
        selected = [all_names[i] for i in selected_indices]
        if not selected:
            messagebox.showinfo("Ничего не выбрано", "Выберите элементы из списка.")
            return

        fig = Figure(figsize=(10, 5), dpi=100)
        ax = fig.add_subplot(111)

        colors = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed",
                  "#0891b2", "#be185d", "#1d4ed8", "#b45309", "#4ade80"]

        for i, elem_id in enumerate(selected[:10]):   # ограничение 10 кривых
            try:
                if param_key in self._results.node_results:
                    series = self._results.get_node_series(param_key, elem_id)
                else:
                    series = self._results.get_link_series(param_key, elem_id)
                ax.plot(list(series.index), list(series.values),
                        label=elem_id, color=colors[i % len(colors)],
                        linewidth=1.6)
            except KeyError:
                pass

        ax.set_xlabel("Время, ч", fontsize=10)
        ax.set_ylabel(ALL_PARAM_LABELS.get(param_key, param_key), fontsize=10)
        ax.set_title(f"Сравнение: {param_label}", fontsize=12, fontweight="bold")
        ax.legend(fontsize=8, loc="best")
        ax.grid(True, linestyle="--", alpha=0.5)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self._canvas_frame)
        canvas.draw()
        toolbar = NavigationToolbar2Tk(canvas, self._canvas_frame)
        toolbar.update()
        toolbar.pack(side=tk.TOP, fill=tk.X)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
