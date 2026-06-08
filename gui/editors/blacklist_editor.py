import tkinter as tk
from tkinter import ttk
import os
import json
from collections import Counter
from config import BLACKLIST_FILE_NAME, GRAMS_FILE_NAME, DEPUTIES_FILE_NAME, FACTIONS_FILE_NAME


class BlacklistEditorWindow:
    def __init__(self, parent, db_path):
        self.parent = parent
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("Настройки фильтрации")
        self.window.geometry("920x680")
        self.window.transient(parent)
        self.window.grab_set()

        # Гарантированное сохранение при закрытии окна
        self.window.protocol("WM_DELETE_WINDOW", self.on_close_editor)

        self.tab_keys = ['keywords', 'ngrams', 'deputies', 'factions']
        self.tab_frames = {}
        self.tab_mode_vars = {k: tk.BooleanVar(value=False) for k in self.tab_keys}
        self.tab_vars = {k: {} for k in self.tab_keys}
        self.tab_select_all_vars = {k: tk.BooleanVar() for k in self.tab_keys}
        self.tab_search_vars = {k: tk.StringVar() for k in self.tab_keys}

        # 🔹 НОВОЕ: Живое хранение выделений в памяти (чтобы не сбрасывалось при поиске)
        self.live_selection = {k: set() for k in self.tab_keys}
        self._load_selection_from_disk()

        self._last_clusters_counter = None

        # Загрузка кластеров из graph_data.json
        g_path = os.path.join(db_path, "graph_data.json")
        if os.path.exists(g_path):
            try:
                with open(g_path, 'r', encoding='utf-8') as f:
                    g_data = json.load(f)
                counts = Counter()
                for n in g_data.get("nodes", []):
                    if n.get("type") == "keyword":
                        counts[n["id"]] = n.get("weight", 0)
                if counts:
                    self._last_clusters_counter = counts
            except Exception:
                pass

        notebook = ttk.Notebook(self.window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for key in self.tab_keys:
            self.tab_frames[key] = ttk.Frame(notebook)
            mode_file = os.path.join(self.db_path, f"{key}_mode.state")
            if os.path.exists(mode_file):
                try:
                    with open(mode_file, 'r', encoding='utf-8') as f:
                        if f.read().strip().lower() == 'true':
                            self.tab_mode_vars[key].set(True)
                except Exception:
                    pass

        notebook.add(self.tab_frames['keywords'], text="Ключевые слова")
        notebook.add(self.tab_frames['ngrams'], text="N-граммы")
        notebook.add(self.tab_frames['deputies'], text="Субъекты")
        notebook.add(self.tab_frames['factions'], text="Фракции")

        self.source_files = {
            'keywords': BLACKLIST_FILE_NAME, 'ngrams': GRAMS_FILE_NAME,
            'deputies': DEPUTIES_FILE_NAME, 'factions': FACTIONS_FILE_NAME
        }

        # Инициализация вкладок
        for key in self.tab_keys:
            if key == 'keywords':
                self._refresh_keywords_tab()
            else:
                self.load_and_populate_tab(key, self.source_files[key])

        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(button_frame, text="Сохранить и закрыть",
                   command=lambda: (self.save_state(), self.window.destroy())).pack(side=tk.RIGHT, padx=5)

    def _load_selection_from_disk(self):
        """Загружает текущие выделения из файлов в память при старте."""
        for k in self.tab_keys:
            bl_f = os.path.join(self.db_path, f"{k}_blacklist.txt")
            if os.path.exists(bl_f):
                try:
                    with open(bl_f, 'r', encoding='utf-8') as f:
                        for line in f:
                            item = line.strip().split('\t')[0].strip()
                            if item:
                                self.live_selection[k].add(item)
                except:
                    pass

    def _update_selection(self, tab_key, term, var):
        """Обновляет live_selection при клике на галочку."""
        if var.get():
            self.live_selection[tab_key].add(term)
        else:
            self.live_selection[tab_key].discard(term)
        self.update_select_all_state(tab_key)

    def on_close_editor(self):
        self.save_state()
        try:
            self.window.destroy()
        except Exception:
            pass

    def save_state(self):
        for k in self.tab_keys:
            mode_f = os.path.join(self.db_path, f"{k}_mode.state")
            try:
                with open(mode_f, 'w', encoding='utf-8') as f:
                    f.write(str(self.tab_mode_vars[k].get()))
            except Exception as e:
                print(f"Ошибка сохранения режима {k}: {e}")

            bl_f = os.path.join(self.db_path, f"{k}_blacklist.txt")
            try:
                # ✅ Сохраняем из live_selection
                sel = sorted(self.live_selection[k])
                with open(bl_f, 'w', encoding='utf-8') as f:
                    for i in sel:
                        f.write(f"{i}\t1\n")
            except Exception as e:
                print(f"Ошибка сохранения {k}_blacklist.txt: {e}")

    def get_filter_state(self):
        state = {}
        for tab_key in self.tab_keys:
            state[tab_key] = {"mode": self.tab_mode_vars[tab_key].get(), "selected": self.live_selection[tab_key]}
        return state

    def populate_keywords_tab(self, clusters_counter):
        self._last_clusters_counter = clusters_counter
        self._refresh_keywords_tab()

    def _refresh_keywords_tab(self):
        tab_key = 'keywords'
        frame = self.tab_frames[tab_key]
        for w in frame.winfo_children(): w.destroy()
        self.tab_vars[tab_key].clear()

        controls_frame = ttk.Frame(frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(controls_frame, text="Поиск:  ").pack(side=tk.LEFT, padx=(0, 2))
        search_entry = ttk.Entry(controls_frame, textvariable=self.tab_search_vars[tab_key], width=20)
        search_entry.pack(side=tk.LEFT, padx=(0, 5))
        self.tab_search_vars[tab_key].trace_add('write', lambda *a: self._kw_schedule_refresh())

        self.sort_mode_var = tk.StringVar(value="Количество (убыв.)")
        ttk.Label(controls_frame, text="Сортировка:  ").pack(side=tk.LEFT, padx=(5, 2))
        sort_combo = ttk.Combobox(controls_frame, textvariable=self.sort_mode_var,
                                  values=["Количество (убыв.)", "Алфавит"], state="readonly", width=22)
        sort_combo.pack(side=tk.LEFT, padx=5)
        sort_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_keywords_content())

        ttk.Checkbutton(controls_frame, variable=self.tab_mode_vars[tab_key],
                        text="Режим белого списка").pack(side=tk.LEFT, padx=5)

        self.tab_select_all_vars[tab_key] = tk.BooleanVar()
        ttk.Checkbutton(controls_frame, variable=self.tab_select_all_vars[tab_key],
                        text="Выделить все").pack(side=tk.RIGHT, padx=5)
        self.tab_select_all_vars[tab_key].trace_add('write', lambda *a: self.toggle_select_all(tab_key))

        self._kw_canvas_frame = ttk.Frame(frame)
        self._kw_canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self._kw_canvas = tk.Canvas(self._kw_canvas_frame)
        self._kw_sb = ttk.Scrollbar(self._kw_canvas_frame, orient=tk.VERTICAL, command=self._kw_canvas.yview)
        self._kw_sf = ttk.Frame(self._kw_canvas)
        self._kw_sf.bind("<Configure>", lambda e: self._kw_canvas.configure(scrollregion=self._kw_canvas.bbox("all")))
        self._kw_canvas.create_window((0, 0), window=self._kw_sf, anchor="nw")
        self._kw_canvas.configure(yscrollcommand=self._kw_sb.set)
        self._kw_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._kw_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_keywords_content()

    def _kw_schedule_refresh(self):
        if hasattr(self, '_kw_refresh_job'): self.window.after_cancel(self._kw_refresh_job)
        self._kw_refresh_job = self.window.after(300, self._refresh_keywords_content)

    def _refresh_keywords_content(self):
        tab_key = 'keywords'
        self.tab_vars[tab_key].clear()
        for w in self._kw_sf.winfo_children(): w.destroy()
        if not self._last_clusters_counter: return

        # 🔹 Используем live_selection (ПАМЯТЬ) вместо чтения файла
        current_selected = self.live_selection[tab_key]

        query = self.tab_search_vars[tab_key].get().lower()
        items = sorted(self._last_clusters_counter.items(),
                       key=lambda x: (-x[1], x[0]) if self.sort_mode_var.get() == "Количество (убыв.)" else (x[0],
                                                                                                             -x[1]))

        for term, count in items:
            if query and query not in term.lower(): continue
            display_text = f"{term} — {count}"
            clean_term = term.strip()

            # 🔹 Берем значение из live_selection
            var = tk.BooleanVar(value=clean_term in current_selected)
            self.tab_vars[tab_key][clean_term] = var

            # 🔹 Добавляем command для обновления live_selection при клике
            cb = ttk.Checkbutton(self._kw_sf, variable=var, text=display_text,
                                 command=lambda t=tab_key, term=clean_term, v=var: self._update_selection(t, term, v))
            cb.pack(anchor=tk.W, padx=5, pady=2)

        self.update_select_all_state(tab_key)

    def _get_display_items(self, tab_key, source_filename):
        """Универсальный парсер элементов с поддержкой расшифровок."""
        items_data = []
        if tab_key == 'keywords' and self._last_clusters_counter:
            for term, count in self._last_clusters_counter.items():
                items_data.append((term.strip(), f"{term.strip()} — {count}"))
        else:
            src_path = os.path.join(self.db_path, source_filename)
            if os.path.exists(src_path):
                with open(src_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        if '\t' in line:
                            parts = line.split('\t')
                            if tab_key == 'ngrams':
                                term = parts[0].strip()
                                desc = parts[1].strip() if len(parts) > 1 else ""
                                # 🔹 Формируем отображение с расшифровкой
                                display = f"{term} — {desc}" if desc else term
                                items_data.append((term, display))
                            elif tab_key == 'deputies' and len(parts) >= 4:
                                full_name = f"{parts[0]} {parts[1]} {parts[2]}".strip()
                                faction = parts[3].split('@')[0].strip() if '@' in parts[3] else parts[3].strip()
                                display = f"{full_name} — {faction}"
                                items_data.append((full_name, display))
                            else:
                                term = parts[0].strip()
                                items_data.append((term, term))
                        else:
                            items_data.append((line, line))
        return items_data

    def load_and_populate_tab(self, tab_key, source_filename):
        self.tab_vars[tab_key].clear()
        frame = self.tab_frames[tab_key]

        if not frame.winfo_children():
            controls_frame = ttk.Frame(frame)
            controls_frame.pack(fill=tk.X, padx=5, pady=5)

            ttk.Label(controls_frame, text="Поиск:  ").pack(side=tk.LEFT, padx=(0, 2))
            search_entry = ttk.Entry(controls_frame, textvariable=self.tab_search_vars[tab_key], width=20)
            search_entry.pack(side=tk.LEFT, padx=(0, 5))
            self.tab_search_vars[tab_key].trace_add('write', lambda *a: self._filter_tab(tab_key, source_filename))

            ttk.Checkbutton(controls_frame, variable=self.tab_mode_vars[tab_key],
                            text="Режим белого списка").pack(side=tk.LEFT, padx=10)

            self.tab_select_all_vars[tab_key] = tk.BooleanVar()
            ttk.Checkbutton(controls_frame, variable=self.tab_select_all_vars[tab_key],
                            text="Выделить все").pack(side=tk.RIGHT, padx=5)
            self.tab_select_all_vars[tab_key].trace_add('write', lambda *a: self.toggle_select_all(tab_key))
        else:
            controls_frame = frame.winfo_children()[0]
            for w in frame.winfo_children()[1:]: w.destroy()

        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas = tk.Canvas(canvas_frame)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        sf = ttk.Frame(canvas)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 🔹 Используем live_selection (ПАМЯТЬ)
        current_selected = self.live_selection[tab_key]

        items_data = self._get_display_items(tab_key, source_filename)
        query = self.tab_search_vars[tab_key].get().lower()

        for raw_term, display_text in items_data:
            if query and query not in display_text.lower(): continue

            # 🔹 Берем значение из live_selection
            is_sel = raw_term in current_selected
            var = tk.BooleanVar(value=is_sel)
            self.tab_vars[tab_key][raw_term] = var

            # 🔹 Добавляем command
            cb = ttk.Checkbutton(sf, variable=var, text=display_text,
                                 command=lambda t=tab_key, term=raw_term, v=var: self._update_selection(t, term, v))
            cb.pack(anchor=tk.W, padx=5, pady=2)

        self.update_select_all_state(tab_key)

    def _filter_tab(self, tab_key, source_filename):
        query = self.tab_search_vars[tab_key].get().lower()
        self.tab_vars[tab_key].clear()
        frame = self.tab_frames[tab_key]

        for w in frame.winfo_children()[1:]: w.destroy()

        canvas_frame = ttk.Frame(frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas = tk.Canvas(canvas_frame)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        sf = ttk.Frame(canvas)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 🔹 Используем live_selection (ПАМЯТЬ)
        current_selected = self.live_selection[tab_key]

        items_data = self._get_display_items(tab_key, source_filename)

        for raw_term, display_text in items_data:
            if query and query not in display_text.lower(): continue

            # 🔹 Берем значение из live_selection
            is_sel = raw_term in current_selected
            var = tk.BooleanVar(value=is_sel)
            self.tab_vars[tab_key][raw_term] = var

            # 🔹 Добавляем command
            cb = ttk.Checkbutton(sf, variable=var, text=display_text,
                                 command=lambda t=tab_key, term=raw_term, v=var: self._update_selection(t, term, v))
            cb.pack(anchor=tk.W, padx=5, pady=2)

        self.update_select_all_state(tab_key)

    def toggle_select_all(self, tab_key):
        state = self.tab_select_all_vars[tab_key].get()
        for term in list(self.tab_vars[tab_key].keys()):
            self.tab_vars[tab_key][term].set(state)
            # 🔹 Обновляем live_selection при выделении всех
            if state:
                self.live_selection[tab_key].add(term)
            else:
                self.live_selection[tab_key].discard(term)

    def update_select_all_state(self, tab_key):
        if not self.tab_vars[tab_key]:
            self.tab_select_all_vars[tab_key].set(False)
            return
        self.tab_select_all_vars[tab_key].set(all(v.get() for v in self.tab_vars[tab_key].values()))