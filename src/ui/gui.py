"""
AppGUI — главное окно приложения EPANET Model Cleaner & Simulator.

Структура
---------
* ttk.Notebook с двумя вкладками:
    1. «Очистка / Конвертация» — оригинальный функционал ETL.
    2. «Гидравлический расчёт» — SimulationTab (src/ui/simulation_tab.py).
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Dict

from src.extract.factory import ParserFactory
from src.transform.cleaner import InpCleaner
from src.load.writer import ModelWriter
from src.ui.viewer import NetworkViewer
from src.ui.simulation_tab import SimulationTab, MultiPlotDialog


class AppGUI:
    """Главное окно приложения."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EPANET Model Cleaner & Simulator")
        self.root.geometry("1050x750")
        self.root.resizable(True, True)
        self._temp_files = []
        self._build_ui()

    # ═══════════════════════════════════════════════════════════════════════════
    #  Построение UI
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Заголовок ─────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg="#1e3a5f", pady=8)
        header.pack(fill=tk.X)

        tk.Label(
            header,
            text="💧  EPANET Model Cleaner & Simulator",
            font=("Arial", 15, "bold"),
            bg="#1e3a5f", fg="white",
        ).pack(side=tk.LEFT, padx=12)

        tk.Label(
            header,
            text="ETL + Гидравлический расчёт | INP · NET · EPANET",
            font=("Arial", 9),
            bg="#1e3a5f", fg="#93c5fd",
        ).pack(side=tk.LEFT)

        # ── Notebook ──────────────────────────────────────────────────────────
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Arial", 11), padding=[10, 4])

        self._notebook = ttk.Notebook(self.root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Вкладка 1: Очистка / Конвертация
        self._clean_frame = tk.Frame(self._notebook)
        self._notebook.add(self._clean_frame, text="🔧  Очистка / Конвертация")
        self._build_clean_tab(self._clean_frame)

        # Вкладка 2: Гидравлический расчёт
        self._sim_frame = SimulationTab(self._notebook)
        self._notebook.add(self._sim_frame, text="📊  Гидравлический расчёт")

        # Вкладка 3: Сравнительный анализ (открывается через кнопку)
        # — запускается как диалоговое окно, не как третья вкладка

        # ── Меню ──────────────────────────────────────────────────────────────
        self._build_menu()

    # ─── Вкладка «Очистка» ────────────────────────────────────────────────────

    def _build_clean_tab(self, parent: tk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Кнопки
        btn_frame = tk.Frame(parent, pady=8)
        btn_frame.grid(row=0, column=0, sticky="ew", padx=8)

        buttons = [
            ("🧹  Очистить файл модели",         "#2563eb", self.on_clean),
            ("🗺️  Открыть и просмотреть схему",  "#059669", self.on_view),
            ("📊  Сравнительный анализ",          "#7c3aed", self.on_multi_plot),
            ("❌  Выход",                          "#dc2626", self.on_exit),
        ]

        for text, color, cmd in buttons:
            tk.Button(
                btn_frame, text=text, font=("Arial", 11),
                width=30, height=1, command=cmd,
                bg=color, fg="white", activebackground=color,
                activeforeground="white", relief="flat", padx=8, pady=6,
            ).pack(side=tk.LEFT, padx=6)

        # Лог
        log_outer = tk.Frame(parent)
        log_outer.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        log_outer.columnconfigure(0, weight=1)
        log_outer.rowconfigure(0, weight=1)

        v_scroll = tk.Scrollbar(log_outer)
        v_scroll.grid(row=0, column=1, sticky="ns")

        self.output_text = tk.Text(
            log_outer, font=("Courier", 10), state=tk.DISABLED,
            wrap=tk.NONE, yscrollcommand=v_scroll.set,
            bg="#f8fafc", fg="#0f172a",
        )
        self.output_text.grid(row=0, column=0, sticky="nsew")
        v_scroll.config(command=self.output_text.yview)

        h_scroll = tk.Scrollbar(parent, orient=tk.HORIZONTAL,
                                 command=self.output_text.xview)
        h_scroll.grid(row=2, column=0, sticky="ew", padx=8)
        self.output_text.config(xscrollcommand=h_scroll.set)

    # ─── Меню ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Очистить файл…",          command=self.on_clean)
        file_menu.add_command(label="Просмотреть схему…",       command=self.on_view)
        file_menu.add_separator()
        file_menu.add_command(label="Выход",                    command=self.on_exit)
        menubar.add_cascade(label="Файл", menu=file_menu)

        sim_menu = tk.Menu(menubar, tearoff=0)
        sim_menu.add_command(
            label="Гидравлический расчёт…",
            command=lambda: self._notebook.select(self._sim_frame),
        )
        sim_menu.add_command(
            label="Сравнительный анализ…",
            command=self.on_multi_plot,
        )
        menubar.add_cascade(label="Расчёт", menu=sim_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self._show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)

        self.root.config(menu=menubar)

    # ═══════════════════════════════════════════════════════════════════════════
    #  Лог (вкладка «Очистка»)
    # ═══════════════════════════════════════════════════════════════════════════

    def log(self, message: str):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.output_text.config(state=tk.DISABLED)
        self.root.update()

    def clear_log(self):
        self.output_text.config(state=tk.NORMAL)
        self.output_text.delete("1.0", tk.END)
        self.output_text.config(state=tk.DISABLED)

    # ═══════════════════════════════════════════════════════════════════════════
    #  Обработчики кнопок
    # ═══════════════════════════════════════════════════════════════════════════

    def select_file(self) -> str:
        return filedialog.askopenfilename(
            parent=self.root,
            title="Выберите файл гидравлической модели",
            filetypes=[
                ("Все форматы EPANET", "*.inp *.net *.epanet"),
                ("INP файлы", "*.inp"),
                ("NET файлы", "*.net"),
                ("EPANET файлы", "*.epanet"),
                ("Все файлы", "*.*"),
            ],
        )

    def select_save_path(self, default_name: str) -> str:
        return filedialog.asksaveasfilename(
            parent=self.root,
            title="Сохранить очищенный файл как…",
            initialfile=default_name,
            defaultextension=".inp",
            filetypes=[
                ("INP файлы (Текст)", "*.inp"),
                ("EPANET файлы (Архив)", "*.epanet"),
                ("NET файлы (Текст)", "*.net"),
                ("Все файлы", "*.*"),
            ],
        )

    def on_view(self):
        filepath = self.select_file()
        if not filepath:
            return

        self._notebook.select(self._clean_frame)
        self.clear_log()
        self.log(f"Открытие схемы: {Path(filepath).name}")

        if not ParserFactory.is_supported(filepath):
            self.log("[Ошибка] Формат не поддерживается.")
            return

        self.log("Схема отображается в отдельном окне…")
        try:
            viewer = NetworkViewer(filepath)
            viewer.show()
        except Exception as e:
            self.log(f"[Ошибка визуализации] {e}")

    def on_clean(self):
        input_path = self.select_file()
        if not input_path:
            return

        self._notebook.select(self._clean_frame)
        self.clear_log()
        input_file = Path(input_path)

        if not ParserFactory.is_supported(input_path):
            self.log("[Ошибка] Формат не поддерживается.")
            return

        # ── EXTRACT ──────────────────────────────────────────────────────────
        self.log(f"[Extract] Чтение: {input_file.name}")

        try:
            parser = ParserFactory.create(input_path)
            sections, order = parser.read()
            preamble = parser.get_preamble()
        except Exception as e:
            self.log(f"[Ошибка чтения] {e}")
            return

        if not order:
            self.log("[Ошибка] Не удалось прочитать секции.")
            return

        original_sections = set(order)
        self.log(f"  Прочитано секций: {len(order)}")
        self._print_element_stats(sections)

        # ── TRANSFORM ────────────────────────────────────────────────────────
        sections_to_remove = InpCleaner.DEFAULT_REMOVE_SECTIONS
        self.log(f"\n[Transform] Очистка…")

        cleaner = InpCleaner(sections, order)
        clean_sections, clean_order = cleaner.clean(
            remove_comments=True,
            drop_empty_lines=True,
            remove_sections=sections_to_remove,
            preserve_title_comments=True,
        )

        remaining_sections = set(clean_order)
        actually_removed = original_sections - remaining_sections

        self.log(f"\n  {'─' * 50}")
        self.log(f"  ОТЧЁТ ПО УДАЛЁННЫМ СЕКЦИЯМ:")
        self.log(f"  {'─' * 50}")

        if actually_removed:
            for i, sec_name in enumerate(sorted(actually_removed), 1):
                self.log(f"    {i}. {sec_name}")
            self.log(f"\n  Итого удалено: {len(actually_removed)}")
        else:
            self.log(f"    Ни одна секция не была удалена.")

        self.log(f"  Осталось секций: {len(clean_order)}")

        # ── LOAD ─────────────────────────────────────────────────────────────
        default_name = f"{input_file.stem}_clean.inp"
        output_path = self.select_save_path(default_name)

        if not output_path:
            self.log("\n[Отмена] Сохранение отменено.")
            return

        if output_path.lower().endswith('.net'):
            self.log("\n[Внимание] Файл будет сохранён как текстовый .NET. "
                     "Если программа EPANET 2.0 его не откроет, пересохраните в .INP.")

        try:
            writer = ModelWriter(output_path)
            writer.write(clean_sections, clean_order, preamble)
        except Exception as e:
            self.log(f"[Ошибка записи] {e}")
            return

        self.log(f"\n{'=' * 70}")
        self.log(f"[Готово] Файл сохранён: {output_path}")
        self.log(f"{'=' * 70}")

    def on_multi_plot(self):
        """Открыть диалог сравнительного графика."""
        results = self._sim_frame._results
        if not results:
            # Переключаемся на вкладку расчёта с подсказкой
            self._notebook.select(self._sim_frame)
            messagebox.showinfo(
                "Нет данных расчёта",
                "Сначала выполните гидравлический расчёт на вкладке\n"
                "«Гидравлический расчёт».",
                parent=self.root,
            )
            return
        MultiPlotDialog(self.root, results)

    def _show_about(self):
        about_win = tk.Toplevel(self.root)
        about_win.title("О программе")
        about_win.geometry("480x280")
        about_win.resizable(False, False)

        tk.Label(
            about_win,
            text="💧 EPANET Model Cleaner & Simulator",
            font=("Arial", 14, "bold"), pady=12,
        ).pack()

        info = (
            "Профессиональная утилита для работы с гидравлическими\n"
            "моделями EPANET.\n\n"
            "Возможности:\n"
            "  • Очистка и конвертация файлов INP / NET / EPANET\n"
            "  • Визуализация гидравлического графа\n"
            "  • Гидравлический расчёт (WNTR / EPANET)\n"
            "  • Матрица результатов: давление, напор, расход…\n"
            "  • Построение графиков и экспорт CSV\n\n"
            "Архитектура: ETL (Extract → Transform → Load)"
        )
        tk.Label(about_win, text=info, font=("Arial", 10),
                 justify="left").pack(padx=20)

    def _print_element_stats(self, sections: Dict):
        element_sections = {
            "[JUNCTIONS]":  "Узлы",
            "[RESERVOIRS]": "Резервуары",
            "[TANKS]":      "Ёмкости",
            "[PIPES]":      "Трубы",
            "[PUMPS]":      "Насосы",
            "[VALVES]":     "Задвижки",
            "[COORDINATES]": "Координаты",
        }

        self.log(f"\n  {'─' * 50}")
        self.log(f"  ЭЛЕМЕНТЫ СЕТИ:")
        self.log(f"  {'─' * 50}")

        for sec_name, label in element_sections.items():
            if sec_name in sections:
                count = len([line for line in sections[sec_name]
                             if line.strip() and not line.strip().startswith(';')])
                self.log(f"    {label}: {count}")

    def on_exit(self):
        for tmp_file in self._temp_files:
            try:
                if os.path.exists(tmp_file):
                    os.unlink(tmp_file)
            except Exception:
                pass
        self.root.quit()

    def run(self):
        self.root.mainloop()
