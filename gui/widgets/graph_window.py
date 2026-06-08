import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import json
import csv
import glob
import re
import threading
from datetime import datetime
from collections import defaultdict, Counter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import numpy as np
import networkx as nx
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import chardet

from config import (
    SOURCES_DIR_NAME, LEXEMES_DIR_NAME,
    GRAMS_FILE_NAME
)

from core.nlp import (
    MYSTEM_MODEL, perform_clustering_and_restore,
    preprocess_ngrams_mapping, get_active_stopwords
)

from core.database import load_filter_state_from_disk
from gui.dialogs.viz_params_dialog import VizParamsWindow
from gui.dialogs.export_dialog import StatsExportWindow
from gui.editors.sources_editor import SourceDetailsWindow
from gui.editors.blacklist_editor import BlacklistEditorWindow
from core.nlp import process_source_text_to_lemmas

def _safe_parse_date(date_str):
    """Безопасно парсит дату из строк 'ДД.ММ.ГГГГ' или 'ГГГГ-ММ-ДД'."""
    if not date_str:
        return None
    # Сначала пробуем ISO формат (стандарт)
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
    # Если не вышло, пробуем русский формат
    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return None

class GraphWindow:
    def __init__(self, parent, db_path):
        self.parent = parent
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("Работа с данными")
        self.window.geometry("1050x680")
        self.window.transient(parent)
        self.window.grab_set()

        # --- НОВОЕ: Состояния и модели для многопоточности ---
        self.cancel_flag = threading.Event()
        self.graph_built = False
        self.graph_data_path = os.path.join(db_path, "graph_data.json")

        # Загрузка состояния (восстановлена полная логика)
        self._load_graph_state()
        self.show_kw_conn_var = tk.BooleanVar(value=self.saved_state.get("show_kw_conn", False))  # <-- ДОБАВИТЬ СЮДА

        # Поиск дат в существующих JSON (восстановлено из оригинала)
        self.lexemes_dir = os.path.join(db_path, LEXEMES_DIR_NAME)
        self.earliest_date = None
        self.latest_date = None
        json_pattern = os.path.join(self.lexemes_dir, "*.json")
        for file_path in glob.glob(json_pattern):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    date_str = data.get("date")
                    if date_str:
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        if self.earliest_date is None or file_date < self.earliest_date:
                            self.earliest_date = file_date
                        if self.latest_date is None or file_date > self.latest_date:
                            self.latest_date = file_date
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
        self.earliest_str = self.earliest_date.strftime("%d.%m.%Y") if self.earliest_date else "Не определена"
        self.latest_str = self.latest_date.strftime("%d.%m.%Y") if self.latest_date else "Не определена"

        self.n_grams_file = os.path.join(db_path, GRAMS_FILE_NAME)

        # --- UI элементы ---
        top_frame = ttk.Frame(self.window)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top_frame, text="Порог кластеризации:").pack(side=tk.LEFT, padx=(0, 5))
        self.cluster_threshold_var = tk.DoubleVar(value=self.saved_state.get("threshold", 0.5))
        cluster_scale = ttk.Scale(top_frame, from_=0.0, to=1.0, orient='horizontal',
                                  variable=self.cluster_threshold_var, command=self.on_cluster_threshold_change)
        cluster_scale.pack(side=tk.LEFT, padx=(0, 10), fill=tk.X, expand=True)
        self.cluster_value_label = ttk.Label(top_frame, text=f"{self.cluster_threshold_var.get():.2f}")
        self.cluster_value_label.pack(side=tk.LEFT)

        current_date_str = datetime.now().strftime("%d.%m.%Y")
        self.date_from_var = tk.StringVar(value=self.saved_state.get("date_from", "21.02.1994"))
        self.date_to_var = tk.StringVar(value=self.saved_state.get("date_to", current_date_str))

        ttk.Label(top_frame, text="От:").pack(side=tk.LEFT, padx=(10, 2))
        self.date_from_entry = ttk.Entry(top_frame, textvariable=self.date_from_var, width=12)
        self.date_from_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.date_from_entry.bind('<KeyRelease>', self.format_date_field)  # Восстановлено

        ttk.Label(top_frame, text="До:").pack(side=tk.LEFT, padx=(0, 2))
        self.date_to_entry = ttk.Entry(top_frame, textvariable=self.date_to_var, width=12)
        self.date_to_entry.pack(side=tk.LEFT, padx=(0, 10))
        self.date_to_entry.bind('<KeyRelease>', self.format_date_field)  # Восстановлено

        self.invert_date_filter_var = tk.BooleanVar(value=self.saved_state.get("invert_filter", False))
        self.invert_date_filter_check = ttk.Checkbutton(top_frame, variable=self.invert_date_filter_var,
                                                        text="Инвертировать период")
        self.invert_date_filter_check.pack(side=tk.LEFT, padx=5)
        self.invert_date_filter_check.bind("<Button-1>", self.on_invert_filter_toggle)  # Восстановлено

        # Восстановление тултипа инверта
        tooltip_invert_period = None

        self._cached_graph_hash = None
        self._cached_positions = {}

        def show_tooltip_invert(event):
            nonlocal tooltip_invert_period
            if tooltip_invert_period: tooltip_invert_period.destroy()
            x, y, _, _ = self.invert_date_filter_check.bbox("insert")
            x += self.invert_date_filter_check.winfo_rootx() + 25
            y += self.invert_date_filter_check.winfo_rooty() + 25
            tooltip_invert_period = tk.Toplevel(self.window)
            tooltip_invert_period.wm_overrideredirect(True)
            tooltip_invert_period.wm_geometry(f"+{x}+{y}")
            label = ttk.Label(tooltip_invert_period,
                              text="Если включено, исключает источники, датированные внутри этого периода.",
                              background="#ffffe0", relief="solid", borderwidth=1, font=("tahoma", "8", "normal"))
            label.pack(ipadx=1, ipady=1)

        def hide_tooltip_invert(event):
            nonlocal tooltip_invert_period
            if tooltip_invert_period: tooltip_invert_period.destroy()
            tooltip_invert_period = None

        self.invert_date_filter_check.bind("<Enter>", show_tooltip_invert)
        self.invert_date_filter_check.bind("<Leave>", hide_tooltip_invert)

        ttk.Button(top_frame, text="Чёрный список", command=self.open_blacklist_editor).pack(side=tk.RIGHT, padx=5)

        # Прогресс и управление процессами
        ctrl_frame = ttk.Frame(self.window)
        ctrl_frame.pack(fill=tk.X, padx=10, pady=5)
        self.progress_bar = ttk.Progressbar(ctrl_frame, orient=tk.HORIZONTAL, mode='determinate', length=400)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.cancel_btn = ttk.Button(ctrl_frame, text="Прервать процесс", state=tk.DISABLED,
                                     command=self._cancel_process)
        self.cancel_btn.pack(side=tk.RIGHT, padx=5)

        log_frame = ttk.LabelFrame(self.window, text="Лог обработки")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, height=12)
        self.log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        status_frame = ttk.Frame(self.window)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        self.status_label = ttk.Label(status_frame, text="Статус: Готово к работе.")
        self.status_label.pack(anchor=tk.W)

        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self.process_btn = ttk.Button(btn_frame, text="Обработать базу данных",
                                      command=lambda: self._run_thread(self._process_db_thread))
        self.process_btn.pack(side=tk.LEFT, padx=5)

        self.force_process_btn = ttk.Button(btn_frame, text="Принудительная обработка",
                                            command=lambda: self._run_thread(
                                                lambda: self._process_db_thread(force=True)))
        self.force_process_btn.pack(side=tk.LEFT, padx=5)

        self.build_btn = ttk.Button(btn_frame, text="Построить граф",
                                    command=lambda: self._run_thread(self._build_graph_thread), state=tk.DISABLED)
        self.build_btn.pack(side=tk.LEFT, padx=5)

        self.build_btn.bind("<Enter>", lambda e: self._show_build_tooltip())
        self.build_btn.bind("<Leave>", lambda e: self._hide_build_tooltip())

        self.visualize_btn = ttk.Button(btn_frame, text="Визуализировать граф", command=self._visualize_graph,
                                        state=tk.DISABLED)
        self.visualize_btn.pack(side=tk.LEFT, padx=5)

        self.visualize_btn.bind("<Enter>", lambda e: self._show_viz_tooltip())
        self.visualize_btn.bind("<Leave>", lambda e: self._hide_viz_tooltip())

        self.viz_params_btn = ttk.Button(btn_frame, text="Параметры визуализации", command=self.open_viz_params)
        self.viz_params_btn.config(state=tk.DISABLED)  # ✅ Блокируем, пока граф не построен
        self.viz_params_btn.pack(side=tk.LEFT, padx=5)

        self.stats_export_btn = ttk.Button(btn_frame, text="Экспорт статистики", state=tk.DISABLED)
        self.stats_export_btn.pack(side=tk.RIGHT, padx=5)
        self.stats_export_btn.config(command=lambda: StatsExportWindow(self.window, self.db_path))

        ttk.Button(btn_frame, text="Закрыть", command=self.on_close).pack(side=tk.RIGHT, padx=5)

        # Загрузка N-грамм и чёрного списка в память (из оригинала)
        self.n_grams = set()
        if os.path.exists(self.n_grams_file):
            with open(self.n_grams_file, 'r', encoding='utf-8') as f:
                self.n_grams = {line.strip() for line in f if line.strip()}
        self.blacklisted_words = set()
        self._refresh_blacklist()
        self.database_processed = False

        self.cached_filter_state = None
        self.editor_ref = None  # Ссылка на открытый BlacklistEditorWindow

        self.graph_data_path = os.path.join(db_path, "graph_data.json")
        self.viz_params = {
            "kw_conn": True,
            "show_factions": True,
            "faction_kw_conn": False,
            "center": "factions",
            "layout": "spring",
            "show_edges": True,
            "show_weights": True,
            "label_offset_x": 0.0,
            "label_offset_y": 0.0
        }

        self.show_edges_var = tk.BooleanVar(value=True)

        pf = os.path.join(db_path, ".viz_params.json")
        if os.path.exists(pf):
            try:
                self.viz_params.update(json.load(open(pf, 'r')))
            except:
                pass

        self.sources_cache = {}
        self._load_sources_cache()

    def _load_sources_cache(self):
        self.sources_cache.clear()
        if not os.path.exists(self.lexemes_dir): return
        for fn in os.listdir(self.lexemes_dir):
            if fn.endswith('.json'):
                try:
                    with open(os.path.join(self.lexemes_dir, fn), 'r', encoding='utf-8') as f:
                        self.sources_cache[os.path.splitext(fn)[0]] = json.load(f)
                except Exception:
                    pass

    def open_viz_params(self):
        # 1. Вычисляем максимальный вес в графе, чтобы ограничить ввод пользователя
        max_graph_weight = 100  # Значение по умолчанию
        if self.graph_built:
            try:
                with open(self.graph_data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Ищем максимальный вес среди всех узлов
                weights = [n.get("weight", 1) for n in data.get("nodes", [])]
                if weights:
                    max_graph_weight = max(weights)
            except Exception:
                pass

        # 2. Передаем вычисленный максимум в диалог
        VizParamsWindow(self.window, self.db_path, self._apply_viz_params,
                        max_graph_weight=max_graph_weight)

    def _apply_viz_params(self):
        params_file = os.path.join(self.db_path, ".viz_params.json")
        if os.path.exists(params_file):
            try:
                with open(params_file, 'r', encoding='utf-8') as f:
                    self.viz_params.update(json.load(f))
            except Exception:
                pass
        # 🔹 ИСПРАВЛЕНИЕ 2: Автоматическая перерисовка, если граф уже построен
        if self.graph_built:
            self._visualize_graph()
        else:
            self._safe_update_status("Параметры обновлены. Нажмите \"Визуализировать граф\". ")

    # --- Вспомогательные методы безопасности GUI ---
    def _run_thread(self, func):
        self.cancel_flag.clear()
        self.cancel_btn.config(state=tk.NORMAL)
        t = threading.Thread(target=func, daemon=True)
        t.start()

    def _cancel_process(self):
        self.cancel_flag.set()
        self._safe_update_status("Выполнение отменено.")
        self._safe_log(">>> Пользователь запросил остановку процесса.\n")

    def _safe_log(self, msg):
        def _append():
            try:
                if not hasattr(self, 'window') or not self.window.winfo_exists(): return
                if not hasattr(self, 'log_text') or not self.log_text.winfo_exists(): return
                self.log_text.insert(tk.END, msg)
                self.log_text.see(tk.END)
                self.log_text.update_idletasks()  # ⚡ Мгновенная отрисовка без задержки
            except tk.TclError:
                pass

        self.window.after(0, _append)
        # Дополнительный пуш для гарантированного вывода в тяжёлых циклах
        if hasattr(self, 'window') and self.window.winfo_exists():
            self.window.update_idletasks()

    def _safe_update_status(self, text):
        def _update():
            try:
                if hasattr(self, 'status_label') and self.status_label.winfo_exists():
                    self.status_label.config(text=text)
            except tk.TclError:
                pass

        self.window.after(0, _update)

    def _safe_update_progress(self, value):
        def _update():
            try:
                if hasattr(self, 'progress_bar') and self.progress_bar.winfo_exists():
                    self.progress_bar.config(value=value)
            except tk.TclError:
                pass

        self.window.after(0, _update)

    def _show_build_tooltip(self):
        if self.build_btn.cget("state") == "disabled": self._show_tooltip(self.build_btn,
                                                                          "Сначала обработайте базу данных.")

    def _hide_build_tooltip(self):
        self._hide_tooltip(self.build_btn)

    def _show_viz_tooltip(self):
        # Теперь подсказка показывается ВСЕГДА при наведении, независимо от состояния кнопки
        self._show_tooltip(self.visualize_btn, "Чтобы применить изменения, перестройте граф.")

    def _hide_viz_tooltip(self):
        self._hide_tooltip(self.visualize_btn)

    def _show_tooltip(self, widget, text):
        if hasattr(self, 'tooltip_window') and self.tooltip_window and self.tooltip_window.winfo_exists():
            self.tooltip_window.destroy()
        x, y, _, _ = widget.bbox("insert")
        x += widget.winfo_rootx() + 25
        y += widget.winfo_rooty() + 25
        self.tooltip_window = tk.Toplevel(self.window)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        # ✅ ДОБАВЛЕН ЯВНЫЙ ШРИФТ: полностью совпадает с остальными подсказками в программе
        ttk.Label(self.tooltip_window, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                  font=("tahoma", "8", "normal")).pack(ipadx=1, ipady=1)

    def _hide_tooltip(self, widget):
        if hasattr(self, 'tooltip_window') and self.tooltip_window:
            self.tooltip_window.destroy();
            self.tooltip_window = None

    # --- Загрузка/Сохранение состояния (полное восстановление оригинала) ---
    def _load_graph_state(self):
        state_file = os.path.join(self.db_path, ".graph_window_state.json")
        invert_state_file = os.path.join(self.db_path, ".invert_date_filter_state")
        kw_conn_state_file = os.path.join(self.db_path, ".show_kw_conn.state")
        self.saved_state = {"threshold": 0.5, "date_from": "21.02.1994", "date_to": datetime.now().strftime("%d.%m.%Y"),
                            "invert_filter": False, "show_kw_conn": False}
        if os.path.exists(state_file):
            try:
                self.saved_state.update(json.load(open(state_file, 'r', encoding='utf-8')))
            except:
                pass
        if os.path.exists(invert_state_file):
            try:
                with open(invert_state_file, 'r', encoding='utf-8') as f:
                    val = f.read().strip()
                    if val: self.saved_state["invert_filter"] = (val.lower() == 'true')
            except:
                pass
        if os.path.exists(kw_conn_state_file):
            try:
                with open(kw_conn_state_file, 'r', encoding='utf-8') as f:
                    val = f.read().strip()
                    if val: self.saved_state["show_kw_conn"] = (val.lower() == 'true')
            except:
                pass

    def on_close(self):
        self.cancel_flag.set()
        self.saved_state.update({
            "threshold": self.cluster_threshold_var.get(),
            "date_from": self.date_from_var.get(),
            "date_to": self.date_to_var.get(),
            "invert_filter": self.invert_date_filter_var.get()
        })
        try:
            with open(os.path.join(self.db_path, ".graph_window_state.json"), 'w') as f:
                json.dump(self.saved_state, f, ensure_ascii=False, indent=4)
        except:
            pass
        try:
            with open(os.path.join(self.db_path, ".invert_date_filter_state"), 'w', encoding='utf-8') as f:
                f.write(str(self.invert_date_filter_var.get()))
        except:
            pass
        try:
            with open(os.path.join(self.db_path, ".show_kw_conn.state"), 'w', encoding='utf-8') as f:
                f.write(str(self.show_kw_conn_var.get()))
        except:
            pass
        self.window.destroy()

    def open_blacklist_editor(self):
        self.editor_ref = BlacklistEditorWindow(self.window, self.db_path)

        # Привязка закрытия для сброса ссылки
        def on_editor_close():
            self.editor_ref = None

        self.editor_ref.window.protocol("WM_DELETE_WINDOW", on_editor_close)

    def get_active_filter_state(self):
        if self.cached_filter_state:
            return self.cached_filter_state
        # Если кэша нет, возвращаем дефолт (показать всё)
        return {
            "keywords": {"mode": False, "selected": set()},
            "ngrams": {"mode": False, "selected": set()},
            "subjects": {"mode": False, "selected": set()},
            "factions": {"mode": False, "selected": set()}
        }

    def on_cluster_threshold_change(self, val):
        self.cluster_value_label.config(text=f"{float(val):.2f}")

    def on_invert_filter_toggle(self, event):
        state = self.invert_date_filter_var.get()
        state_file = os.path.join(self.db_path, ".invert_date_filter_state")
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                f.write(str(state))
        except Exception as e:
            print(f"DEBUG: Ошибка сохранения состояния инвертирования фильтра: {e}")

    def _refresh_blacklist(self):
        """Перезагружает элементы чёрного списка с диска в память."""
        self.blacklisted_words = set()
        for key in ['keywords', 'ngrams', 'deputies', 'factions']:
            bl_path = os.path.join(self.db_path, f"{key}_blacklist.txt")
            if os.path.exists(bl_path):
                try:
                    with open(bl_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line: continue
                            word = line.rsplit('\t', 1)[0] if '\t' in line else line
                            if word: self.blacklisted_words.add(word)
                except Exception as e:
                    print(f"DEBUG: Ошибка чтения {bl_path}: {e}")

    # --- Форматирование дат (полное восстановление оригинала) ---
    def format_date_field(self, event):
        entry_widget = event.widget
        var = self.date_from_var if entry_widget == self.date_from_entry else (
            self.date_to_var if entry_widget == self.date_to_entry else None)
        if not var: return
        value = var.get()
        cursor_pos_original = entry_widget.index(tk.INSERT)
        char = event.char
        new_value = value

        if event.type == tk.EventType.KeyPress:
            if char.isdigit():
                new_value = value[:cursor_pos_original] + char + value[cursor_pos_original:]
            elif char == '.':
                new_value = value[:cursor_pos_original] + char + value[cursor_pos_original:]
            else:
                return
        elif event.type == tk.EventType.KeyRelease:
            new_value = var.get();
            cursor_pos_original = entry_widget.index(tk.INSERT)
        else:
            return

        if event.keysym in ['BackSpace', 'Delete']:
            cursor_pos = cursor_pos_original
            if event.keysym == 'BackSpace' and cursor_pos > 0:
                new_value = value[:cursor_pos - 1] + value[cursor_pos:]
            elif event.keysym == 'Delete' and cursor_pos < len(value):
                new_value = value[:cursor_pos] + value[cursor_pos + 1:]
            digits_only = ''.join(filter(str.isdigit, new_value))
            formatted = ""
            for i, digit in enumerate(digits_only):
                if i == 2 or i == 4: formatted += '.'
                formatted += digit
            formatted = formatted[:10]
            var.set(formatted);
            entry_widget.icursor(cursor_pos_original)
            return

        digits_only = ''.join(filter(str.isdigit, new_value))
        formatted = ""
        for i, digit in enumerate(digits_only):
            if i == 2 or i == 4: formatted += '.'
            formatted += digit
        formatted = formatted[:10]
        dots_added_before_cursor = sum(1 for i in range(min(cursor_pos_original, len(digits_only))) if i == 2 or i == 4)
        new_cursor = min(len(formatted), cursor_pos_original + dots_added_before_cursor)
        if len(formatted) > 10: new_cursor = 10
        var.set(formatted);
        entry_widget.icursor(new_cursor)

    # --- НОВАЯ ЛОГИКА: Многопоточная обработка БД ---
    def _process_db_thread(self, force=False):
        # 1. Очистка старых логов и подготовка UI
        self.log_text.delete(1.0, tk.END)
        self._safe_update_status("Принудительная обработка..." if force else "Обработка...")
        mode_note = " (кэш игнорируется, пересчёт всех источников)" if force else ""
        self._safe_log(f"[{datetime.now().strftime('%H:%M:%S')}] Инициализация обработки базы данных{mode_note}...\n")

        self.build_btn.config(state=tk.DISABLED)
        self.database_processed = False

        sources_dir = os.path.join(self.db_path, SOURCES_DIR_NAME)
        lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)

        # Гарантия существования папок с логированием
        for d in [sources_dir, lexemes_dir]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
                self._safe_log(f"Создана директория: {d}\n")

        try:
            all_files = [f for f in os.listdir(sources_dir) if f.endswith('.txt')]
        except PermissionError:
            self._safe_log(f"Ошибка: Нет прав доступа к папке {sources_dir}.\n")
            return
        except Exception as e:
            self._safe_log(f"Ошибка чтения директории: {e}\n")
            return

        if not all_files:
            self._safe_log("В папке 'sources' нет файлов .txt. Импортируйте источники и запустите обработку снова.\n")
            self.build_btn.config(state=tk.NORMAL)
            self._safe_update_progress(100)
            return

        self._safe_log(f"Найдено файлов в базе: {len(all_files)}\n")

        # 🔹 1. ФИЛЬТРАЦИЯ ПО ДАТЕ И ПРОВЕРКА КЭША (до начала цикла)
        try:
            d_from = datetime.strptime(self.date_from_var.get(), "%d.%m.%Y")
            d_to = datetime.strptime(self.date_to_var.get(), "%d.%m.%Y")
            invert = self.invert_date_filter_var.get()
        except ValueError:
            self._safe_log("Ошибка формата даты. Используйте ДД.ММ.ГГГГ.\n")
            self.build_btn.config(state=tk.NORMAL)
            self._safe_update_progress(100)
            return

        self._safe_log(
            f"Фильтр периода: {d_from.strftime('%d.%m.%Y')} - {d_to.strftime('%d.%m.%Y')} {'(инвертировано)' if invert else ''}\n")

        files_to_process = []
        skipped_by_date = 0
        skipped_cached = 0

        for fname in all_files:
            lex_path = os.path.join(lexemes_dir, f"{os.path.splitext(fname)[0]}.json")
            filepath = os.path.join(sources_dir, fname)
            in_range = True

            # Проверяем дату по уже существующему JSON
            if os.path.exists(lex_path):
                try:
                    with open(lex_path, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    date_str = old_data.get("date")
                    src_date = _safe_parse_date(date_str)  # Используем новую функцию

                    if src_date:
                        in_range = d_from <= src_date <= d_to
                        if invert: in_range = not in_range
                except:
                    pass

            if not in_range:
                skipped_by_date += 1
                continue

            # 🔹 ПРОВЕРКА КЭША + МЕТАДАННЫХ (субъекты, дата)
            cache_valid = False
            if not force and os.path.exists(lex_path) and os.path.getmtime(lex_path) >= os.path.getmtime(filepath):
                try:
                    # 1. Быстрая проверка времени: кэш не должен быть старше исходного файла
                    if os.path.getmtime(lex_path) >= os.path.getmtime(filepath):
                        # 2. Валидация содержимого: читаем JSON один раз, проверяем наличие токенов
                        with open(lex_path, 'r', encoding='utf-8') as jf:
                            j_data = json.load(jf)
                        # Если токены есть, считаем кэш актуальным.
                        # Дата и депутаты уже сохранены внутри этого же JSON, поэтому отдельный .meta файл избыточен.
                        if j_data.get("tokens"):
                            cache_valid = True
                except (json.JSONDecodeError, OSError):
                    pass

            if cache_valid:
                skipped_cached += 1
                continue

            files_to_process.append(fname)

        self._safe_log(f"Для обработки отобрано: {len(files_to_process)} источников.\n")
        if skipped_by_date > 0: self._safe_log(f"   Пропущено по дате: {skipped_by_date}\n")
        if skipped_cached > 0: self._safe_log(f"   Пропущено (кэш актуален): {skipped_cached}\n")

        if not files_to_process:
            self._safe_log("Нет файлов для обработки. База актуальна или все вне периода.\n")
            self.database_processed = True
            self._safe_update_status("База данных актуальна. Можно строить граф.")
            self.build_btn.config(state=tk.NORMAL)
            self._safe_update_progress(100)
            return

        # 🔹 2. ЗАГРУЗКА СПРАВОЧНИКОВ
        current_stopwords = get_active_stopwords(self.db_path)
        ngram_mapping = preprocess_ngrams_mapping(
            set(open(os.path.join(self.db_path, GRAMS_FILE_NAME), 'r', encoding='utf-8').read().splitlines()),
            current_stopwords
        )
        self._safe_log("Справочники (N-граммы, стоп-слова) загружены.\n\n")

        # 🔹 3. ЦИКЛ ОБРАБОТКИ (логи пишутся сразу после каждого шага)
        for idx, fname in enumerate(files_to_process, 1):
            if self.cancel_flag.is_set(): break
            self._safe_update_progress((idx / len(files_to_process)) * 100)

            filepath = os.path.join(sources_dir, fname)
            self._safe_log(f"[{datetime.now().strftime('%H:%M:%S')}] Открыт источник: {fname}\n")

            try:
                with open(filepath, 'rb') as f:
                    raw = f.read()
                # 🔥 Оптимизация: пропускаем chardet для файлов < 1МБ
                if len(raw) < 1_000_000:
                    try:
                        content = raw.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            content = raw.decode('cp1251')
                        except UnicodeDecodeError:
                            content = raw.decode('utf-8', errors='ignore')
                else:
                    enc = chardet.detect(raw)['encoding'] or 'utf-8'
                    content = raw.decode(enc, errors='ignore')

                content = content.replace('\n', '').replace('\r', '')

            except PermissionError:
                self._safe_log(f"   ОШИБКА ДОСТУПА: Файл заблокирован другим приложением.\n\n")
                continue
            except Exception as e:
                self._safe_log(f"   ОШИБКА ЧТЕНИЯ: {e}\n\n")
                continue

            # 🔹 Удаление римских цифр (восстановлено)
            content = re.sub(r'\b(?=[IVXLCDM]+\b)[IVXLCDM]+\b', '', content, flags=re.IGNORECASE)

            # 🔹 Расшифровка обозначений
            abbr_path = os.path.join(self.db_path, "abbreviations.json")
            if os.path.exists(abbr_path):
                try:
                    with open(abbr_path, 'r', encoding='utf-8') as f:
                        abbr_data = json.load(f)
                    for full_exp, abrs in sorted(abbr_data.items(), key=lambda x: -len(x[0])):
                        for abbr in abrs:
                            pattern = r'(?<!\w)' + re.escape(abbr) + r'(?!\w)'
                            content = re.sub(pattern, full_exp, content, flags=re.IGNORECASE)
                except:
                    pass

            # Лемматизация + N-граммы + Стоп-слова
            try:
                tokens = process_source_text_to_lemmas(content, ngram_mapping, current_stopwords)
                token_counts = Counter(tokens)
                self._safe_log(f"   Токенов найдено: {len(token_counts)}. Сохранение...\n")
            except Exception as e:
                self._safe_log(f"   ОШИБКА ПРИ ЛЕММАТИЗАЦИИ ({fname}): {str(e)}\n")
                # Пропускаем этот файл и переходим к следующему, чтобы не крашить всю базу
                continue

            # Сохранение JSON (с сохранением старых метаданных)
            lex_path = os.path.join(lexemes_dir, f"{os.path.splitext(fname)[0]}.json")
            old_deputies, old_date, old_url = [], datetime.now().strftime("%Y-%m-%d"), ""
            if os.path.exists(lex_path):
                try:
                    with open(lex_path, 'r', encoding='utf-8') as old_f:
                        old_data = json.load(old_f)
                        old_deputies = old_data.get("deputies", [])
                        old_date = old_data.get("date", old_date)
                        old_url = old_data.get("url", "")
                        old_description = old_data.get("description", "")
                except:
                    pass

            with open(lex_path, 'w', encoding='utf-8') as f:
                json.dump({"tokens": dict(token_counts), "date": old_date, "deputies": old_deputies, "url": old_url, "description": old_description}, f,
                          ensure_ascii=False, indent=2)

            # 🔹 Сохраняем метаданные кэша для будущих проверок
            meta_path = os.path.join(lexemes_dir, f".meta_{os.path.splitext(fname)[0]}.json")
            with open(meta_path, 'w', encoding='utf-8') as mf:
                json.dump({
                    "date": old_date,
                    "deps_hash": hash(str(sorted(old_deputies)))
                }, mf)

            # 🔹 Логирование полученных токенов (восстановлено)
            self._safe_log(f"[INFO] {fname}: Токены -> {token_counts.most_common()}\n\n")

        # 🔹 4. ЗАВЕРШЕНИЕ
        if not self.cancel_flag.is_set():
            self._load_sources_cache()
            self.database_processed = True
            self._safe_log(f"[{datetime.now().strftime('%H:%M:%S')}] База данных обработана успешно.\n")
            self._safe_update_status("База данных обработана. Можно строить граф.")
        else:
            self._safe_update_status("Обработка отменена пользователем.")

        self.build_btn.config(state=tk.NORMAL)
        self._safe_update_progress(100)

    # --- НОВАЯ ЛОГИКА: Многопоточное построение графа (с точными весами) ---
    def _build_graph_thread(self):
        self._safe_update_status("Построение графа...")
        self._safe_log("\n--- Построение графа ---\n")
        self._safe_update_progress(50)

        # 1. Парсинг дат и фильтрация источников
        try:
            d_from = datetime.strptime(self.date_from_var.get(), "%d.%m.%Y")
            d_to = datetime.strptime(self.date_to_var.get(), "%d.%m.%Y")
        except ValueError:
            self._safe_log("Ошибка формата даты. Используйте ДД.ММ.ГГГГ.\n")
            return

        lexemes_dir = self.lexemes_dir
        if not os.path.exists(lexemes_dir):
            self._safe_log("Папка лексем не найдена.\n")
            return

        sources_jsons = [f for f in os.listdir(lexemes_dir) if f.endswith('.json')]
        valid_sources = []
        total = len(sources_jsons)
        processed_count = 0

        for idx, sf in enumerate(sources_jsons, 1):
            if self.cancel_flag.is_set(): return

            try:
                with open(os.path.join(lexemes_dir, sf), 'r', encoding='utf-8') as f:
                    data = json.load(f)

                tokens = data.get("tokens", {})

                src_date_str = data.get("date", "N/A")
                in_range = True
                if src_date_str != "N/A":
                    src_date = _safe_parse_date(src_date_str)  # Используем новую функцию
                    if src_date:
                        in_range = d_from <= src_date <= d_to
                        if self.invert_date_filter_var.get(): in_range = not in_range
                    else:
                        pass

                if in_range:
                    valid_sources.append({"name": os.path.splitext(sf)[0], "tokens": tokens,
                                          "deputies": data.get("deputies", [])})
                    processed_count += 1
                    self._safe_update_progress(50 + (processed_count / max(total, 1)) * 25)
            except Exception as e:
                self._safe_log(f"Ошибка чтения {sf}: {e}\n")
                continue

        if not valid_sources:
            self._safe_log("Нет источников с токенами в выбранном диапазоне или база не обработана.\n")
            return

        # 2. Подготовка N-грамм и кластеризация
        ngram_mapping = {}
        ngrams_set = set()
        grams_file = os.path.join(self.db_path, GRAMS_FILE_NAME)
        if os.path.exists(grams_file):
            stopwords = get_active_stopwords(self.db_path)
            ngram_mapping = preprocess_ngrams_mapping(set(open(grams_file, 'r', encoding='utf-8').read().splitlines()),
                                                      stopwords)
            with open(grams_file, 'r', encoding='utf-8') as f:
                ngrams_set = {l.strip().lower() for l in f if l.strip()}

        self._safe_log("Кластеризация токенов...\n")
        if self.cancel_flag.is_set(): return
        global_token_counts = Counter()
        for src in valid_sources: global_token_counts.update(src["tokens"])
        unique_tokens = list(global_token_counts.keys())
        if not unique_tokens:
            self._safe_log("Токены не найдены.\n")
            return

        clustered_list = perform_clustering_and_restore(unique_tokens, threshold=self.cluster_threshold_var.get(),
                                                        ngram_mapping=ngram_mapping)
        cluster_map = dict(zip(unique_tokens, clustered_list))

        final_cluster_counts = Counter()
        final_source_data = []
        for src in valid_sources:
            mapped_tokens = []
            for orig_tok, count in src["tokens"].items():
                rep_tok = cluster_map.get(orig_tok, orig_tok)
                mapped_tokens.extend([rep_tok] * count)
                final_cluster_counts[rep_tok] += count
            final_source_data.append(
                {"name": src["name"], "tokens": Counter(mapped_tokens), "deputies": src["deputies"]})

        self._safe_update_progress(75)
        if self.editor_ref and self.editor_ref.window.winfo_exists():
            try:
                self.editor_ref.populate_keywords_tab(final_cluster_counts)
            except Exception as e:
                self._safe_log(f"Ошибка обновления вкладки: {e}\n")

        self._safe_log("--- Кластеры и веса ---\n")
        for tok, count in final_cluster_counts.most_common():
            self._safe_log(f"{tok}: {count}\n")

        # 3. Сбор графа с точными весами и типизацией узлов
        graph_data = {"nodes": [], "edges": []}
        for tok, count in final_cluster_counts.items():
            is_ngram = ' ' in tok or tok.lower() in ngrams_set
            # 🔹 Явное приведение веса к int, чтобы избежать проблем сериализации
            graph_data["nodes"].append({"id": tok, "type": "ngram" if is_ngram else "keyword", "weight": int(count)})

        sub_counts = defaultdict(set)
        fac_counts = defaultdict(int)
        sub_coocc = defaultdict(int)
        sub_kw_weight = defaultdict(int)
        for src in final_source_data:
            toks = list(src["tokens"].keys())
            deps = src.get("deputies", [])
            src_dep_names = [d.split(" — ", 1)[0].strip() for d in deps if " — " in d]
            for d in deps:
                if " — " in d:
                    name, fac = d.split(" — ", 1)
                    ac = fac.split('@')[0].strip()
                    sub_counts[name.strip()].add(src["name"])
                    fac_counts[fac.strip()] += 1
            for i in range(len(src_dep_names)):
                for j in range(i + 1, len(src_dep_names)):
                    sub_coocc[(src_dep_names[i], src_dep_names[j])] += 1
            for d_name in src_dep_names:
                for t in toks:
                    sub_kw_weight[(d_name, t)] += src["tokens"].get(t, 0)

        for d, srcs in sub_counts.items():
            graph_data["nodes"].append({"id": d, "type": "subject", "weight": len(srcs)})
        for f, c in fac_counts.items():
            graph_data["nodes"].append({"id": f, "type": "faction", "weight": c})

        kw_coocc = defaultdict(int)
        for src in final_source_data:
            token_counts = src["tokens"]
            unique_tokens = list(token_counts.keys())
            for i in range(len(unique_tokens)):
                for j in range(i + 1, len(unique_tokens)):
                    u, v = unique_tokens[i], unique_tokens[j]
                    kw_coocc[(u, v)] += min(token_counts[u], token_counts[v])

        for (u, v), w in kw_coocc.items():
            graph_data["edges"].append({"source": u, "target": v, "weight": w, "type": "kw-kw"})
        for (u, v), w in sub_coocc.items():
            graph_data["edges"].append({"source": u, "target": v, "weight": w, "type": "sub-sub"})
        for (s, k), w in sub_kw_weight.items():
            graph_data["edges"].append({"source": s, "target": k, "weight": w, "type": "sub-kw"})
        for src in final_source_data:
            for d in src.get("deputies", []):
                if " — " in d:
                    dn, fc = d.split(" — ", 1)
                    graph_data["edges"].append(
                        {"source": dn.strip(), "target": fc.strip(), "weight": 1, "type": "sub-fac"})

        # Удаляем изолированные узлы до фильтрации
        connected_nodes = set()
        for e in graph_data["edges"]:
            connected_nodes.add(e["source"])
            connected_nodes.add(e["target"])
        graph_data["nodes"] = [n for n in graph_data["nodes"] if n["id"] in connected_nodes]

        # Загружаем состояние фильтров с диска (исправляет NameError)
        filter_state = load_filter_state_from_disk(self.db_path)

        TYPE_TO_CAT = {"keyword": "keywords", "ngram": "ngrams", "subject": "deputies", "faction": "factions"}
        nodes_by_category = defaultdict(set)
        for node in graph_data["nodes"]:
            cat = TYPE_TO_CAT.get(node.get("type"), node.get("type"))
            if cat in filter_state:
                nodes_by_category[cat].add(node["id"])

        allowed_nodes = set(n['id'] for n in graph_data['nodes'])
        for cat, state in filter_state.items():
            if not state['selected'] and not state['mode']:
                continue

            cat_nodes = {n['id'] for n in graph_data['nodes'] if TYPE_TO_CAT.get(n['type']) == cat}
            if state['mode']:  # Белый список: оставляем только выбранные из этой категории
                allowed_nodes = (allowed_nodes - cat_nodes) | (cat_nodes & state['selected'])
            else:  # Чёрный список: убираем выбранные из этой категории
                allowed_nodes -= state['selected']

        # Финальное применение фильтрации к структуре графа
        graph_data["nodes"] = [n for n in graph_data["nodes"] if n["id"] in allowed_nodes]
        graph_data["edges"] = [e for e in graph_data["edges"] if
                               e["source"] in allowed_nodes and e["target"] in allowed_nodes]

        self._safe_log(
            f"После фильтрации осталось узлов: {len(graph_data['nodes'])}, рёбер: {len(graph_data['edges'])}\n")

        # 5. Дополнительные связи и синхронизация
        if self.viz_params.get("faction_kw_conn", False):
            fac_kw_w = defaultdict(int)
            for src in final_source_data:
                for d in src.get("deputies", []):
                    if " — " in d:
                        _, fac = d.split(" — ", 1)
                        for t, c in src["tokens"].items():
                            fac_kw_w[(fac.strip(), t)] += c
            for (f, k), w in fac_kw_w.items():
                graph_data["edges"].append({"source": f, "target": k, "weight": w, "type": "fac-kw"})

        if self.editor_ref and self.editor_ref.window.winfo_exists() and hasattr(self.editor_ref,
                                                                                 'sync_keywords_from_graph'):
            try:
                self.editor_ref.sync_keywords_from_graph(
                    {n["id"]: n["weight"] for n in graph_data["nodes"] if n["type"] in ("keyword", "ngram")})
            except:
                pass

        # 6. Сохранение и обновление GUI
        self._safe_update_progress(90)
        with open(self.graph_data_path, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, ensure_ascii=False, indent=2)

        self.graph_built = True
        self._safe_log("Граф построен.\n")
        self._safe_update_status("Граф построен. Доступна визуализация.")
        self.visualize_btn.config(state=tk.NORMAL)
        self.stats_export_btn.config(state=tk.NORMAL)
        self._safe_update_progress(95)
        self.viz_params_btn.config(state=tk.NORMAL)
        self.build_btn.config(state=tk.NORMAL)
        self.stats_export_btn.config(state=tk.NORMAL)
        self._safe_update_progress(100)
        self.cancel_btn.config(state=tk.DISABLED)

    # --- НОВАЯ ЛОГИКА: Визуализация графа ---
    def _open_source_details(self, source_name):
        """Открывает сведения об источнике, читая данные с диска (для актуальности)."""
        from gui.editors.sources_editor import SourceDetailsWindow

        lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
        json_path = os.path.join(lexemes_dir, f"{source_name}.json")

        # 1. Пытаемся прочитать с диска
        src_dict = None
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                src_dict = {
                    "name": source_name,
                    "file": f"{source_name}.txt",
                    "url": data.get("url", " "),
                    "date": data.get("date", " "),
                    "deputies": data.get("deputies", []),
                    "description": data.get("description", " ")
                }
            except Exception:
                pass

        # 2. Фоллбэк на кэш, если файла нет (например, временный кэш)
        if src_dict is None:
            cache_data = self.sources_cache.get(source_name, {})
            src_dict = {
                "name": source_name,
                "file": f"{source_name}.txt",
                "url": cache_data.get("url", " "),
                "date": cache_data.get("date", " "),
                "deputies": cache_data.get("deputies", []),
                "description": cache_data.get("description", " ")
            }

        SourceDetailsWindow(self.window, self.db_path, src_dict)

    def _visualize_graph(self):
        if not self.graph_built: return

        # 1. Загрузка параметров
        params_file = os.path.join(self.db_path, ".viz_params.json")
        if os.path.exists(params_file):
            try:
                with open(params_file, 'r', encoding='utf-8') as f:
                    self.viz_params.update(json.load(f))
            except Exception:
                pass

        self._safe_update_status("Визуализация...")
        try:
            with open(self.graph_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self._safe_log(f"Ошибка загрузки данных графа: {e}\n")
            return

        # 🔹 Фильтрация узлов по упоминаниям (НОВОЕ)
        kw_min = self.viz_params.get("kw_min", 1)
        kw_max = self.viz_params.get("kw_max", 999999)
        sub_min = self.viz_params.get("sub_min", 1)
        sub_max = self.viz_params.get("sub_max", 999999)
        fac_min = self.viz_params.get("fac_min", 1)
        fac_max = self.viz_params.get("fac_max", 999999)

        valid_node_ids = set()
        filtered_nodes = []
        for n in data["nodes"]:
            w = n.get("weight", 0)
            n_type = n.get("type", "keyword")
            keep = False

            if n_type in ("keyword", "ngram"):
                if kw_min <= w <= kw_max: keep = True
            elif n_type == "subject":
                if sub_min <= w <= sub_max: keep = True
            elif n_type == "faction":
                if fac_min <= w <= fac_max: keep = True
            else:
                keep = True  # Fallback для неизвестных типов

            if keep:
                filtered_nodes.append(n)
                valid_node_ids.add(n["id"])

        # Оставляем только рёбра между видимыми узлами
        filtered_edges = [e for e in data["edges"] if e["source"] in valid_node_ids and e["target"] in valid_node_ids]
        data["nodes"] = filtered_nodes
        data["edges"] = filtered_edges

        G = nx.Graph()
        for n in data["nodes"]:
            w = n.get("weight")
            if w is None: w = 1
            G.add_node(n["id"], type=n.get("type", "keyword"), weight=int(w))
        for e in data["edges"]:
            w = e.get("weight", 1) if e.get("type") != "sub-fac" else 1
            G.add_edge(e["source"], e["target"], weight=w, type=e["type"])

        center_type = self.viz_params.get("center_type", "Общий вид")
        center_node = self.viz_params.get("center_node", "  ").strip()

        draw_G = G
        pos = {}

        ego_nodes = set()
        if center_type == "Общий вид":
            ego_nodes = set(G.nodes())
        elif center_node and center_node in G:
            ego_nodes.add(center_node)
            if center_type == "Портрет слова":
                ego_nodes.update(n for n in G.neighbors(center_node))
                for nb in list(ego_nodes):
                    if G.nodes[nb].get('type') == 'subject':
                        ego_nodes.update(n for n in G.neighbors(nb) if G.nodes[n].get('type') == 'faction')
            elif center_type == "Портрет субъекта":
                words = [n for n in G.neighbors(center_node) if G.nodes[n].get('type') in ('keyword', 'ngram')]
                facs = [n for n in G.neighbors(center_node) if G.nodes[n].get('type') == 'faction']
                ego_nodes.update(words + facs)
            elif center_type == "Портрет фракции":
                subjects = [n for n in G.neighbors(center_node) if G.nodes[n].get('type') == 'subject']
                ego_nodes.update(subjects)
                for sub in subjects:
                    ego_nodes.update(n for n in G.neighbors(sub) if G.nodes[n].get('type') in ('keyword', 'ngram'))

        draw_G = G.subgraph(ego_nodes).copy() if ego_nodes else G.copy()

        # 🔹 ПРИМЕНЕНИЕ ФИЛЬТРОВ ПЕРЕД ОТРИСОВКОЙ
        filter_state = load_filter_state_from_disk(self.db_path)
        allowed_nodes = set(draw_G.nodes())

        for cat, fs in filter_state.items():
            is_white = fs.get("mode", False)
            selected = fs.get("selected", set())
            if not selected: continue
            if is_white:
                allowed_nodes &= selected
            else:
                allowed_nodes -= selected

        removed = [n for n in draw_G.nodes() if n not in allowed_nodes]
        draw_G.remove_nodes_from(removed)

        # 2. ПРОВЕРКА КЭША ПОЗИЦИЙ + УЧЁТ ВЫБРАННОЙ СТРУКТУРЫ
        layout_type = self.viz_params.get("layout_type", "Сило-ориентированный")
        current_nodes = tuple(sorted(draw_G.nodes()))
        current_edges = tuple(sorted([tuple(sorted(e)) for e in draw_G.edges()]))
        current_hash = hash((center_type, center_node, layout_type, current_nodes, current_edges))

        cached_hash = getattr(self, '_cached_graph_hash', None)
        cached_pos = getattr(self, '_cached_positions', None)

        sp_mode = self.viz_params.get("spacing_mode", "fixed")
        sp_fixed = self.viz_params.get("spacing_fixed", 0.6)
        sp_base = self.viz_params.get("spacing_dynamic_base", 0.4)
        sp_factor = self.viz_params.get("spacing_dynamic_factor", 0.015)

        if sp_mode == "dynamic":
            weights = [draw_G.nodes[n].get("weight", 1) for n in draw_G.nodes()]
            max_w = max(weights) if weights else 1
            k_val = sp_base + (max_w * sp_factor)
            k_val = min(k_val, 4.0)
        else:
            k_val = sp_fixed

        if cached_hash == current_hash and cached_pos:
            pos = cached_pos.copy()
            self._safe_log("Восстановлены сохраненные позиции узлов.\n")
        else:
            if layout_type == "Круговой":
                pos = nx.circular_layout(draw_G)
            elif layout_type == "Кольцевой":
                w_groups = defaultdict(list)
                for n in draw_G.nodes(): w_groups[draw_G.nodes[n].get('weight', 1)].append(n)
                pos = nx.shell_layout(draw_G, nlist=[w_groups[w] for w in sorted(w_groups.keys(), reverse=True)])
            else:
                if center_node and center_node in draw_G:
                    init_pos = {center_node: (0.0, 0.0)}
                    pos = nx.spring_layout(draw_G, pos=init_pos, fixed=[center_node], k=k_val, iterations=100)
                else:
                    pos = nx.kamada_kawai_layout(draw_G, scale=k_val * 2.0)
            self._cached_graph_hash = current_hash
            self._cached_positions = pos.copy()

        # 3. Фильтрация рёбер
        if not self.viz_params.get("kw_conn", True):
            kw_edges = [(u, v) for u, v, d in draw_G.edges(data=True) if d.get("type") == "kw-kw"]
            draw_G.remove_edges_from(kw_edges)
        elif center_type == "Портрет слова" and center_node and center_node in draw_G:
            edges_to_remove = [(u, v) for u, v, d in draw_G.edges(data=True) if
                               d.get("type") == "kw-kw" and u != center_node and v != center_node]
            draw_G.remove_edges_from(edges_to_remove)

        # 4. Стили
        node_colors_map = self.viz_params.get("node_colors", {})
        edge_colors_map = self.viz_params.get("edge_colors", {})
        font_cfg = self.viz_params.get("font", {})
        font_size = font_cfg.get("size", 8)
        font_color = font_cfg.get("color", "#000000")
        font_weight = font_cfg.get("weight", "normal")
        off_x = self.viz_params.get("offsets", {}).get("x", 0.0)
        off_y = self.viz_params.get("offsets", {}).get("y", 0.0)

        fig, ax = plt.subplots(figsize=(14, 10))

        # 🔹 ИСПРАВЛЕНИЕ: Восстанавливаем логику сохранения/восстановления масштаба внутри draw()
        def draw():
            # Сохраняем текущие границы (Zoom level)
            current_xlim = ax.get_xlim()
            current_ylim = ax.get_ylim()

            ax.clear()
            node_sizes = [max(100, draw_G.nodes[n].get("weight", 1) * 30) for n in draw_G.nodes()]
            node_colors = []

            center_type = self.viz_params.get("center_type", "Общий вид")
            center_node = self.viz_params.get("center_node", " ").strip()
            center_color = self.viz_params.get("center_word_color", "#FFD700")

            for n in draw_G.nodes():
                t = draw_G.nodes[n].get('type', 'keyword')
                if center_type == "Портрет слова" and n == center_node:
                    c = center_color
                else:
                    c = node_colors_map.get('keyword' if t == 'ngram' else t, 'lightyellow')
                node_colors.append(c)

            nx.draw_networkx_nodes(draw_G, pos, node_size=node_sizes, node_color=node_colors, alpha=0.85,
                                   edgecolors="gray", ax=ax)

            if self.show_edges_var.get():
                edge_types = defaultdict(list)
                for u, v, d in draw_G.edges(data=True):
                    edge_types[d.get("type", "default")].append((u, v))
                for e_type, edges in edge_types.items():
                    color = edge_colors_map.get(e_type, "gray")
                    width = [max(0.5, draw_G.edges[e].get("weight", 1) * 0.3) for e in edges]
                    nx.draw_networkx_edges(draw_G, pos, edgelist=edges, width=width, alpha=0.6, edge_color=color, ax=ax)

            if self.viz_params.get("smart_labels", False):
                cx = sum(p[0] for p in pos.values()) / len(pos) if pos else 0.0
                cy = sum(p[1] for p in pos.values()) / len(pos) if pos else 0.0
                label_pos = {}
                base_r = self.viz_params.get("label_base_radius", 0.035)
                mult_r = self.viz_params.get("label_radius_multiplier", 0.003)
                for n in draw_G.nodes():
                    x, y = pos[n]
                    dx, dy = x - cx, y - cy
                    dist = max(0.1, np.hypot(dx, dy))
                    ux, uy = dx / dist, dy / dist
                    radius = base_r + len(str(n)) * mult_r
                    label_pos[n] = (x + ux * radius, y + uy * radius)
            else:
                label_pos = {n: (pos[n][0] + off_x, pos[n][1] + off_y) for n in draw_G.nodes()}

            node_labels = {n: f"{n}\n[{int(draw_G.nodes[n].get('weight', 0))}]" for n in draw_G.nodes()}
            nx.draw_networkx_labels(draw_G, label_pos, labels=node_labels, font_size=font_size, font_weight=font_weight,
                                    font_color=font_color, ax=ax)
            ax.axis("off")

            # 🔹 Восстанавливаем границы после очистки/перерисовки
            ax.set_xlim(current_xlim)
            ax.set_ylim(current_ylim)

            fig.canvas.draw_idle()

        draw()
        self.show_edges_var.trace_add('write', lambda *args: draw())

        viz_win = tk.Toplevel(self.window)
        viz_win.title("Визуализация графа")
        viz_win.geometry("950x700")

        def on_viz_close():
            self._cached_positions = pos.copy()
            viz_win.destroy()

        viz_win.protocol("WM_DELETE_WINDOW", on_viz_close)

        editor_mode = tk.BooleanVar(value=False)
        top_bar = ttk.Frame(viz_win)
        top_bar.pack(fill=tk.X, pady=2)
        ttk.Checkbutton(top_bar, text="Редактор графа", variable=editor_mode).pack(side=tk.LEFT)
        ttk.Separator(top_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Checkbutton(top_bar, text="Отображать рёбра", variable=self.show_edges_var).pack(side=tk.LEFT, padx=5)

        db_name = os.path.basename(self.db_path)

        def export_graph(fmt):
            initial_file = f"{db_name}_graph.{fmt}" if fmt != "csv" else f"{db_name}_edges.csv"
            path = filedialog.asksaveasfilename(defaultextension=f".{fmt}", initialfile=initial_file,
                                                filetypes=[(fmt.upper(), f"*.{fmt}")])
            if not path: return
            try:
                if fmt == "csv":
                    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                        w = csv.writer(f)
                        w.writerow(["Source", "Target", "Weight", "Type"])
                        for u, v, d in draw_G.edges(data=True): w.writerow(
                            [u, v, d.get('weight', 1), d.get('type', '')])
                else:
                    bg = 'white' if fmt == 'jpg' else None
                    fig.savefig(path, dpi=300, transparent=(fmt == 'png'), bbox_inches='tight', facecolor=bg)
                messagebox.showinfo("Экспорт", "Успешно сохранено.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

        # 🔹 ВОССТАНОВЛЕНИЕ: Кнопка "Подогнать" и её функция
        def fit_to_bounds():
            if not pos: return
            # Собираем все координаты
            x_coords = [p[0] for p in pos.values()]
            y_coords = [p[1] for p in pos.values()]
            if not x_coords or not y_coords: return

            x_min, x_max = min(x_coords), max(x_coords)
            y_min, y_max = min(y_coords), max(y_coords)

            # Вычисляем отступы (padding) ~15% от размера графа
            x_range = (x_max - x_min) * 0.15 if x_max > x_min else 1.0
            y_range = (y_max - y_min) * 0.15 if y_max > y_min else 1.0

            # Применяем новые границы
            ax.set_xlim(x_min - x_range, x_max + x_range)
            ax.set_ylim(y_min - y_range, y_max + y_range)
            fig.canvas.draw_idle()

        fit_to_bounds()
        # 🔹 КНОПКА ПОДГОНКИ
        ttk.Button(top_bar, text="Подогнать", command=fit_to_bounds).pack(side=tk.LEFT, padx=5)
        ttk.Separator(top_bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(top_bar, text="Экспорт JPG", command=lambda: export_graph("jpg")).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="Экспорт PNG", command=lambda: export_graph("png")).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_bar, text="Экспорт CSV", command=lambda: export_graph("csv")).pack(side=tk.LEFT, padx=5)

        canvas = FigureCanvasTkAgg(fig, master=viz_win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(canvas, viz_win)
        toolbar.update()
        ttk.Button(viz_win, text="Закрыть", command=viz_win.destroy).pack(pady=5)

        drag_data = {"node": None, "start_x": 0, "start_y": 0, "orig_pos": (0, 0)}
        pan_state = {"start_x": 0, "start_y": 0, "xlim": None, "ylim": None}

        def on_press(event):
            if event.inaxes != ax: return
            if event.button == 3:
                pan_state["start_x"] = event.xdata;
                pan_state["start_y"] = event.ydata
                pan_state["xlim"] = ax.get_xlim();
                pan_state["ylim"] = ax.get_ylim()
                return
            if not editor_mode.get():
                if event.button == 1 and event.xdata is not None:
                    click_pos = np.array([event.xdata, event.ydata])
                    min_dist, nearest_node = float('inf'), None
                    for node, p in pos.items():
                        d = np.linalg.norm(click_pos - np.array(p))
                        if d < min_dist: min_dist, nearest_node = d, node
                    xlim = ax.get_xlim()
                    if min_dist < (xlim[1] - xlim[0]) * 0.04 and nearest_node:
                        self._show_node_info(viz_win, nearest_node, G)
                return
            if event.button == 1 and event.xdata is not None:
                click_pos = np.array([event.xdata, event.ydata])
                min_dist, nearest_node = float('inf'), None
                for node, p in pos.items():
                    d = np.linalg.norm(click_pos - np.array(p))
                    if d < min_dist: min_dist, nearest_node = d, node
                if min_dist < 0.15:
                    drag_data["node"] = nearest_node
                    drag_data["start_x"], drag_data["start_y"] = event.xdata, event.ydata
                    drag_data["orig_pos"] = pos[nearest_node]

        def on_motion(event):
            if event.inaxes != ax: return

            # 🔹 ИСПРАВЛЕНИЕ: Запоминаем границы перед перемещением узла
            current_xlim = ax.get_xlim()
            current_ylim = ax.get_ylim()

            if pan_state["xlim"] is not None:
                dx = event.xdata - pan_state["start_x"];
                dy = event.ydata - pan_state["start_y"]
                ax.set_xlim(pan_state["xlim"][0] - dx, pan_state["xlim"][1] - dx)
                ax.set_ylim(pan_state["ylim"][0] - dy, pan_state["ylim"][1] - dy)
                fig.canvas.draw_idle()
                return
            if not editor_mode.get(): return
            if drag_data["node"]:
                dx = event.xdata - drag_data["start_x"];
                dy = event.ydata - drag_data["start_y"]
                pos[drag_data["node"]] = (drag_data["orig_pos"][0] + dx, drag_data["orig_pos"][1] + dy)
                draw()
                # 🔹 Восстанавливаем границы после перетаскивания узла
                ax.set_xlim(current_xlim)
                ax.set_ylim(current_ylim)
                fig.canvas.draw_idle()

        def on_release(event):
            self._cached_positions = pos.copy()
            drag_data["node"] = None;
            pan_state["xlim"] = None;
            pan_state["ylim"] = None

        def on_scroll(event):
            if event.inaxes != ax: return
            cur_xlim, cur_ylim = ax.get_xlim(), ax.get_ylim()
            xdata, ydata = event.xdata, event.ydata
            if xdata is None or ydata is None: return
            scale = 0.9 if event.button == 'up' else 1.1
            ax.set_xlim(xdata - (xdata - cur_xlim[0]) * scale, xdata + (cur_xlim[1] - xdata) * scale)
            ax.set_ylim(ydata - (ydata - cur_ylim[0]) * scale, ydata + (cur_ylim[1] - ydata) * scale)
            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('button_press_event', on_press)
        fig.canvas.mpl_connect('motion_notify_event', on_motion)
        fig.canvas.mpl_connect('button_release_event', on_release)
        fig.canvas.mpl_connect('scroll_event', on_scroll)
        self._safe_update_status("Визуализация завершена.")

    def _export_graph(self, fmt, obj):
        try:
            if fmt == "csv":
                path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
                if not path: return
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f)
                    w.writerow(["Source", "Target", "Weight", "Type"])
                    for u, v, d in obj.edges(data=True):
                        w.writerow([u, v, d.get('weight', 1), d.get('type', '')])
                messagebox.showinfo("Экспорт", "CSV успешно сохранён.")
            else:
                path = filedialog.asksaveasfilename(defaultextension=f".{fmt}", filetypes=[(fmt.upper(), f"*.{fmt}")])
                if not path: return
                bg = 'white' if fmt == 'jpg' else None
                obj.savefig(path, dpi=300, transparent=(fmt == 'png'), bbox_inches='tight', facecolor=bg)
                messagebox.showinfo("Экспорт", f"{fmt.upper()} успешно сохранён.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _render_section_with_buttons(self, parent, title, connections, G):
        ttk.Label(parent, text=title, font=("Arial", 10, "bold")).pack(anchor=tk.W, padx=10, pady=(5, 2))
        if not connections:
            ttk.Label(parent, text="Нет связей.", foreground="gray").pack(anchor=tk.W, padx=20)
            return

        for target, weight, node_type in connections:
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, padx=10, pady=1)

            if weight > 0:
                ttk.Label(frame, text=str(int(weight)), width=5, anchor=tk.CENTER).pack(side=tk.RIGHT)

            btn = ttk.Button(frame, text=target)
            btn.pack(fill=tk.X, side=tk.LEFT)
            # 🔧 ИСПРАВЛЕНИЕ: передаём G явно вместо несуществующего self._viz_G
            btn.bind("<Button-1>", lambda e, t=target: self._show_node_info(self.window, t, G))

    def on_node_click(self, event, G, raw_data):
        if event.inaxes is None or event.xdata is None: return
        click = np.array([event.xdata, event.ydata])
        pos = nx.spring_layout(G)

    def show_node_details(self, node_id, full_graph_data):
        win = tk.Toplevel(self.window)
        win.title(f"Сведения: {node_id}")
        win.geometry("400x500")
        win.grab_set()
        ttk.Label(win, text=node_id, font=("Arial", 12, "bold")).pack(pady=5)

        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        canvas = tk.Canvas(frame)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        sf = ttk.Frame(canvas)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Сбор связей
        conns = defaultdict(list)
        for e in full_graph_data["edges"]:
            if e["source"] == node_id:
                conns[e["target"]].append((e["weight"], e["type"], e["source"]))
            elif e["target"] == node_id:
                conns[e["source"]].append((e["weight"], e["type"], e["target"]))

        # Сортировка и вывод по типам (как в ТЗ)
        self._render_section(sf, conns, node_id, win)

        ttk.Button(win, text="Закрыть", command=win.destroy).pack(pady=10)

    def _show_node_info(self, parent_win, node_id, G):
        self._load_sources_cache()

        # 🔴 ЗАЩИТА: Закрываем старое окно сведений, если оно открыто
        if hasattr(self, '_info_win') and self._info_win.winfo_exists():
            self._info_win.destroy()

        # 🔴 ЗАЩИТА: Если переданный родитель уже уничтожен, используем главное окно
        if not parent_win.winfo_exists():
            parent_win = self.window

        self._info_win = tk.Toplevel(parent_win)
        self._info_win.title(f"Сведения: {node_id}")
        self._info_win.geometry("750x650")
        self._info_win.transient(parent_win)
        self._info_win.grab_set()

        cvs = tk.Canvas(self._info_win)
        sb = ttk.Scrollbar(self._info_win, orient=tk.VERTICAL, command=cvs.yview)
        sf = ttk.Frame(cvs)
        sf.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=sf, anchor="nw")
        cvs.configure(yscrollcommand=sb.set)
        cvs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Label(sf, text=f"Узел: {node_id}", font=("Arial", 11, "bold")).pack(pady=5)
        ttk.Label(sf, text=f"Вес: {G.nodes[node_id].get('weight', 0)}").pack(pady=2)
        ttk.Label(sf, text="Источники:", font=("Arial", 10, "bold")).pack(pady=(10, 2))

        # 🔵 ИСПРАВЛЕННАЯ ЛОГИКА ПОИСКА ИСТОЧНИКОВ (ЕДИНЫЙ ЦИКЛ, БЕЗ ДУБЛЕЙ)
        sources = []
        node_type = G.nodes[node_id].get('type', 'keyword')
        nid_lower = node_id.strip().lower()
        is_ngram = ' ' in node_id

        current_deputies = set()
        dep_file = os.path.join(self.db_path, "deputies.txt")
        if os.path.exists(dep_file):
            try:
                with open(dep_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        parts = line.strip().split('\t')
                        if len(parts) >= 3:
                            full_name = f"{parts[0]} {parts[1]} {parts[2]}".strip()
                            current_deputies.add(full_name)
            except:
                pass

        # Если это N-грамма, лемматизируем её для точного поиска в токенах
        ngram_lemmas = set()
        if is_ngram and MYSTEM_MODEL:
            try:
                lemmas_raw = MYSTEM_MODEL.lemmatize(node_id)
                ngram_lemmas = {l.strip().lower() for l in lemmas_raw if l.strip()}
            except:
                pass

        for src_name, d in self.sources_cache.items():
            tokens = d.get("tokens", {})
            tok_keys_lower = set(k.lower() for k in tokens.keys())
            found = False

            if node_type == 'subject':
                active_deps_in_src = [dep for dep in d.get("deputies", []) if
                                      dep.split(' — ')[0].strip() in current_deputies]
                if any(dep.startswith(node_id) for dep in active_deps_in_src):
                    found = True
            elif node_type == 'faction':
                # Фракция: ищем её в записях депутатов формата "ФИО — Фракция"
                if any(f" — {node_id}" in dep for dep in d.get("deputies", [])):
                    found = True
            else:  # keyword / ngram
                # 1. Точное совпадение
                if nid_lower in tok_keys_lower:
                    found = True
                # 2. Для N-грамм: проверяем леммы или все слова фразы
                elif is_ngram:
                    if ngram_lemmas and ngram_lemmas.issubset(tok_keys_lower):
                        found = True
                    else:
                        # Фоллбэк: все слова фразы есть в токенах источника
                        ngram_words = set(nid_lower.split())
                        if ngram_words.issubset(tok_keys_lower):
                            found = True
                # 3. Фоллбэк для обычных слов: частичное совпадение (кластеризация могла изменить форму)
                else:
                    if any(nid_lower in tk or tk in nid_lower for tk in tok_keys_lower):
                        found = True

            if found:
                if os.path.exists(os.path.join(self.db_path, "lexemes", f"{src_name}.json")):
                    sources.append(src_name)

        sources.sort()

        if not sources:
            ttk.Label(sf, text="Не найдено.", foreground="gray").pack(pady=2)
        else:
            for s in sources:
                ttk.Button(sf, text=s,
                           command=lambda s_name=s: self._open_source_details(s_name)).pack(fill=tk.X,
                                                                                            padx=5,
                                                                                            pady=1)

        # 🔵 ОРИГИНАЛ: Сбор соседей (полностью сохранён)
        ttk.Separator(sf, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        subs, kws, facs = [], [], []
        for nb in G.neighbors(node_id):
            w = G[node_id][nb].get('weight', 1)
            tp = G.nodes[nb].get('type', 'keyword')
            if tp == 'subject':
                subs.append((nb, w, tp))
            elif tp == 'keyword':
                kws.append((nb, w, tp))
            elif tp == 'faction':
                facs.append((nb, w, tp))

        # 🔵 ОРИГИНАЛ: Сортировка связей по весу (от большего к меньшему)
        subs.sort(key=lambda x: x[1], reverse=True)
        kws.sort(key=lambda x: x[1], reverse=True)
        facs.sort(key=lambda x: x[1], reverse=True)

        # 🔵 ОРИГИНАЛ: Отрисовка секций (без изменений)
        self._render_section_with_buttons(sf, "Субъекты", subs, G)
        ttk.Separator(sf, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        self._render_section_with_buttons(sf, "Ключевые слова", kws, G)
        ttk.Separator(sf, orient='horizontal').pack(fill=tk.X, padx=10, pady=5)
        self._render_section_with_buttons(sf, "Фракции", facs, G)
        ttk.Button(sf, text="Закрыть", command=self._info_win.destroy).pack(pady=10)

    def _visualize_thread(self):
        self._safe_update_status("Генерация layout и отрисовка...")
        try:
            with open(self.graph_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self._safe_log(f"Ошибка загрузки данных графа: {e}\n");
            return

        G = nx.Graph()
        color_map = {"keyword": "lightblue", "subject": "lightgreen", "faction": "lightcoral"}
        for n in data["nodes"]: G.add_node(n["id"], type=n.get("type", "keyword"), weight=n.get("weight", 1))
        for e in data["edges"]:
            w = e.get("weight", 1) if e.get("type") != "sub-fac" else 1
            G.add_edge(e["source"], e["target"], weight=w, type=e["type"])

        # --- НОВАЯ ЛОГИКА ЦЕНТРИРОВАНИЯ ---
        center_type = self.viz_params.get("center", "factions")
        offset_x = self.viz_params.get("offset_x", 0.06)
        offset_y = self.viz_params.get("offset_y", 0.04)

        center_nodes = []
        all_nodes = list(G.nodes())

        if center_type == "subjects":
            center_nodes = [n for n in all_nodes if G.nodes[n].get("type") == "subject"]
        elif center_type == "factions":
            center_nodes = [n for n in all_nodes if G.nodes[n].get("type") == "faction"]
        elif center_type == "keywords":
            kw_target = simpledialog.askstring("Центр графа", "Введите ключевое слово для центра:",
                                               parent=self.window)
            if kw_target and kw_target in G:
                center_nodes = [kw_target]
            else:
                # Fallback: если отмена или не найдено, берём самую частотную ключевую лексему
                kw_nodes = sorted([n for n in all_nodes if G.nodes[n].get("type") == "keyword"],
                                  key=lambda x: G.nodes[x].get("weight", 0), reverse=True)
                if kw_nodes: center_nodes = [kw_nodes[0]]

        surrounding_nodes = [n for n in all_nodes if n not in center_nodes]

        # Строим позиции
        pos = {}
        if center_nodes and surrounding_nodes:
            pos = nx.shell_layout(G, nlist=[center_nodes, surrounding_nodes])
        else:
            pos = nx.spring_layout(G, seed=42, k=0.8, iterations=50)
        # --- КОНЕЦ ЛОГИКИ ЦЕНТРИРОВАНИЯ ---
        fig, ax = plt.subplots(figsize=(14, 10))

        node_sizes = [max(100, G.nodes[n].get("weight", 1) * 30) for n in G.nodes()]
        node_colors = [color_map.get(G.nodes[n].get("type", "keyword"), "lightyellow") for n in G.nodes()]
        edge_widths = [max(0.5, G.edges[e].get("weight", 1) * 0.3) for e in G.edges()]

        nx.draw_networkx_nodes(G, pos, node_size=node_sizes, node_color=node_colors, alpha=0.85, edgecolors="gray",
                               ax=ax)
        nx.draw_networkx_edges(G, pos, width=edge_widths, alpha=0.4, edge_color="gray", ax=ax)

        node_labels = {n: f"{n}\n[{G.nodes[n].get('weight', 1)}]" for n in G.nodes()}
        # Применяем пользовательское смещение к подписям
        label_pos = {n: (pos[n][0] + offset_x, pos[n][1] + offset_y) for n in G.nodes()}
        nx.draw_networkx_labels(G, label_pos, labels=node_labels, font_size=7, font_weight="normal", font_color="black",
                                ax=ax)

        edge_labels = {(u, v): str(int(d.get("weight", 1))) for u, v, d in G.edges(data=True) if d.get("weight", 0) > 0}
        if edge_labels: nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8, font_color="gray",
                                                     alpha=0.8, ax=ax)

        ax.set_title("Семантический граф связей", fontsize=14)
        ax.axis("off");
        plt.tight_layout()

        # Встраивание в Tkinter (безопасно через after)
        def show_viz_window():
            viz_win = tk.Toplevel(self.window)
            viz_win.title("Визуализация графа");
            viz_win.geometry("950x700")
            ttk.Label(viz_win, text="🖱️ Зум: колёсико | 📐 Панорама: зажать ЛКМ | 🔍 Меню: кнопки сверху",
                      foreground="gray", font=("Arial", 9)).pack(pady=2)

            canvas = FigureCanvasTkAgg(fig, master=viz_win)
            canvas.draw();
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            toolbar = NavigationToolbar2Tk(canvas, viz_win);
            toolbar.update()
            ttk.Button(viz_win, text="Закрыть", command=viz_win.destroy).pack(pady=5)

            def on_scroll(event):
                if event.inaxes != ax: return
                scale = 0.9 if event.button == 'up' else 1.1
                xdata, ydata = event.xdata, event.ydata
                if xdata is None: return
                ax.set_xlim(xdata - (xdata - ax.get_xlim()[0]) * scale, xdata + (ax.get_xlim()[1] - xdata) * scale)
                ax.set_ylim(ydata - (ydata - ax.get_ylim()[0]) * scale, ydata + (ax.get_ylim()[1] - ydata) * scale)
                fig.canvas.draw_idle()

            fig.canvas.mpl_connect('scroll_event', on_scroll)
            self._safe_update_status("Визуализация завершена.")

        self.window.after(0, show_viz_window)