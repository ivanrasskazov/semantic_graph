import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.colorchooser as colorchooser
import json
import os
from config import DEFAULTS_DIR
from core.database import load_defaults_settings


class VizParamsWindow:
    def __init__(self, parent, db_path, apply_callback, save_to_defaults=False, max_graph_weight=100):
        self.parent = parent
        self.max_graph_weight = max_graph_weight
        self.db_path = db_path
        self.apply_callback = apply_callback
        self.save_to_defaults = save_to_defaults

        self.params_file = os.path.join(DEFAULTS_DIR, ".viz_params.json") if self.save_to_defaults else os.path.join(
            db_path, ".viz_params.json")

        # 🔹 ВОССТАНОВЛЕНО: Добавлены параметры разрежения узлов
        self.params = {
            "kw_conn": True, "center_type": "Общий вид", "center_node": "  ", "layout_type": "Сило-ориентированный",
            "node_colors": {"keyword": "#add8e6", "subject": "#90ee90", "faction": "#f08080"},
            "center_word_color": "#FFD700",
            "edge_colors": {"kw-kw": "#888888", "sub-fac": "#aa6666", "sub-kw": "#6688aa", "sub-sub": "#88aa88"},
            "font": {"size": 8, "color": "#000000", "weight": "normal"},
            "offsets": {"x": 0.05, "y": 0.05}, "styles": {},
            "smart_labels": False,
            "label_base_radius": 0.035,
            "label_radius_multiplier": 0.003,
            "min_mentions": 1,
            "max_mentions": 999999,
            "kw_min": 1, "kw_max": 999999,
            "sub_min": 1, "sub_max": 999999,
            "fac_min": 1, "fac_max": 999999,
            "spacing_mode": "fixed",
            "spacing_fixed": 0.6,
            "spacing_dynamic_base": 0.4,
            "spacing_dynamic_factor": 0.015
        }

        if os.path.exists(self.params_file):
            try:
                with open(self.params_file, 'r', encoding='utf-8') as f:
                    self.params.update(json.load(f))
            except:
                pass

        self.window = tk.Toplevel(parent)
        self.window.title("Параметры визуализации")
        self.window.geometry("750x650")
        self.window.transient(parent)
        self.window.grab_set()

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Вкладка 1: Основные ---
        tab_main = ttk.Frame(notebook)
        scroll_main = self._create_scrolled_area(tab_main)
        self._build_main_tab(scroll_main)
        notebook.add(tab_main, text="Основные")

        # --- Вкладка 2: Стилизация ---
        tab_style = ttk.Frame(notebook)
        scroll_style = self._create_scrolled_area(tab_style)
        self._build_style_tab(scroll_style)
        notebook.add(tab_style, text="Стилизация")

        # --- Вкладка 3: Стили ---
        tab_presets = ttk.Frame(notebook)
        scroll_presets = self._create_scrolled_area(tab_presets)
        self._build_presets_tab(scroll_presets)
        notebook.add(tab_presets, text="Стили")

        if not self.save_to_defaults:
            ttk.Button(self.window, text="Применить по умолчанию", command=self._apply_defaults_viz).pack(pady=5)

        btn_text = "Сохранить как параметры по умолчанию" if self.save_to_defaults else "Сохранить и закрыть"
        ttk.Button(self.window, text=btn_text, command=self._save_and_close).pack(pady=10)

    def _create_scrolled_area(self, parent):
        """Создаёт область с вертикальной прокруткой для вкладки"""
        canvas = tk.Canvas(parent, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        return scrollable_frame

    def _build_main_tab(self, container):
        self.var_kw = tk.BooleanVar(value=self.params.get("kw_conn", True))
        self._add_cb(container, "Взаимосвязь ключевых слов", self.var_kw, "Скрыть рёбра слово-слово.")

        ttk.Label(container, text="Структура графа:").pack(anchor=tk.W, padx=20, pady=(10, 2))
        self.layout_var = tk.StringVar(value=self.params.get("layout_type", "Сило-ориентированный"))
        ttk.Combobox(container, textvariable=self.layout_var, values=["Сило-ориентированный", "Круговой", "Кольцевой"],
                     state="readonly", width=35).pack(anchor=tk.W, padx=20)

        ttk.Label(container, text="Режим:").pack(anchor=tk.W, padx=20, pady=(10, 2))
        self.center_type_var = tk.StringVar(value=self.params.get("center_type", "Общий вид"))
        type_combo = ttk.Combobox(container, textvariable=self.center_type_var,
                                  values=["Общий вид", "Портрет фракции", "Портрет субъекта", "Портрет слова"],
                                  state="readonly", width=35)
        type_combo.pack(anchor=tk.W, padx=20)
        type_combo.bind("<<ComboboxSelected>>", self._update_node_dropdown)

        if self.save_to_defaults:
            type_combo.config(state="disabled")
            ttk.Label(container, text="Режим визуализации фиксирован для всех новых баз данных.",
                      foreground="gray", font=("tahoma", 8)).pack(anchor=tk.W, padx=20, pady=(0, 5))

        ttk.Label(container, text="Центральный узел:").pack(anchor=tk.W, padx=20, pady=(10, 2))
        self.node_select_var = tk.StringVar(value=self.params.get("center_node", "  "))
        self.node_combo = ttk.Combobox(container, textvariable=self.node_select_var, state="readonly", width=35)
        self.node_combo.pack(anchor=tk.W, padx=20)
        self._update_node_dropdown(None)

        # 🔹 ВОССТАНОВЛЕНО: Параметры разрежения узлов
        sep1 = ttk.Separator(container, orient="horizontal")
        sep1.pack(fill=tk.X, padx=20, pady=15)
        ttk.Label(container, text="Разрежение узлов (k):", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=20)

        self.spacing_mode_var = tk.StringVar(value=self.params.get("spacing_mode", "fixed"))
        ttk.Radiobutton(container, text="Фиксированное значение", variable=self.spacing_mode_var, value="fixed").pack(
            anchor=tk.W, padx=20)
        ttk.Radiobutton(container, text="Динамическое (зависит от максимального веса)", variable=self.spacing_mode_var,
                        value="dynamic").pack(anchor=tk.W, padx=20)

        f_fixed = ttk.Frame(container)
        f_fixed.pack(anchor=tk.W, padx=20, pady=2)
        ttk.Label(f_fixed, text="Фиксированное значение:").pack(side=tk.LEFT)
        self.spacing_fixed_var = tk.DoubleVar(value=self.params.get("spacing_fixed", 0.6))
        ttk.Spinbox(f_fixed, from_=0.1, to=4.0, increment=0.1, textvariable=self.spacing_fixed_var, width=5).pack(
            side=tk.LEFT, padx=5)

        f_dyn = ttk.Frame(container)
        f_dyn.pack(anchor=tk.W, padx=20, pady=5)
        ttk.Label(f_dyn, text="База (динам.):").pack(side=tk.LEFT)
        self.spacing_dyn_base_var = tk.DoubleVar(value=self.params.get("spacing_dynamic_base", 0.4))
        ttk.Spinbox(f_dyn, from_=0.1, to=2.0, increment=0.1, textvariable=self.spacing_dyn_base_var, width=5).pack(
            side=tk.LEFT, padx=5)
        ttk.Label(f_dyn, text="Множитель веса (динам.):").pack(side=tk.LEFT, padx=(10, 0))
        self.spacing_dyn_factor_var = tk.DoubleVar(value=self.params.get("spacing_dynamic_factor", 0.015))
        ttk.Spinbox(f_dyn, from_=0.0, to=0.1, increment=0.001, textvariable=self.spacing_dyn_factor_var, width=5).pack(
            side=tk.LEFT, padx=5)

        # 🔹 Фильтрация по упоминаниям
        if not self.save_to_defaults:
            sep2 = ttk.Separator(container, orient="horizontal")
            sep2.pack(fill=tk.X, padx=20, pady=15)
            ttk.Label(container, text="Фильтрация узлов по весу:", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W,
                                                                                                      padx=20)

            # Ключевые слова
            f_kw = ttk.Frame(container)
            f_kw.pack(fill=tk.X, padx=20, pady=5)
            ttk.Label(f_kw, text="Ключевые слова / N-граммы:").pack(side=tk.LEFT, padx=(0, 10))
            ttk.Label(f_kw, text="Мин:").pack(side=tk.LEFT)
            self.kw_min_var = tk.IntVar(value=self.params.get("kw_min", 1))
            ttk.Spinbox(f_kw, from_=1, to=self.max_graph_weight, increment=1, textvariable=self.kw_min_var,
                        width=8).pack(side=tk.LEFT, padx=2)
            ttk.Label(f_kw, text="Макс:").pack(side=tk.LEFT)
            self.kw_max_var = tk.IntVar(value=self.params.get("kw_max", 999999))
            ttk.Spinbox(f_kw, from_=1, to=999999, increment=1, textvariable=self.kw_max_var, width=8).pack(side=tk.LEFT,
                                                                                                           padx=2)

            # Субъекты
            f_sub = ttk.Frame(container)
            f_sub.pack(fill=tk.X, padx=20, pady=5)
            ttk.Label(f_sub, text="Субъекты:").pack(side=tk.LEFT, padx=(0, 10))
            ttk.Label(f_sub, text="Мин:").pack(side=tk.LEFT)
            self.sub_min_var = tk.IntVar(value=self.params.get("sub_min", 1))
            ttk.Spinbox(f_sub, from_=1, to=self.max_graph_weight, increment=1, textvariable=self.sub_min_var,
                        width=8).pack(side=tk.LEFT, padx=2)
            ttk.Label(f_sub, text="Макс:").pack(side=tk.LEFT)
            self.sub_max_var = tk.IntVar(value=self.params.get("sub_max", 999999))
            ttk.Spinbox(f_sub, from_=1, to=999999, increment=1, textvariable=self.sub_max_var, width=8).pack(
                side=tk.LEFT, padx=2)

            # Фракции
            f_fac = ttk.Frame(container)
            f_fac.pack(fill=tk.X, padx=20, pady=5)
            ttk.Label(f_fac, text="Фракции:").pack(side=tk.LEFT, padx=(0, 10))
            ttk.Label(f_fac, text="Мин:").pack(side=tk.LEFT)
            self.fac_min_var = tk.IntVar(value=self.params.get("fac_min", 1))
            ttk.Spinbox(f_fac, from_=1, to=self.max_graph_weight, increment=1, textvariable=self.fac_min_var,
                        width=8).pack(side=tk.LEFT, padx=2)
            ttk.Label(f_fac, text="Макс:").pack(side=tk.LEFT)
            self.fac_max_var = tk.IntVar(value=self.params.get("fac_max", 999999))
            ttk.Spinbox(f_fac, from_=1, to=999999, increment=1, textvariable=self.fac_max_var, width=8).pack(
                side=tk.LEFT, padx=2)

    def _build_style_tab(self, container):
        ttk.Label(container, text="Цвета узлов:").pack(anchor=tk.W, padx=10)
        self._color_buttons = {}
        for node_type in ["keyword", "subject", "faction"]:
            f = ttk.Frame(container);
            f.pack(fill=tk.X, padx=20, pady=2)
            lbl = {"keyword": "Слово", "subject": "Субъект", "faction": "Фракция"}[node_type]
            ttk.Label(f, text=f"{lbl}: ").pack(side=tk.LEFT)
            color = self.params.get("node_colors", {}).get(node_type, "#ffffff")
            btn = tk.Label(f, bg=color, width=2, relief="solid")
            btn.pack(side=tk.LEFT, padx=5)
            btn.bind("<Button-1>", lambda e, m="node", k=node_type, b=btn: self._pick_color(m, k, b))
            self._color_buttons[f"node_{node_type}"] = btn

        ttk.Label(container, text="Цвета рёбер:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self._edge_buttons = {}
        for edge_type in ["kw-kw", "sub-fac", "sub-kw", "sub-sub"]:
            f = ttk.Frame(container);
            f.pack(fill=tk.X, padx=20, pady=2)
            names = {"kw-kw": "Слово-Слово", "sub-fac": "Фракция-Субъект", "sub-kw": "Субъект-Слово",
                     "sub-sub": "Субъект-Субъект"}
            ttk.Label(f, text=f"{names.get(edge_type, edge_type)}: ").pack(side=tk.LEFT)
            color = self.params.get("edge_colors", {}).get(edge_type, "#888888")
            btn = tk.Label(f, bg=color, width=2, relief="solid")
            btn.pack(side=tk.LEFT, padx=5)
            btn.bind("<Button-1>", lambda e, m="edge", k=edge_type, b=btn: self._pick_color(m, k, b))
            self._edge_buttons[f"edge_{edge_type}"] = btn

        self.font_size = tk.IntVar(value=self.params.get("font", {}).get("size", 8))
        self.font_weight = tk.StringVar(value=self.params.get("font", {}).get("weight", "normal"))
        self.offset_x = tk.DoubleVar(value=self.params.get("offsets", {}).get("x", 0.0))
        self.offset_y = tk.DoubleVar(value=self.params.get("offsets", {}).get("y", 0.0))

        f_font = ttk.Frame(container);
        f_font.pack(fill=tk.X, padx=20, pady=10)
        ttk.Label(f_font, text="Шрифт (px):").pack(side=tk.LEFT)
        ttk.Spinbox(f_font, from_=6, to=16, textvariable=self.font_size, width=3).pack(side=tk.LEFT, padx=5)
        ttk.Label(f_font, text="| Начертание:").pack(side=tk.LEFT, padx=5)
        ttk.Combobox(f_font, textvariable=self.font_weight, values=["normal", "bold"], width=7, state="readonly").pack(
            side=tk.LEFT)

        f_off = ttk.Frame(container);
        f_off.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(f_off, text="Смещение текста (X, Y):").pack(side=tk.LEFT)
        ttk.Spinbox(f_off, from_=-0.2, to=0.2, increment=0.01, textvariable=self.offset_x, width=5).pack(side=tk.LEFT,
                                                                                                         padx=5)
        ttk.Label(f_off, text=",").pack(side=tk.LEFT)
        ttk.Spinbox(f_off, from_=-0.2, to=0.2, increment=0.01, textvariable=self.offset_y, width=5).pack(side=tk.LEFT)

        self.smart_labels_var = tk.BooleanVar(value=self.params.get("smart_labels", False))
        self._add_cb(container, "Радиальное размещение подписей", self.smart_labels_var,
                     "Автоматически раздвигает подписи...")

        self.label_base_radius_var = tk.DoubleVar(value=self.params.get("label_base_radius", 0.035))
        self.label_radius_mult_var = tk.DoubleVar(value=self.params.get("label_radius_multiplier", 0.003))

        ttk.Label(container, text="Радиальное смещение (базовое):").pack(anchor=tk.W, padx=20, pady=(15, 2))
        ttk.Spinbox(container, from_=0.0, to=0.5, increment=0.005, textvariable=self.label_base_radius_var,
                    width=5).pack(anchor=tk.W, padx=20)

        ttk.Label(container, text="Множитель радиуса на длину текста:").pack(anchor=tk.W, padx=20, pady=(5, 2))
        ttk.Spinbox(container, from_=0.0, to=0.05, increment=0.001, textvariable=self.label_radius_mult_var,
                    width=5).pack(anchor=tk.W, padx=20)

        ttk.Label(container, text="Цвет центрального слова:").pack(anchor=tk.W, padx=10, pady=(15, 0))
        f_cw = ttk.Frame(container);
        f_cw.pack(fill=tk.X, padx=20, pady=2)
        center_color = self.params.get("center_word_color", "#FFD700")
        self.center_color_btn = tk.Label(f_cw, bg=center_color, width=2, relief="solid", cursor="hand2")
        self.center_color_btn.pack(side=tk.LEFT, padx=5)
        ttk.Label(f_cw, text="(для режима \"Портрет слова\")").pack(side=tk.LEFT, padx=5)
        self.center_color_btn.bind("<Button-1>", lambda e, b=self.center_color_btn: self._pick_center_color(b))

    def _build_presets_tab(self, container):
        ttk.Label(container, text="Сохранить как стиль:").pack(pady=10)
        self.style_name = tk.StringVar(value="Мой стиль")
        ttk.Entry(container, textvariable=self.style_name, width=20).pack()
        ttk.Button(container, text="Сохранить", command=self._save_style).pack(pady=5)
        self.style_combo = ttk.Combobox(container, values=list(self.params.get("styles", {}).keys()), state="readonly",
                                        width=20)
        self.style_combo.pack()
        self.style_combo.bind("<<ComboboxSelected>>", self._load_style)
        ttk.Button(container, text="Удалить стиль", command=self._delete_style).pack(pady=5)

    def _pick_center_color(self, btn):
        code, color = colorchooser.askcolor(initialcolor=btn.cget("bg"))
        if color:
            btn.config(bg=color)
            self.params["center_word_color"] = color

    def _apply_defaults_viz(self):
        if not messagebox.askyesno("Подтверждение", "Применить параметры по умолчанию к текущей базе?"):
            return
        defaults = load_defaults_settings()
        viz = defaults.get("viz_params", {})
        self.var_kw.set(viz.get("kw_conn", True))
        self.center_type_var.set(viz.get("center_type", viz.get("viz_center_type", "Общий вид")))
        self.layout_var.set(viz.get("layout_type", "Сило-ориентированный"))
        self.node_select_var.set(viz.get("center_node", viz.get("viz_center_node", " ")))
        self._update_node_dropdown(None)
        self._save_and_close()

    def _pick_color(self, mode, key, btn):
        code, color = colorchooser.askcolor(initialcolor=btn.cget("bg"))
        if color:
            btn.config(bg=color)
            if mode == "node":
                self.params.setdefault("node_colors", {})[key] = color
            else:
                self.params.setdefault("edge_colors", {})[key] = color

    def _save_style(self):
        name = self.style_name.get().strip()
        if not name: return
        if "styles" not in self.params: self.params["styles"] = {}
        self.params["styles"][name] = {
            "node_colors": dict(self.params.get("node_colors", {})),
            "edge_colors": dict(self.params.get("edge_colors", {})),
            "font": {"size": self.font_size.get(), "weight": self.font_weight.get(),
                     "color": self.params.get("font", {}).get("color", "#000")},
            "offsets": {"x": self.offset_x.get(), "y": self.offset_y.get()},
            "smart_labels": self.smart_labels_var.get(),
            "label_base_radius": self.label_base_radius_var.get(),
            "label_radius_multiplier": self.label_radius_mult_var.get(),
            "spacing_mode": self.spacing_mode_var.get(),
            "spacing_fixed": self.spacing_fixed_var.get(),
            "spacing_dynamic_base": self.spacing_dyn_base_var.get(),
            "spacing_dynamic_factor": self.spacing_dyn_factor_var.get(),
            "kw_min": self.kw_min_var.get(), "kw_max": self.kw_max_var.get(),
            "sub_min": self.sub_min_var.get(), "sub_max": self.sub_max_var.get(),
            "fac_min": self.fac_min_var.get(), "fac_max": self.fac_max_var.get()
        }
        self.style_combo['values'] = list(self.params["styles"].keys())
        self.style_combo.set(name)
        messagebox.showinfo("Успех", f"Стиль '{name}' сохранён.")

    def _load_style(self, e=None):
        name = self.style_combo.get()
        if name in self.params.get("styles", {}):
            s = self.params["styles"][name]
            self.params["node_colors"].update(s.get("node_colors", {}))
            self.params["edge_colors"].update(s.get("edge_colors", {}))
            self.params["font"].update(s.get("font", {}))
            self.params["offsets"].update(s.get("offsets", {}))
            self.font_size.set(self.params["font"]["size"])
            self.font_weight.set(self.params["font"]["weight"])
            self.offset_x.set(self.params["offsets"]["x"])
            self.offset_y.set(self.params["offsets"]["y"])
            # 🔹 ВОССТАНОВЛЕНО: Загрузка параметров разрежения из стиля
            if "spacing_mode" in s:
                self.spacing_mode_var.set(s["spacing_mode"])
                self.spacing_fixed_var.set(s.get("spacing_fixed", 0.6))
                self.spacing_dyn_base_var.set(s.get("spacing_dynamic_base", 0.4))
                self.spacing_dyn_factor_var.set(s.get("spacing_dynamic_factor", 0.015))
            if "kw_min" in s:
                self.kw_min_var.set(s.get("kw_min", 1))
                self.kw_max_var.set(s.get("kw_max", 999999))
                self.sub_min_var.set(s.get("sub_min", 1))
                self.sub_max_var.set(s.get("sub_max", 999999))
                self.fac_min_var.set(s.get("fac_min", 1))
                self.fac_max_var.set(s.get("fac_max", 999999))
            for k, v in self.params["node_colors"].items():
                if f"node_{k}" in self._color_buttons: self._color_buttons[f"node_{k}"].config(bg=v)
            for k, v in self.params["edge_colors"].items():
                if f"edge_{k}" in self._edge_buttons: self._edge_buttons[f"edge_{k}"].config(bg=v)
            messagebox.showinfo("Успех", f"Стиль '{name}' применён.")

    def _update_node_dropdown(self, event):
        ctype = self.center_type_var.get()
        node_type_map = {"Портрет фракции": "faction", "Портрет субъекта": "subject", "Портрет слова": "keyword"}
        if ctype == "Общий вид":
            self.node_combo.config(state=tk.DISABLED);
            self.node_select_var.set("  ");
            return
        nodes = self._get_available_nodes(node_type_map.get(ctype))
        self.node_combo['values'] = sorted(nodes)
        if nodes:
            self.node_combo.config(state="readonly");
            self.node_select_var.set(
                nodes[0] if self.node_select_var.get() not in nodes else self.node_select_var.get())
        else:
            self.node_combo.config(state=tk.DISABLED);
            self.node_select_var.set("  ")

    def _get_available_nodes(self, node_type):
        g_path = os.path.join(self.db_path, "graph_data.json")
        if not os.path.exists(g_path): return []
        try:
            with open(g_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            valid_types = {"keyword", "ngram"} if node_type == "keyword" else {node_type}
            return [n['id'] for n in data['nodes'] if n.get('type') in valid_types]
        except:
            return []

    def _add_cb(self, parent, text, var, tip):
        f = ttk.Frame(parent);
        f.pack(anchor=tk.W, padx=15, pady=2)
        cb = ttk.Checkbutton(f, variable=var, text=text);
        cb.pack(side=tk.LEFT)
        self._setup_tip(cb, tip)

    def _setup_tip(self, w, text):
        tw = None

        def show(e):
            nonlocal tw
            if tw and tw.winfo_exists(): tw.destroy()
            tw = tk.Toplevel(self.window);
            tw.wm_overrideredirect(True)
            ttk.Label(tw, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                      font=("tahoma", "8", "normal"), wraplength=300).pack(ipadx=6, ipady=4)
            x, y = e.x_root + 15, e.y_root + 15;
            tw.wm_geometry(f"+{x}+{y}")

        def hide(e):
            nonlocal tw
            if tw and tw.winfo_exists(): tw.destroy(); tw = None

        w.bind("<Enter>", show);
        w.bind("<Leave>", hide)

    def _delete_style(self):
        name = self.style_combo.get()
        if not name or name not in self.params.get("styles", {}): messagebox.showwarning("Внимание",
                                                                                         "Стиль не выбран."); return
        if not messagebox.askyesno("Подтверждение", f"Удалить стиль '{name}'?"): return
        del self.params["styles"][name]
        self.style_combo['values'] = list(self.params["styles"].keys());
        self.style_combo.set("")
        try:
            with open(self.params_file, 'w', encoding='utf-8') as f:
                json.dump(self.params, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Успех", "Стиль удалён.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _save_and_close(self):
        if not self.save_to_defaults:
            self.params.update({
                "kw_conn": self.var_kw.get(), "center_type": self.center_type_var.get(),
                "center_node": self.node_select_var.get(), "layout_type": self.layout_var.get(),
                "font": {"size": self.font_size.get(), "weight": self.font_weight.get(),
                         "color": self.params.get("font", {}).get("color", "#000")},
                "center_word_color": self.params.get("center_word_color", "#FFD700"),
                "offsets": {"x": self.offset_x.get(), "y": self.offset_y.get()},
                "smart_labels": self.smart_labels_var.get(),
                "label_base_radius": self.label_base_radius_var.get(),
                "label_radius_multiplier": self.label_radius_mult_var.get(),
                # Типизированная фильтрация (сохраняем текущие значения)
                "kw_min": self.kw_min_var.get(), "kw_max": self.kw_max_var.get(),
                "sub_min": self.sub_min_var.get(), "sub_max": self.sub_max_var.get(),
                "fac_min": self.fac_min_var.get(), "fac_max": self.fac_max_var.get(),
                # Параметры разрежения
                "spacing_mode": self.spacing_mode_var.get(),
                "spacing_fixed": self.spacing_fixed_var.get(),
                "spacing_dynamic_base": self.spacing_dyn_base_var.get(),
                "spacing_dynamic_factor": self.spacing_dyn_factor_var.get()
            })
        else:
            self.params.update({
                "kw_conn": self.var_kw.get(), "center_type": self.center_type_var.get(),
                "center_node": self.node_select_var.get(), "layout_type": self.layout_var.get(),
                "font": {"size": self.font_size.get(), "weight": self.font_weight.get(),
                         "color": self.params.get("font", {}).get("color", "#000")},
                "center_word_color": self.params.get("center_word_color", "#FFD700"),
                "offsets": {"x": self.offset_x.get(), "y": self.offset_y.get()},
                "smart_labels": self.smart_labels_var.get(),
                "label_base_radius": self.label_base_radius_var.get(),
                "label_radius_multiplier": self.label_radius_mult_var.get(),
                # Параметры разрежения
                "spacing_mode": self.spacing_mode_var.get(),
                "spacing_fixed": self.spacing_fixed_var.get(),
                "spacing_dynamic_base": self.spacing_dyn_base_var.get(),
                "spacing_dynamic_factor": self.spacing_dyn_factor_var.get()
            })
        try:
            with open(self.params_file, 'w', encoding='utf-8') as f:
                json.dump(self.params, f, ensure_ascii=False, indent=2)
        except:
            pass
        if self.apply_callback: self.apply_callback()
        self.window.destroy()