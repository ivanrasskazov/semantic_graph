import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import json

# Импорты путей и констант
from config import FACTIONS_FILE_NAME, DEPUTIES_FILE_NAME, LEXEMES_DIR_NAME, DEFAULTS_DIR, SYSTEM_FACTIONS

try:
    from gui.editors.sources_editor import SourceDetailsWindow
except ImportError:
    SourceDetailsWindow = None

class FactionDetailsWindow:
    """Окно с детальной информацией о фракции."""

    def __init__(self, parent, faction_name, db_path, on_update_callback=None):
        self.parent = parent
        self.faction_name = faction_name
        self.db_path = db_path
        self.on_update_callback = on_update_callback
        self.edit_mode = False
        self.desc_text_content = " "

        # 🔹 Заглушка для системных фракций
        if faction_name in SYSTEM_FACTIONS and not self.desc_text_content.strip():
            self.desc_text_content = "Это системная фракция. Она необходима для работы программы и не может быть удалена или изменена."

        # Инициализация списков до отрисовки UI
        self.faction_members = []
        self.faction_sources = []
        self.faction_dates = []

        self.window = tk.Toplevel(parent)
        self.window.title(f"Сведения о фракции: {faction_name}")
        self.window.geometry("650x600")
        self.window.transient(parent)
        self.window.grab_set()

        self._build_ui()
        self._load_stats()

    def _build_ui(self):
        main = ttk.Frame(self.window, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # Заголовок (Название фракции)
        ttk.Label(main, text="Название фракции: ", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.ent_name = ttk.Entry(main, width=50)  # 🔹 Убрали state="readonly" при создании
        self.ent_name.insert(0, self.faction_name)  # 🔹 Теперь вставка сработает
        self.ent_name.config(state="readonly")  # 🔹 Делаем readonly после вставки
        self.ent_name.pack(fill=tk.X, pady=(0, 15))

        # Статистика
        stats_frame = ttk.LabelFrame(main, text="Статистика базы данных", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 15))
        self.lbl_sources = ttk.Label(stats_frame, text="Источники: ...")
        self.lbl_sources.pack(anchor=tk.W)
        self.lbl_subjects = ttk.Label(stats_frame, text="Субъекты: ...")
        self.lbl_subjects.pack(anchor=tk.W)
        self.lbl_period = ttk.Label(stats_frame, text="Период: ...")
        self.lbl_period.pack(anchor=tk.W)

        # Описание
        ttk.Label(main, text="Описание: ", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(10, 0))
        desc_frame = ttk.Frame(main)
        desc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.text_desc = tk.Text(desc_frame, height=6, wrap=tk.WORD, font=("Segoe UI", 9))
        sb_desc = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=self.text_desc.yview)
        self.text_desc.configure(yscrollcommand=sb_desc.set)
        self.text_desc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_desc.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_desc.insert(tk.END, self.desc_text_content)
        self.text_desc.config(state="disabled")  # По умолчанию только чтение

        # Кнопки
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)

        self.btn_sources = ttk.Button(btn_frame, text="Источники", command=self._show_sources)
        self.btn_sources.pack(side=tk.LEFT, padx=5)

        self.btn_subjects = ttk.Button(btn_frame, text="Субъекты", command=self._show_subjects)
        self.btn_subjects.pack(side=tk.LEFT, padx=5)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Редактирование и закрытие
        self.btn_edit = ttk.Button(btn_frame, text="Редактировать", command=self._toggle_edit)
        self.btn_edit.pack(side=tk.LEFT, padx=5)

        # 🔹 Блокировка для системных фракций
        if self.faction_name in SYSTEM_FACTIONS:
            self.btn_edit.config(state=tk.DISABLED)
            self._setup_tooltip(self.btn_edit, "Системную фракцию невозможно редактировать.")

        ttk.Button(btn_frame, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT)

    def _setup_tooltip(self, widget, text):
        """Простая всплывающая подсказка при наведении."""
        tooltip = None

        def show(e):
            nonlocal tooltip
            if not tooltip:
                x, y, _, _ = widget.bbox("insert")
                x += widget.winfo_rootx() + 25
                y += widget.winfo_rooty() + 25
                tooltip = tk.Toplevel(widget)
                tooltip.wm_overrideredirect(True)
                tooltip.wm_geometry(f"+{x}+{y}")
                tk.Label(tooltip, text=text, bg="#ffffe0", relief="solid", borderwidth=1,
                         font=("tahoma", 8, "normal")).pack(ipadx=2, ipady=1)

        def hide(e):
            nonlocal tooltip
            if tooltip: tooltip.destroy(); tooltip = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _load_stats(self):
        # ─────────────────────────────────────────────────────────────
        # 1. Загружаем описание из factions.txt
        # ─────────────────────────────────────────────────────────────
        factions_file = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        loaded_desc = " "
        search_name = self.faction_name.split('@')[0].strip()
        if os.path.exists(factions_file):
            with open(factions_file, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    clean = line.strip()
                    if not clean: continue
                    file_name = clean.split('@')[0].strip()
                    if file_name == search_name:
                        if '@' in clean:
                            loaded_desc = clean.split('@', 1)[1].replace('\\n', '\n')
                        break

        # Обработка системных фракций
        if self.faction_name in SYSTEM_FACTIONS:
            if not loaded_desc.strip():
                loaded_desc = "Это системная фракция. Она необходима для работы программы и не может быть удалена или изменена."
            self.btn_edit.config(state=tk.DISABLED)
            self._setup_tooltip(self.btn_edit, "Системную фракцию невозможно редактировать.")
        else:
            self.btn_edit.config(state="normal")

        # Обновляем текстовое поле описания
        self.text_desc.config(state="normal")
        self.text_desc.delete("1.0", tk.END)
        self.text_desc.insert("1.0", loaded_desc)
        if not self.edit_mode:
            self.text_desc.config(state="disabled")
        self.desc_text_content = loaded_desc

        # ─────────────────────────────────────────────────────────────
        # 2. Собираем субъектов фракции из deputies.txt
        # ─────────────────────────────────────────────────────────────
        self.faction_members.clear()
        deputies_file = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        if os.path.exists(deputies_file):
            with open(deputies_file, 'r', encoding='utf-8-sig') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 4:
                        # Извлекаем имя фракции (без описания) для сравнения
                        dep_faction = parts[3].split('@')[0].strip()
                        if dep_faction == self.faction_name:
                            fio = f"{parts[0]} {parts[1]} {parts[2]}".strip()
                            self.faction_members.append(fio)

        # ─────────────────────────────────────────────────────────────
        # 3. Собираем ИСТОЧНИКИ и ДАТЫ из lexemes/*.json
        # ─────────────────────────────────────────────────────────────
        sources_set = set()
        dates_list = []
        lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)

        if os.path.exists(lexemes_dir):
            for fname in os.listdir(lexemes_dir):
                if fname.endswith('.json'):
                    try:
                        with open(os.path.join(lexemes_dir, fname), 'r', encoding='utf-8') as jf:
                            data = json.load(jf)
                        deputies_in_source = data.get('deputies', [])
                        for dep_str in deputies_in_source:
                            # Ищем вхождение " — Фракция" (с тире) в строке депутата
                            if f" — {self.faction_name}" in dep_str:
                                sources_set.add(fname.replace('.json', '.txt'))
                                if 'date' in data and data['date']:
                                    dates_list.append(data['date'])
                                break  # Достаточно одного совпадения на файл
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue  # Пропускаем битые файлы

        self.faction_sources = sorted(list(sources_set))
        self.faction_dates = sorted(dates_list)

        # ─────────────────────────────────────────────────────────────
        # 4. Обновление интерфейса со статистикой
        # ─────────────────────────────────────────────────────────────
        self.lbl_sources.config(text=f"Источники: {len(self.faction_sources)}")
        self.lbl_subjects.config(text=f"Субъекты: {len(self.faction_members)}")
        if self.faction_dates:
            self.lbl_period.config(text=f"Период: {self.faction_dates[0]} — {self.faction_dates[-1]}")
        else:
            self.lbl_period.config(text="Период: Не указан")

    def _show_sources(self):
        """Открывает окно со списком источников фракции + поиск."""
        src_win = tk.Toplevel(self.window)
        src_win.title(f"Источники: {self.faction_name}")
        src_win.geometry("400x400")
        src_win.transient(self.window)
        src_win.grab_set()

        ttk.Label(src_win, text="Поиск источников:").pack(anchor=tk.W, padx=5, pady=(5, 0))
        search_var = tk.StringVar()
        ttk.Entry(src_win, textvariable=search_var).pack(fill=tk.X, padx=5, pady=2)

        canvas_frame = ttk.Frame(src_win)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas = tk.Canvas(canvas_frame)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def render_list():
            for w in scroll_frame.winfo_children(): w.destroy()
            query = search_var.get().lower()
            if not self.faction_sources:
                # 🔹 НОВОЕ: Сообщение если источников нет
                ttk.Label(scroll_frame, text="Источники не найдены", foreground="gray").pack(pady=20)
                return
            for src in self.faction_sources:
                if query in src.lower():
                    btn = ttk.Button(scroll_frame, text=src, width=55)
                    btn.pack(fill=tk.X, padx=5, pady=1)
                    try:
                        from gui.editors.sources_editor import SourceDetailsWindow
                        btn.config(
                            command=lambda s=src: SourceDetailsWindow(src_win, self.db_path, s.replace('.txt', '')))
                    except ImportError:
                        btn.config(state=tk.DISABLED, text=f"{src} (нет модуля)")

        search_var.trace_add('write', lambda *a: render_list())
        render_list()

    def _show_subjects(self):
        subj_win = tk.Toplevel(self.window)
        subj_win.title(f"Субъекты: {self.faction_name}")
        subj_win.geometry("480x400")
        subj_win.transient(self.window)
        subj_win.grab_set()

        ttk.Label(subj_win, text="Поиск субъектов:").pack(anchor=tk.W, padx=10, pady=(5, 0))
        search_var = tk.StringVar()
        ttk.Entry(subj_win, textvariable=search_var).pack(fill=tk.X, padx=10, pady=(0, 5))

        canvas_frame = ttk.Frame(subj_win)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        canvas = tk.Canvas(canvas_frame)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        from gui.editors.deputies_editor import DeputyDetailsWindow

        # Внутри FactionDetailsWindow._show_subjects()
        class StubDeputyEditor:
            """Минимальная, но рабочая реализация редактора для открытия сведений из фракций."""

            def __init__(self, db_path):
                self.db_path = db_path
                self.deputies_descriptions = {}
                self.original_deputies = []
                self.save_deputies = lambda: None
                self._load_db()

            def _load_db(self):
                dep_file = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
                if not os.path.exists(dep_file): return
                with open(dep_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        p = line.strip().split('\t')
                        if len(p) >= 4:
                            surname, name, patronymic, raw_faction = p
                            faction = raw_faction.split('@')[0].strip()
                            fio = f"{surname} {name} {patronymic}".strip()
                            self.original_deputies.append({
                                "display": f"{fio} — {faction}",
                                "faction": faction,
                                "parts": p
                            })

            def _refresh_listbox(self):
                pass

            def _get_subject_stats(self, subject_name, faction):
                sources, dates = [], []
                lex_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
                if not os.path.exists(lex_dir): return sources, dates
                norm_target = ' '.join(subject_name.split()).strip().lower().replace('ё', 'е')

                for fname in os.listdir(lex_dir):
                    if not fname.endswith('.json'): continue
                    try:
                        with open(os.path.join(lex_dir, fname), 'r', encoding='utf-8') as jf:
                            data = json.load(jf)
                        for dep_str in data.get('deputies', []):
                            if ' — ' not in dep_str: continue
                            dep_name = dep_str.split(' — ', 1)[0].strip().lower().replace('ё', 'е')
                            if norm_target == dep_name or norm_target in dep_name:
                                sources.append(fname.replace('.json', '.txt'))
                                if data.get('date'): dates.append(data['date'])
                                break
                    except:
                        pass
                return sources, sorted(dates)

        helper = StubDeputyEditor(self.db_path)

        def render():
            for w in scroll_frame.winfo_children(): w.destroy()
            q = search_var.get().lower()
            if not self.faction_members:
                ttk.Label(scroll_frame, text="Субъекты не найдены", foreground="gray").pack(pady=20)
                return
            for name in self.faction_members:
                if q in name.lower():
                    btn = ttk.Button(scroll_frame, text=name, width=55)
                    btn.pack(fill=tk.X, padx=5, pady=2)
                    if DeputyDetailsWindow:
                        btn.config(command=lambda n=name: DeputyDetailsWindow(subj_win, helper, f"{n} — {self.faction_name}"))
                    else:
                        btn.config(state=tk.DISABLED)

        search_var.trace_add('write', lambda *a: render())
        render()

    def _toggle_edit(self):
        if self.faction_name in SYSTEM_FACTIONS:
            messagebox.showwarning("Доступ запрещён", "Редактирование системной фракции невозможно.")
            return
        if not self.edit_mode:
            self.edit_mode = True
            # 🔹 Сначала разблокируем, потом фокус
            self.ent_name.config(state="normal")
            self.text_desc.config(state="normal")  # 🔹 Ключевая строка
            self.text_desc.update()  # 🔹 Принудительное обновление виджета
            self.btn_edit.config(text="Сохранить")
            self.ent_name.focus_set()
            self.ent_name.select_range(0, tk.END)
        else:
            self._save_changes()

    def _save_changes(self):
        new_name = self.ent_name.get().strip()
        raw_desc = self.text_desc.get("1.0", tk.END)
        # Tkinter добавляет \n в конец, убираем только его
        new_desc = raw_desc[:-1] if raw_desc.endswith('\n') else raw_desc
        new_desc = new_desc.strip()

        if not new_name:
            messagebox.showwarning("Ошибка", "Название фракции не может быть пустым.")
            return

        # Экранируем переносы для корректного хранения в одной строке .txt
        desc_for_file = new_desc.replace('\r\n', '\\n').replace('\n', '\\n')
        line_to_save = f"{new_name}@{desc_for_file}" if desc_for_file else new_name

        factions_file = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        try:
            with open(factions_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(factions_file, 'w', encoding='utf-8') as f:
                updated = False
                for line in lines:
                    file_name = line.split('@')[0].strip()
                    if file_name == self.faction_name:
                        f.write(line_to_save + '\n')
                        updated = True
                    else:
                        f.write(line)
                if not updated:
                    f.write(line_to_save + '\n')
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить factions.txt: {e}")
            return

        # Если имя изменилось, обновляем привязку у субъектов
        if new_name != self.faction_name:
            deputies_file = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
            if os.path.exists(deputies_file):
                try:
                    with open(deputies_file, 'r', encoding='utf-8') as f:
                        dep_lines = f.readlines()
                    with open(deputies_file, 'w', encoding='utf-8') as f:
                        for line in dep_lines:
                            parts = line.strip().split('\t')
                            if len(parts) >= 4:
                                dep_faction = parts[3].split('@')[0].strip()
                                if dep_faction == self.faction_name:
                                    old_desc = parts[3].split('@', 1)[1] if '@' in parts[3] else ""
                                    parts[3] = f"{new_name}@{old_desc}" if old_desc else new_name
                                    f.write('\t'.join(parts) + '\n')
                                else:
                                    f.write(line)
                            else:
                                f.write(line)
                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось обновить deputies.txt: {e}")

        # 🔹 Обновляем состояние ТЕКУЩЕГО окна без перезагрузки
        self.faction_name = new_name
        self.window.title(f"Сведения: {new_name}")
        self.edit_mode = False
        self.ent_name.config(state="readonly")

        self.text_desc.config(state="normal")
        self.text_desc.delete("1.0", tk.END)
        self.text_desc.insert("1.0", new_desc)
        self.text_desc.config(state="disabled")
        self.desc_text_content = new_desc

        self.btn_edit.config(text="Редактировать")

        # 🔹 КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: обновляем родительский список через коллбек, а не self._refresh_list()
        if self.on_update_callback:
            self.on_update_callback()

        messagebox.showinfo("Успех", "Изменения сохранены.")

    def _refresh_list(self):
        self.tree_factions.delete(*self.tree_factions.get_children())
        for f in self.factions:
            # ВАЖНО: Вставляем только имя. Если нужно отображать превью описания,
            # сделайте это в отдельном столбце, а не склеивайте строки.
            self.tree_factions.insert("", "end", values=(f['name'],))

    def _clear_form(self):
        self.ent_name.delete(0, tk.END)
        self.text_desc.delete("1.0", tk.END)
        self.edit_index = None
        self.btn_edit.config(text="Добавить")

    def _edit_faction(self):
        """Этот метод теперь не используется напрямую, так как редактирование происходит через _toggle_edit,
        но оставлен для совместимости или если потребуется вызвать диалог."""
        pass

    def _update_faction_in_db(self, new_name):
        """Обновляет имя фракции в factions.txt и в deputies.txt."""
        # 1. Обновить factions.txt
        factions_file = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        try:
            with open(factions_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(factions_file, 'w', encoding='utf-8') as f:
                for line in lines:
                    f.write(new_name + '\n' if line.strip() == self.faction_name else line)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить factions.txt: {e}")
            return

        # 2. Обновить deputies.txt (4-я колонка)
        deputies_file = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        if os.path.exists(deputies_file):
            try:
                with open(deputies_file, 'r', encoding='utf-8') as f:
                    dep_lines = f.readlines()
                with open(deputies_file, 'w', encoding='utf-8') as f:
                    for line in dep_lines:
                        parts = line.strip().split('\t')
                        if len(parts) == 4 and parts[3].strip() == self.faction_name:
                            parts[3] = new_name
                        f.write('\t'.join(parts) + '\n')
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось обновить deputies.txt: {e}")

class FactionsEditorWindow:
    def __init__(self, parent, db_path, is_defaults=False):
        self.parent = parent
        self.db_path = db_path
        self.changes_made = False
        self.is_defaults = is_defaults

        # Путь для описаний фракций
        self.desc_file = os.path.join(self.db_path, "factions_desc.json")
        self.factions_descriptions = {}
        if os.path.exists(self.desc_file):
            try:
                with open(self.desc_file, 'r', encoding='utf-8') as f:
                    self.factions_descriptions = json.load(f)
            except:
                pass

        self.window = tk.Toplevel(parent)
        self.window.title("Список фракций")
        self.window.geometry("880x550")
        self.window.transient(parent)
        self.window.grab_set()

        text_frame = ttk.Frame(self.window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.listbox = tk.Listbox(text_frame)
        scrollbar_y = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar_y.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.bind('<Delete>', lambda e: self.delete_selected())

        self.factions_file_path = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        self.factions = []

        if os.path.exists(self.factions_file_path):
            with open(self.factions_file_path, 'r', encoding='utf-8') as f:
                # 🔹 ИСПРАВЛЕНИЕ: читаем файл, но сразу отбрасываем часть после '@'
                raw_lines = [line.strip() for line in f if line.strip()]
                self.factions = [line.split('@')[0].strip() for line in raw_lines if line.split('@')[0].strip()]

        # 🔹 СОРТИРОВКА: Системные фракции первыми
        sorted_system = sorted([f for f in self.factions if f in SYSTEM_FACTIONS])
        sorted_others = sorted([f for f in self.factions if f not in SYSTEM_FACTIONS])
        self.factions = sorted_system + sorted_others

        for faction in self.factions:
            self.listbox.insert(tk.END, faction)

        self.original_factions = list(self.listbox.get(0, tk.END)) if self.listbox.size() > 0 else []

        self.factions_search_var = tk.StringVar()
        ttk.Label(self.window, text="Поиск фракций:").pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.factions_search_entry = ttk.Entry(self.window, textvariable=self.factions_search_var)
        self.factions_search_entry.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.factions_search_var.trace_add('write', lambda *args: self._search_factions())

        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        self.add_btn = ttk.Button(button_frame, text="Добавить", command=self.add_faction)
        self.add_btn.pack(side=tk.LEFT, padx=5)

        # КНОПКА "СВЕДЕНИЯ" вместо "РЕДАКТИРОВАТЬ"
        self.details_btn = ttk.Button(button_frame, text="Сведения", command=self.show_details)
        self.details_btn.pack(side=tk.LEFT, padx=5)

        self.del_btn = ttk.Button(button_frame, text="Удалить", command=self.delete_selected)
        self.del_btn.pack(side=tk.LEFT, padx=5)

        self.import_btn = ttk.Button(button_frame, text="Импортировать", command=self.import_from_file)
        self.import_btn.pack(side=tk.LEFT, padx=5)
        self.import_btn.bind("<Enter>",
                             lambda e: self.on_import_btn_hover("Каждая фракция должна быть с новой строки."))
        self.import_btn.bind("<Leave>", lambda e: self.hide_tooltip())

        if not self.is_defaults:
            ttk.Button(button_frame, text="Добавить значения по умолчанию", command=self._merge_defaults).pack(
                side=tk.LEFT, padx=5)

        self.delete_all_btn = ttk.Button(button_frame, text="Удалить всё", command=self.delete_all)
        self.delete_all_btn.pack(side=tk.LEFT, padx=5)

        self.close_btn = ttk.Button(button_frame, text="Закрыть", command=self.on_close)
        self.close_btn.pack(side=tk.RIGHT, padx=5)

        self.tooltip = None

    def _search_factions(self):
        query = self.factions_search_var.get().lower()
        self.listbox.delete(0, tk.END)
        for fac in self.original_factions:
            if query in fac.lower():
                self.listbox.insert(tk.END, fac)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        self.original_factions = []
        if os.path.exists(self.factions_file_path):
            with open(self.factions_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    clean = line.strip()
                    if not clean:
                        continue
                    # 🔹 ВАЖНО: берём ТОЛЬКО название до символа @
                    name = clean.split('@')[0].strip()
                    if name and name not in self.original_factions:
                        self.original_factions.append(name)
                        self.listbox.insert(tk.END, name)

    def show_details(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите фракцию для просмотра сведений.")
            return
        raw_name = self.listbox.get(sel[0])
        # 🔹 Отрезаем "@описание", если оно случайно попало
        clean_name = raw_name.split('@')[0].strip()
        FactionDetailsWindow(self.window, clean_name, self.db_path, on_update_callback=self._refresh_list)

    def save_factions(self):
        try:
            # Читаем текущие описания, чтобы не потерять их при перезаписи файла
            existing_desc = {}
            if os.path.exists(self.factions_file_path):
                with open(self.factions_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if '@' in line:
                            n, d = line.split('@', 1)
                            existing_desc[n.strip()] = d
                        else:
                            existing_desc[line] = ""

            with open(self.factions_file_path, 'w', encoding='utf-8') as f:
                for faction in self.listbox.get(0, tk.END):
                    clean_name = faction.split('@')[0].strip()
                    if clean_name:
                        desc = existing_desc.get(clean_name, "")
                        if desc:
                            f.write(f"{clean_name}@{desc}\n")
                        else:
                            f.write(f"{clean_name}\n")

            os.utime(self.db_path, None)
            messagebox.showinfo("Сохранение", "Список фракций сохранён.")
            self.changes_made = False
            self.original_factions = list(self.listbox.get(0, tk.END))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {e}")

    def _merge_defaults(self):
        if not messagebox.askyesno("Подтверждение", "Вы уверены, что хотите добавить значения по умолчанию?"): return
        def_path = os.path.join(DEFAULTS_DIR, "factions.txt")
        if not os.path.exists(def_path): return

        current = set(self.listbox.get(0, tk.END))
        added = 0
        with open(def_path, 'r', encoding='utf-8') as f:
            for line in f:
                item = line.strip()
                if item and item not in current:
                    self.listbox.insert(tk.END, item)
                    self.changes_made = True
                    added += 1
        messagebox.showinfo("Готово", f"Добавлено {added} новых значений из параметров по умолчанию.")

    def on_import_btn_hover(self, text):
        self.hide_tooltip()
        x, y, _, _ = self.import_btn.bbox("insert")
        x += self.import_btn.winfo_rootx() + 25
        y += self.import_btn.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.window)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                          font=("tahoma", "8", "normal"))
        label.pack(ipadx=1, ipady=1)

    def hide_tooltip(self):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def add_faction(self):
        new_faction = simpledialog.askstring("Добавить фракцию", "Введите название фракции:", parent=self.window)
        if new_faction:
            new_faction = new_faction.strip()
            if not new_faction: return

            # 🔹 ЗАМЕНА "—" НА "-" ПРИ ДОБАВЛЕНИИ
            new_faction = new_faction.replace('—', '-')

            existing = self.listbox.get(0, tk.END)
            if new_faction in existing:
                messagebox.showwarning("Предупреждение", f"Фракция '{new_faction}' уже существует.")
                return
            self.listbox.insert(tk.END, new_faction)
            self.changes_made = True

    def show_details(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите фракцию для просмотра сведений.")
            return
        raw_name = self.listbox.get(sel[0])
        # 🔹 Гарантированно отрезаем "@описание", если оно случайно попало в список
        faction_name = raw_name.split('@')[0].strip()
        FactionDetailsWindow(self.window, faction_name, self.db_path, on_update_callback=self._refresh_list)

    def delete_selected(self):
        selection = self.listbox.curselection()
        if not selection: return
        idx = selection[0]
        item = self.listbox.get(idx)

        if item in SYSTEM_FACTIONS:
            messagebox.showwarning("Доступ запрещён", "Удаление системной фракции невозможно.")
            return

        # Проверка субъектов, привязанных к этой фракции
        dep_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        affected = []
        if os.path.exists(dep_path):
            with open(dep_path, 'r', encoding='utf-8') as f:
                for line in f:
                    p = line.strip().split('\t')
                    if len(p) == 4 and p[3].strip() == item:
                        affected.append(f"{p[0]} {p[1]} {p[2]}".strip())

        if affected:
            self._show_reassign_dialog(item, affected, idx)
        else:
            self.listbox.delete(idx)
            self.changes_made = True
            self._auto_select_next(idx)

    def delete_all(self):
        if self.listbox.size() == 0: return
        dlg = tk.Toplevel(self.window)
        dlg.title("Удаление всех фракций")
        dlg.geometry("400x150")
        dlg.transient(self.window)
        dlg.grab_set()
        ttk.Label(dlg, text="Для удаления всех фракций введите \"УДАЛИТЬ\":").pack(pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()

        def execute():
            if entry.get().strip() == "УДАЛИТЬ":
                # 🔹 Собираем индексы только тех фракций, которые НЕ входят в системные
                indices_to_remove = []
                for i in range(self.listbox.size()):
                    if self.listbox.get(i) not in SYSTEM_FACTIONS:
                        indices_to_remove.append(i)

                # 🔹 Удаляем в обратном порядке, чтобы индексы списка не сдвигались
                for i in reversed(indices_to_remove):
                    self.listbox.delete(i)

                self.changes_made = True
                dlg.destroy()
                messagebox.showinfo("Успех", "Все несистемные фракции удалены.")
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")

        ttk.Button(dlg, text="Удалить", command=execute).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=2)

    def _auto_select_next(self, idx):
        if self.listbox.size() > 0:
            new_idx = idx if idx < self.listbox.size() else idx - 1
            self.listbox.select_set(new_idx)
            self.listbox.activate(new_idx)

    def _show_reassign_dialog(self, old_fac, affected_deputies, current_idx):
        dlg = tk.Toplevel(self.window)
        dlg.title("Переназначение субъектов")
        dlg.geometry("500x400")
        dlg.transient(self.window)
        dlg.grab_set()

        ttk.Label(dlg, text=f"Фракция '{old_fac}' имеет субъектов.\nВыберите новую фракцию:").pack(pady=10)
        other_facs = [self.listbox.get(i) for i in range(self.listbox.size()) if self.listbox.get(i) != old_fac]
        new_fac_var = tk.StringVar(value=other_facs[0] if other_facs else "Фракция не определена")
        ttk.Combobox(dlg, textvariable=new_fac_var, values=other_facs, state="readonly").pack(pady=5)

        ttk.Label(dlg, text="Затронутые субъекты:").pack(anchor=tk.W, padx=10)
        lb = tk.Listbox(dlg, height=10)
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        for dep in affected_deputies: lb.insert(tk.END, dep)

        def apply():
            new_fac = new_fac_var.get()
            dep_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
            if os.path.exists(dep_path):
                with open(dep_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                with open(dep_path, 'w', encoding='utf-8') as f:
                    for line in lines:
                        p = line.strip().split('\t')
                        if len(p) == 4 and p[3].strip() == old_fac:
                            p[3] = new_fac
                        f.write('\t'.join(p) + '\n')

            self.listbox.delete(current_idx)
            self.changes_made = True
            self._auto_select_next(current_idx)
            dlg.destroy()
            messagebox.showinfo("Готово",
                                f"Фракция удалена. {len(affected_deputies)} субъектов переназначены в '{new_fac}'.")

        ttk.Button(dlg, text="Применить", command=apply).pack(pady=5)

    def _edit_selected(self):
        sel = self.listbox.curselection()
        if not sel: return

        old_name = self.listbox.get(sel[0])

        # Создаем кастомное диалоговое окно вместо simpledialog для надежности
        edit_dialog = tk.Toplevel(self.window)
        edit_dialog.title("Редактировать фракцию")
        edit_dialog.geometry("400x150")
        edit_dialog.transient(self.window)
        edit_dialog.grab_set()

        ttk.Label(edit_dialog, text="Новое название фракции:").pack(pady=10)
        entry = ttk.Entry(edit_dialog, width=50)
        entry.pack(pady=5)
        entry.insert(0, old_name)  # 🔹 Автоматически подставляем текущее название
        entry.select_range(0, tk.END)  # Выделяем весь текст

        result = {"value": None}

        def on_ok():
            val = entry.get().strip()
            if val:
                result["value"] = val
                edit_dialog.destroy()

        def on_cancel():
            edit_dialog.destroy()

        btn_frame = ttk.Frame(edit_dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)

        self.window.wait_window(edit_dialog)

        new_name = result["value"]
        if new_name and new_name != old_name:
            new_name = new_name.replace('—', '-')

            existing = [self.listbox.get(i) for i in range(self.listbox.size()) if i != sel[0]]
            if new_name in existing:
                messagebox.showwarning("Внимание", "Такое название уже занято.")
                return

            self.listbox.delete(sel[0])
            self.listbox.insert(sel[0], new_name)
            self.listbox.selection_set(sel[0])
            self.changes_made = True

            dep_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
            if os.path.exists(dep_path):
                with open(dep_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                with open(dep_path, 'w', encoding='utf-8') as f:
                    for line in lines:
                        p = line.strip().split('\t')
                        if len(p) == 4 and p[3].strip() == old_name:
                            p[3] = new_name
                        f.write('\t'.join(p) + '\n')

    def import_from_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите файл с фракциями",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path:
            return

        try:
            # 🔹 1. Загружаем текущую базу из файла в словарь {имя: описание}
            faction_db = {}
            if os.path.exists(self.factions_file_path):
                with open(self.factions_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        if '@' in line:
                            n, d = line.split('@', 1)
                            faction_db[n.strip()] = d
                        else:
                            faction_db[line] = ""

            current_names = set(self.listbox.get(0, tk.END))
            new_factions = []
            added_count = 0
            overwritten_count = 0

            # 🔹 2. Обрабатываем импортируемый файл
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_lines = f.readlines()

            for line in raw_lines:
                line = line.strip()
                if not line: continue

                # Нормализация тире
                line = line.replace('—', '-').replace('–', '-')

                if '@' in line:
                    name, desc = line.split('@', 1)
                else:
                    name, desc = line, ""

                name = name.strip()
                if not name: continue

                # Экранируем реальные переносы строк для корректного хранения в одной строке .txt
                desc = desc.replace('\r\n', '\\n').replace('\n', '\\n').strip()

                if name in current_names:
                    # Фракция уже есть в списке -> перезаписываем описание, только если оно указано в импорте
                    if desc:
                        faction_db[name] = desc
                        overwritten_count += 1
                else:
                    # Новая фракция
                    faction_db[name] = desc
                    new_factions.append(name)
                    current_names.add(name)  # Защита от дублей внутри самого файла импорта
                    added_count += 1

            # 🔹 3. Сохраняем обновлённую базу обратно в файл (с сортировкой: системные первыми)
            all_names = sorted(faction_db.keys())
            sys_facs = [n for n in all_names if n in SYSTEM_FACTIONS]
            other_facs = [n for n in all_names if n not in SYSTEM_FACTIONS]

            with open(self.factions_file_path, 'w', encoding='utf-8') as f:
                for n in (sys_facs + other_facs):
                    d = faction_db[n]
                    if d:
                        f.write(f"{n}@{d}\n")
                    else:
                        f.write(f"{n}\n")

            # 🔹 4. Добавляем только новые имена в Listbox
            for faction in sorted(new_factions):
                self.listbox.insert(tk.END, faction)

            # 🔹 5. Формируем отчёт
            if added_count > 0 or overwritten_count > 0:
                msg = []
                if added_count > 0:
                    msg.append(f"Успешно добавлено {added_count} фракций.")
                if overwritten_count > 0:
                    msg.append(f"Перезаписано описание у {overwritten_count} фракций.")
                messagebox.showinfo("Импорт завершён", "\n".join(msg))
                self.changes_made = True
            else:
                messagebox.showinfo("Импорт", "Новых фракций не найдено, описания не изменены.")

        except Exception as e:
            messagebox.showerror("Ошибка импорта", f"Не удалось прочитать файл:\n{e}")

    def on_close(self):
        if self.changes_made and messagebox.askyesno("Сохранить изменения?",
                                                     "Вы хотите сохранить изменения в списке фракций?"):
            self.save_factions()
        self.window.destroy()