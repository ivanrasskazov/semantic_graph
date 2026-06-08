import tkinter as tk
from tkinter import ttk,  messagebox
import re
from datetime import datetime

from config import DEFAULTS_DIR
from core.database import load_defaults_settings, save_defaults_settings, _ensure_defaults_dir
from gui.editors.ngrams_editor import NgramsEditorWindow
from gui.editors.stopwords_editor import StopwordsEditorWindow
from gui.editors.deputies_editor import DeputiesEditorWindow
from gui.editors.abbreviations_editor import AbbreviationsEditorWindow
from gui.editors.factions_editor import FactionsEditorWindow
from gui.dialogs.viz_params_dialog import VizParamsWindow

class DefaultParamsWindow:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Параметры по умолчанию")
        self.window.geometry("820x680")
        self.window.transient(parent)
        self.window.grab_set()
        _ensure_defaults_dir()
        self.settings = load_defaults_settings()

        now_str = datetime.now().strftime("%d.%m.%Y")
        for k in ["reg_date", "date_from", "date_to"]:
            if self.settings.get(f"use_device_time_{k}", True):
                self.settings[k] = now_str

        ttk.Label(self.window,
                  text="Редактировать параметры по умолчанию.\nЭти параметры будут применены к новым базам данных.",
                  wraplength=600, justify=tk.CENTER, font=("Arial", 10, "bold")).pack(pady=10, padx=10)

        canvas = tk.Canvas(self.window)
        scrollbar = ttk.Scrollbar(self.window, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)
        scroll_frame.bind("<MouseWheel>", _on_mousewheel)

        self._build_lists_section(scroll_frame)
        self._build_dates_section(scroll_frame)
        self._build_other_section(scroll_frame)

        ttk.Button(scroll_frame, text="Параметры визуализации по умолчанию",
                   command=lambda: VizParamsWindow(self.window, None, None, save_to_defaults=True)).pack(pady=10)
        ttk.Button(scroll_frame, text="Сохранить и закрыть", command=self._save_and_close).pack(pady=10)

    def _validate(self):
        # Проверка порога кластеризации
        if hasattr(self, 'thresh_var'):
            if not (0.0 <= self.thresh_var.get() <= 1.0):
                messagebox.showerror("Ошибка", "Порог кластеризации должен быть от 0.00 до 1.00.")
                return False

        # Проверка дат (если отключено "время устройства")
        if hasattr(self, 'date_checks') and hasattr(self, 'date_vars'):
            for key in ["reg_date", "date_from", "date_to"]:
                if not self.date_checks[key].get():
                    val = self.date_vars[key].get()
                    if not re.match(r"^\d{2}\.\d{2}\.\d{4}$", val):
                        messagebox.showerror("Ошибка", f"Неверный формат даты в поле '{key}'. Требуется ДД.ММ.ГГГГ.")
                        return False
        return True

    def _build_lists_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Списки по умолчанию")
        frame.pack(fill=tk.X, padx=10, pady=5)
        lists = [
            ("Список фракций по умолчанию", FactionsEditorWindow),
            ("Список субъектов по умолчанию", DeputiesEditorWindow),
            ("Список стоп-слов по умолчанию", StopwordsEditorWindow),
            ("Список N-грамм по умолчанию", NgramsEditorWindow),
            ("Список обозначений по умолчанию", AbbreviationsEditorWindow)
        ]
        for txt, cls in lists:
            ttk.Button(frame, text=txt, width=40,
                       command=lambda c=cls: c(self.window, DEFAULTS_DIR, is_defaults=True)).pack(pady=2, padx=10)

    def _build_dates_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Даты по умолчанию")
        frame.pack(fill=tk.X, padx=10, pady=5)

        self.date_vars = {}
        self.date_entries = {}
        self.date_checks = {}

        for key, label in [("reg_date", "Дата регистрации по умолчанию"), ("date_from", "Дата от по умолчанию"),
                           ("date_to", "Дата до по умолчанию")]:
            f_row = ttk.Frame(frame)
            f_row.pack(fill=tk.X, padx=5, pady=2)
            ttk.Label(f_row, text=label, width=25, anchor=tk.W).pack(side=tk.LEFT, padx=(5, 0))

            var = tk.StringVar(value=self.settings.get(key, ""))
            use_device = tk.BooleanVar(value=self.settings.get(f"use_device_time_{key}", True))
            self.date_vars[key] = var
            self.date_checks[key] = use_device

            entry = ttk.Entry(f_row, textvariable=var, width=12, state=tk.DISABLED if use_device.get() else tk.NORMAL)
            entry.pack(side=tk.LEFT, padx=2)
            self.date_entries[key] = entry

            # Биндинг форматирования даты
            entry.bind('<KeyRelease>', lambda e, k=key: self._format_date_entry(e, k))
            entry.bind('<BackSpace>', lambda e, k=key: self._handle_backspace(e, k))
            entry.bind('<Delete>', lambda e, k=key: self._format_date_entry(e, k))

            chk = ttk.Checkbutton(f_row, text="Использовать время устройства", variable=use_device,
                                  command=lambda k=key: self._toggle_date_entry(k))
            chk.pack(side=tk.LEFT, padx=5)

    def _build_other_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Другие параметры")
        frame.pack(fill=tk.X, padx=10, pady=5)

        # 1. Порог кластеризации
        ttk.Label(frame, text="Порог кластеризации по умолчанию (0.00 - 1.00):").pack(anchor=tk.W, padx=10, pady=(5, 2))
        self.thresh_var = tk.DoubleVar(value=self.settings.get("threshold", 0.5))
        scale = ttk.Scale(frame, from_=0.0, to=1.0, variable=self.thresh_var, orient=tk.HORIZONTAL)
        scale.pack(fill=tk.X, padx=10, pady=(0, 2))
        self.thresh_label = ttk.Label(frame, text=f"{self.thresh_var.get():.2f}")
        self.thresh_label.pack(anchor=tk.W, padx=10)
        scale.configure(command=lambda v: self.thresh_label.config(text=f"{float(v):.2f}"))

        # 2. Инвертировать период
        self.invert_var = tk.BooleanVar(value=self.settings.get("invert_period", False))
        ttk.Checkbutton(frame, text="Инвертировать период по умолчанию",
                        variable=self.invert_var).pack(anchor=tk.W, padx=10, pady=10)

    def _toggle_date_entry(self, key):
        if self.date_checks[key].get():
            self.date_entries[key].config(state=tk.DISABLED)
            self.date_vars[key].set(datetime.now().strftime("%d.%m.%Y"))
        else:
            self.date_entries[key].config(state=tk.NORMAL)

    def _format_date_entry(self, event, key):
        val = self.date_vars[key].get().replace("  ", "")
        val = re.sub(r'[^\d.]', '', val)
        parts = val.split('.')
        clean = ''.join(parts)
        res = ""
        for i, ch in enumerate(clean):
            if i in (2, 4) and i < len(clean): res += "."
            res += ch
        if len(res) > 10: res = res[:10]
        self.date_vars[key].set(res)

    def _handle_backspace(self, event, key):
        self.window.after(10, lambda: self._format_date_entry(event, key))

    def _save_and_close(self):
        if not self._validate(): return

        # Формируем словарь только из существующих и актуальных полей
        data = {
            "threshold": self.thresh_var.get() if hasattr(self, 'thresh_var') else 0.5,
            "invert_period": self.invert_var.get() if hasattr(self, 'invert_var') else False,
            "viz_center_type": "Общий вид",
            "viz_center_node": ""
        }

        # Сохраняем даты и флаги времени устройства
        if hasattr(self, 'date_vars') and hasattr(self, 'date_checks'):
            for key in ["reg_date", "date_from", "date_to"]:
                data[key] = self.date_vars[key].get()
                data[f"use_device_time_{key}"] = self.date_checks[key].get()

        save_defaults_settings(data)
        self.window.destroy()