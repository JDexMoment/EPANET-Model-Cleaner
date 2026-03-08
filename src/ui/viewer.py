import tkinter as tk
import traceback
from typing import Dict, List, Tuple, Optional
from parser_factory import ParserFactory


class NetworkViewer:
    COLORS = {
        "junction": "#333333",
        "reservoir": "#1a5fb4",
        "tank": "#26a269",
        "pipe": "#555555",
        "pump": "#e01b24",
        "valve": "#ff7800",
        "background": "#ffffff",
    }

    SIZES = {
        "junction_radius": 3,
        "reservoir_size": 8,
        "tank_size": 7,
        "pipe_width": 1,
        "pump_width": 2,
        "valve_width": 2,
    }

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.sections: Dict[str, List[str]] = {}
        self.order: List[str] = []

        self.coordinates: Dict[str, Tuple[float, float]] = {}
        self.vertices: Dict[str, List[Tuple[float, float]]] = {}
        self.junctions: set = set()
        self.reservoirs: set = set()
        self.tanks: set = set()

        self.pipes: List[dict] = []
        self.pumps: List[dict] = []
        self.valves: List[dict] = []

        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.drag_start = None

    def show(self):
        try:
            parser = ParserFactory.create(self.filepath)
            self.sections, self.order = parser.read()
            self._parse_coordinates()
            self._parse_vertices()
            self._parse_nodes()
            self._parse_links()
        except Exception as e:
            err_msg = traceback.format_exc()
            self._show_error(f"ОШИБКА:\n{err_msg}")
            return

        if not self.coordinates:
            self._show_error("В файле нет секции [COORDINATES].\nНевозможно построить схему.")
            return

        self._create_window()

    def _show_error(self, message: str):
        err_win = tk.Toplevel()
        err_win.title("Критическая ошибка")
        err_win.geometry("600x400")
        text = tk.Text(err_win, font=("Courier", 9))
        text.pack(fill=tk.BOTH, expand=True)
        text.insert(tk.END, message)
        text.config(state=tk.DISABLED)

    def _parse_line_fields(self, line: str) -> List[str]:
        if ';' in line:
            line = line[:line.index(';')]
        return line.strip().split()

    def _parse_coordinates(self):
        for line in self.sections.get("[COORDINATES]", []):
            fields = self._parse_line_fields(line)
            if len(fields) >= 3:
                try:
                    self.coordinates[fields[0]] = (float(fields[1]), float(fields[2]))
                except ValueError:
                    pass

    def _parse_vertices(self):
        for line in self.sections.get("[VERTICES]", []):
            fields = self._parse_line_fields(line)
            if len(fields) >= 3:
                try:
                    link_id = fields[0]
                    if link_id not in self.vertices:
                        self.vertices[link_id] = []
                    self.vertices[link_id].append((float(fields[1]), float(fields[2])))
                except ValueError:
                    pass

    def _parse_nodes(self):
        for line in self.sections.get("[JUNCTIONS]", []):
            fields = self._parse_line_fields(line)
            if fields: self.junctions.add(fields[0])

        for line in self.sections.get("[RESERVOIRS]", []):
            fields = self._parse_line_fields(line)
            if fields: self.reservoirs.add(fields[0])

        for line in self.sections.get("[TANKS]", []):
            fields = self._parse_line_fields(line)
            if fields: self.tanks.add(fields[0])

    def _parse_links(self):
        for line in self.sections.get("[PIPES]", []):
            fields = self._parse_line_fields(line)
            if len(fields) >= 3:
                self.pipes.append({'id': fields[0], 'n1': fields[1], 'n2': fields[2]})

        for line in self.sections.get("[PUMPS]", []):
            fields = self._parse_line_fields(line)
            if len(fields) >= 3:
                self.pumps.append({'id': fields[0], 'n1': fields[1], 'n2': fields[2]})

        for line in self.sections.get("[VALVES]", []):
            fields = self._parse_line_fields(line)
            if len(fields) >= 3:
                self.valves.append({'id': fields[0], 'n1': fields[1], 'n2': fields[2]})

    def _create_window(self):
        self.win = tk.Toplevel()
        self.win.title(f"Схема сети — {self.filepath}")
        self.win.geometry("1100x800")

        info_frame = tk.Frame(self.win, bg="#f0f0f0", height=40)
        info_frame.pack(fill=tk.X)
        info_frame.pack_propagate(False)

        stats_text = (
            f"Узлы: {len(self.junctions)}   "
            f"Резервуары: {len(self.reservoirs)}   "
            f"Ёмкости: {len(self.tanks)}   "
            f"Трубы: {len(self.pipes)}   "
            f"Насосы: {len(self.pumps)}   "
            f"Задвижки: {len(self.valves)}"
        )
        tk.Label(info_frame, text=stats_text, font=("Arial", 10), bg="#f0f0f0").pack(side=tk.LEFT, padx=10, pady=5)

        btn_frame = tk.Frame(info_frame, bg="#f0f0f0")
        btn_frame.pack(side=tk.RIGHT, padx=10)

        tk.Button(btn_frame, text="Сброс", command=self._reset_view).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="+", width=3, command=lambda: self._zoom(1.3)).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="−", width=3, command=lambda: self._zoom(0.7)).pack(side=tk.LEFT, padx=2)

        self.canvas = tk.Canvas(self.win, bg=self.COLORS["background"], highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self._zoom(1.2))
        self.canvas.bind("<Button-5>", lambda e: self._zoom(0.8))
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)

        self._draw_legend()
        self.win.after(50, self._fit_to_screen)

    def _world_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        sx = (x - self.offset_x) * self.scale
        sy = self.canvas.winfo_height() - (y - self.offset_y) * self.scale
        return sx, sy

    def _fit_to_screen(self):
        if not self.coordinates: return

        xs = [c[0] for c in self.coordinates.values()]
        ys = [c[1] for c in self.coordinates.values()]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        data_width = max_x - min_x or 1
        data_height = max_y - min_y or 1

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width < 10 or canvas_height < 10:
            self.win.after(100, self._fit_to_screen)
            return

        margin = 40
        scale_x = (canvas_width - 2 * margin) / data_width
        scale_y = (canvas_height - 2 * margin) / data_height
        self.scale = min(scale_x, scale_y)

        self.offset_x = (min_x + max_x) / 2 - canvas_width / (2 * self.scale)
        self.offset_y = (min_y + max_y) / 2 - canvas_height / (2 * self.scale)
        self._redraw()

    def _reset_view(self):
        self._fit_to_screen()

    def _redraw(self):
        self.canvas.delete("network")
        self._draw_links(self.pipes, self.COLORS["pipe"], self.SIZES["pipe_width"], "pipe")
        self._draw_links(self.pumps, self.COLORS["pump"], self.SIZES["pump_width"], "pump")
        self._draw_links(self.valves, self.COLORS["valve"], self.SIZES["valve_width"], "valve")
        self._draw_junctions()
        self._draw_reservoirs()
        self._draw_tanks()

    def _draw_links(self, links, color, width, link_type):
        for link in links:
            link_id = link['id']
            node1 = link['n1']
            node2 = link['n2']

            if node1 not in self.coordinates or node2 not in self.coordinates:
                continue

            x1, y1 = self.coordinates[node1]
            x2, y2 = self.coordinates[node2]

            points = [(x1, y1)]
            if link_id in self.vertices:
                points.extend(self.vertices[link_id])
            points.append((x2, y2))

            for i in range(len(points) - 1):
                sx1, sy1 = self._world_to_screen(points[i][0], points[i][1])
                sx2, sy2 = self._world_to_screen(points[i + 1][0], points[i + 1][1])
                self.canvas.create_line(sx1, sy1, sx2, sy2, fill=color, width=width, tags="network")

            if link_type in ("pump", "valve"):
                mid_idx = len(points) // 2
                if len(points) % 2 == 0:
                    mx = (points[mid_idx - 1][0] + points[mid_idx][0]) / 2
                    my = (points[mid_idx - 1][1] + points[mid_idx][1]) / 2
                else:
                    mx, my = points[mid_idx][0], points[mid_idx][1]

                smx, smy = self._world_to_screen(mx, my)
                r = 5
                if link_type == "pump":
                    self.canvas.create_oval(smx - r, smy - r, smx + r, smy + r, fill=color, outline="white",
                                            tags="network")
                else:
                    self.canvas.create_polygon(smx, smy - r, smx + r, smy, smx, smy + r, smx - r, smy, fill=color,
                                               outline="white", tags="network")

    def _draw_junctions(self):
        r = self.SIZES["junction_radius"]
        for node_id in self.junctions:
            if node_id in self.coordinates:
                sx, sy = self._world_to_screen(self.coordinates[node_id][0], self.coordinates[node_id][1])
                self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill=self.COLORS["junction"],
                                        outline=self.COLORS["junction"], tags="network")

    def _draw_reservoirs(self):
        s = self.SIZES["reservoir_size"]
        for node_id in self.reservoirs:
            if node_id in self.coordinates:
                sx, sy = self._world_to_screen(self.coordinates[node_id][0], self.coordinates[node_id][1])
                self.canvas.create_rectangle(sx - s, sy - s, sx + s, sy + s, fill=self.COLORS["reservoir"],
                                             outline="white", width=2, tags="network")

    def _draw_tanks(self):
        s = self.SIZES["tank_size"]
        for node_id in self.tanks:
            if node_id in self.coordinates:
                sx, sy = self._world_to_screen(self.coordinates[node_id][0], self.coordinates[node_id][1])
                self.canvas.create_oval(sx - s, sy - s, sx + s, sy + s, fill=self.COLORS["tank"], outline="white",
                                        width=2, tags="network")

    def _draw_legend(self):
        items = [
            ("●", self.COLORS["junction"], "Узел"),
            ("■", self.COLORS["reservoir"], "Резервуар"),
            ("●", self.COLORS["tank"], "Ёмкость"),
            ("—", self.COLORS["pipe"], "Труба"),
            ("—", self.COLORS["pump"], "Насос"),
            ("—", self.COLORS["valve"], "Задвижка"),
        ]
        for i, item in enumerate(items):
            y = 15 + i * 20
            self.canvas.create_text(15, y, text=item[0], fill=item[1], font=("Arial", 12, "bold"), anchor="w",
                                    tags="legend")
            self.canvas.create_text(35, y, text=item[2], fill="#333", font=("Arial", 9), anchor="w", tags="legend")

    def _on_resize(self, event):
        self._redraw()

    def _on_mousewheel(self, event):
        self._zoom(1.2 if event.delta > 0 else 0.8, event.x, event.y)

    def _zoom(self, factor, center_x=None, center_y=None):
        cx = center_x if center_x is not None else self.canvas.winfo_width() / 2
        cy = center_y if center_y is not None else self.canvas.winfo_height() / 2
        wx = cx / self.scale + self.offset_x
        wy = (self.canvas.winfo_height() - cy) / self.scale + self.offset_y
        self.scale *= factor
        self.offset_x = wx - cx / self.scale
        self.offset_y = wy - (self.canvas.winfo_height() - cy) / self.scale
        self._redraw()

    def _on_drag_start(self, event):
        self.drag_start = (event.x, event.y)

    def _on_drag_motion(self, event):
        if self.drag_start:
            self.offset_x -= (event.x - self.drag_start[0]) / self.scale
            self.offset_y += (event.y - self.drag_start[1]) / self.scale
            self.drag_start = (event.x, event.y)
            self._redraw()

    def _on_drag_end(self, event):
        self.drag_start = None