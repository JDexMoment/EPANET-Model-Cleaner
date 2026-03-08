import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from typing import Dict
import os

from src.extract.factory import ParserFactory
from src.transform.cleaner import InpCleaner
from src.load.writer import ModelWriter
from src.ui.viewer import NetworkViewer


class AppGUI:
    """Главное окно приложения."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EPANET Model Cleaner")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        self._temp_files = []
        self._build_ui()

    def _build_ui(self):
        tk.Label(
            self.root, text="EPANET Model Cleaner",
            font=("Arial", 16, "bold"), pady=10,
        ).pack()

        tk.Label(
            self.root, text="✓ Встроенный Python парсер активен (Поддержка: INP, NET, EPANET)",
            font=("Arial", 9), fg="green"
        ).pack()

        button_frame = tk.Frame(self.root, pady=10)
        button_frame.pack()

        buttons = [
            ("Очистить файл модели", self.on_clean),
            ("Открыть и просмотреть схему", self.on_view),
            ("Выход", self.on_exit),
        ]

        for text, command in buttons:
            btn = tk.Button(
                button_frame, text=text, font=("Arial", 12),
                width=30, height=2, command=command,
            )
            btn.pack(pady=5)

        text_frame = tk.Frame(self.root)
        text_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        v_scrollbar = tk.Scrollbar(text_frame)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.output_text = tk.Text(
            text_frame, font=("Courier", 10), state=tk.DISABLED,
            wrap=tk.NONE, yscrollcommand=v_scrollbar.set,
        )
        self.output_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.config(command=self.output_text.yview)

        h_scrollbar = tk.Scrollbar(self.root, orient=tk.HORIZONTAL, command=self.output_text.xview)
        h_scrollbar.pack(fill=tk.X, padx=10)
        self.output_text.config(xscrollcommand=h_scrollbar.set)

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
        # Теперь можно сохранять в 3 разных форматах!
        return filedialog.asksaveasfilename(
            parent=self.root,
            title="Сохранить очищенный файл как...",
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

        self.clear_log()
        self.log(f"Открытие схемы: {Path(filepath).name}")

        if not ParserFactory.is_supported(filepath):
            self.log("[Ошибка] Формат не поддерживается.")
            return

        self.log("Схема отображается в отдельном окне...")
        try:
            viewer = NetworkViewer(filepath)
            viewer.show()
        except Exception as e:
            self.log(f"[Ошибка визуализации] {e}")

    def on_clean(self):
        input_path = self.select_file()
        if not input_path:
            return

        self.clear_log()
        input_file = Path(input_path)

        if not ParserFactory.is_supported(input_path):
            self.log("[Ошибка] Формат не поддерживается.")
            return

        # ── EXTRACT ──
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

        # ── TRANSFORM ──
        sections_to_remove = InpCleaner.DEFAULT_REMOVE_SECTIONS
        self.log(f"\n[Transform] Очистка...")

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

        # ── LOAD ──
        default_name = f"{input_file.stem}_clean.inp"
        output_path = self.select_save_path(default_name)

        if not output_path:
            self.log("\n[Отмена] Сохранение отменено.")
            return

        # Если пользователь выбрал расширение .net, предупредим его
        if output_path.lower().endswith('.net'):
            self.log("\n[Внимание] Файл будет сохранён как текстовый .NET. "
                     "Если программа EPANET 2.0 его не откроет, пересохраните его в .INP.")

        try:
            # ИСПОЛЬЗУЕМ НОВЫЙ ModelWriter
            writer = ModelWriter(output_path)
            writer.write(clean_sections, clean_order, preamble)
        except Exception as e:
            self.log(f"[Ошибка записи] {e}")
            return

        self.log(f"\n{'=' * 70}")
        self.log(f"[Готово] Файл сохранён: {output_path}")
        self.log(f"{'=' * 70}")

    def _print_element_stats(self, sections: Dict):
        element_sections = {
            "[JUNCTIONS]": "Узлы",
            "[RESERVOIRS]": "Резервуары",
            "[TANKS]": "Ёмкости",
            "[PIPES]": "Трубы",
            "[PUMPS]": "Насосы",
            "[VALVES]": "Задвижки",
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
            except:
                pass
        self.root.quit()

    def run(self):
        self.root.mainloop()