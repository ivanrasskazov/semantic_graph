import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import json
from config import DEPUTIES_FILE_NAME, FACTIONS_FILE_NAME, DEFAULTS_DIR, LEXEMES_DIR_NAME

# Импорт окна сведений об источнике (убедитесь, что файл sources_editor.py доступен)
try:
    from gui.editors.sources_editor import SourceDetailsWindow
except ImportError:
    SourceDetailsWindow = None

SYSTEM_FACTIONS = {"Законодательный (представительный) орган", "Федеральный СПЗИ", "Сенатор Российской Федерации"}

class DeputyDetailsWindow:
    def __init__(self, parent, editor, display_str):
        self.parent = parent
        self.editor = editor
        self.display_str = display_str
        self.db_path = editor.db_path
        self.edit_mode = False

        self.desc_text_content = " "
        if hasattr(editor, 'original_deputies') and editor.original_deputies:
            for dep in editor.original_deputies:
                if dep.get('display') == display_str:
                    raw_faction_col = dep['parts'][3] if len(dep.get('parts', [])) > 3 else " "
                    if '@' in raw_faction_col:
                        self.desc_text_content = raw_faction_col.split('@', 1)[1].replace('\\n', '\n')
                    break

        # Парсим строку из списка
        if " — " in display_str:
            name_part, faction = display_str.rsplit(" — ", 1)
        else:
            name_part, faction = display_str, "Фракция не определена"

        self.name_part = name_part.strip()
        self.faction = faction.strip()

        # 🔹 ИСПРАВЛЕНИЕ: Читаем описание напрямую из модели данных (parts[3])
        self.desc_text_content = ""
        for dep in self.editor.original_deputies:
            if dep['display'] == self.display_str:
                raw_faction_col = dep['parts'][3] if len(dep['parts']) > 3 else ""
                if '@' in raw_faction_col:
                    self.desc_text_content = raw_faction_col.split('@', 1)[1].replace('\\n', '\n')
                break

        # Определяем тип субъекта
        f_low = self.faction.lower()
        if "орган" in f_low:
            self.subj_type = "Законодательный (представительный) орган"
        elif "федеральный спзи" in f_low:
            self.subj_type = "Федеральный СПЗИ"
        elif "сенатор" in f_low:
            self.subj_type = "Сенатор Российской Федерации"
        else:
            self.subj_type = "Депутат Государственной Думы"

        self.window = tk.Toplevel(parent)
        self.window.title(f"Сведения: {self.name_part}")
        self.window.geometry("620x600")
        self.window.transient(parent)
        self.window.grab_set()

        self._build_ui()
        self._load_stats()

    def _build_ui(self):
        main = ttk.Frame(self.window, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text=f"Тип: {self.subj_type}", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        if self.subj_type == "Сенатор Российской Федерации" or self.subj_type == "Депутат Государственной Думы":
            text_label = "Фамилия Имя Отчество"
        else:
            text_label = "Название"
        ttk.Label(main, text=f"{text_label}:").pack(anchor=tk.W)
        self.ent_name = ttk.Entry(main, width=50)
        self.ent_name.insert(0, self.name_part)
        self.ent_name.config(state="readonly")
        self.ent_name.pack(fill=tk.X, pady=(0, 10))

        self.ent_faction = None
        if self.subj_type == "Депутат Государственной Думы":
            ttk.Label(main, text="Фракция:").pack(anchor=tk.W)
            facs = []
            fac_file = os.path.join(self.db_path, FACTIONS_FILE_NAME)
            if os.path.exists(fac_file):
                with open(fac_file, 'r', encoding='utf-8') as f:
                    facs = [l.strip() for l in f if l.strip() and l.strip() not in SYSTEM_FACTIONS]
            # 🔹 Сначала "Фракция не определена", остальные по алфавиту
            sorted_facs = ["Фракция не определена"] + sorted([f for f in facs if f != "Фракция не определена"])
            self.ent_faction = ttk.Combobox(main, values=sorted_facs, state="disabled", width=48)
            self.ent_faction.set(self.faction)
            self.ent_faction.pack(fill=tk.X, pady=(0, 10))

        stats_frame = ttk.LabelFrame(main, text="Статистика по базе данных", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        self.lbl_sources_count = ttk.Label(stats_frame, text="Источники: —")
        self.lbl_sources_count.pack(anchor=tk.W)
        self.lbl_period = ttk.Label(stats_frame, text="Период: —")
        self.lbl_period.pack(anchor=tk.W)

        # 🔹 ОПИСАНИЕ (ТЕПЕРЬ НАД КНОПКАМИ)
        ttk.Label(main, text="Описание:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(10, 0))
        desc_frame = ttk.Frame(main)
        desc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.text_desc = tk.Text(desc_frame, height=5, wrap=tk.WORD, font=("Segoe UI", 9))
        sb_desc = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=self.text_desc.yview)
        self.text_desc.configure(yscrollcommand=sb_desc.set)
        self.text_desc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_desc.pack(side=tk.RIGHT, fill=tk.Y)

        if self.desc_text_content:
            self.desc_text_content = self.desc_text_content.replace('\\n', '\n')

        self.text_desc.insert(tk.END, self.desc_text_content)
        self.text_desc.config(state="disabled")

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=10)
        self.btn_sources = ttk.Button(btn_frame, text="Источники", command=self._show_sources)
        self.btn_sources.pack(side=tk.LEFT, padx=5)
        if self.faction and self.faction != "Неизвестно":
            self.btn_faction = ttk.Button(btn_frame, text="Фракция", command=self._show_faction)
            self.btn_faction.pack(side=tk.LEFT, padx=5)
        self.btn_edit = ttk.Button(btn_frame, text="Редактировать", command=self._toggle_edit)
        self.btn_edit.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT)

    def _load_stats(self):
        sources, dates = self.editor._get_subject_stats(self.name_part, self.faction)
        self.lbl_sources_count.config(text=f"Источники: {len(sources)}")
        self.sources_list = sources
        self.lbl_period.config(text=f"Период: {dates[0]} — {dates[-1]}" if dates else "Период: Не указан")

    def _show_faction(self):
        if not self.faction or self.faction == "Неизвестно": return
        try:
            from gui.editors.factions_editor import FactionDetailsWindow
            FactionDetailsWindow(self.window, self.faction, self.db_path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть сведения о фракции:\n{e}")

    def _show_sources(self):
        # 🔹 ПЕРЕЗАГРУЗКА СПИСКА ИСТОЧНИКОВ С ДИСКА (исправляет устаревший кэш)
        fresh_sources, _ = self.editor._get_subject_stats(self.name_part, self.faction)
        self.sources_list = fresh_sources
        self.lbl_sources_count.config(text=f"Источники: {len(fresh_sources)}")

        src_win = tk.Toplevel(self.window)
        src_win.title("Источники субъекта")
        src_win.geometry("400x400")
        src_win.transient(self.window)
        src_win.grab_set()
        search_var = tk.StringVar()
        ttk.Label(src_win, text="Поиск источников: ").pack(anchor=tk.W, padx=5, pady=(5, 0))
        ttk.Entry(src_win, textvariable=search_var).pack(fill=tk.X, padx=5, pady=2)
        canvas_frame = ttk.Frame(src_win)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        canvas = tk.Canvas(canvas_frame)
        sb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        frame = ttk.Frame(canvas)
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def render_list():
            for w in frame.winfo_children(): w.destroy()
            query = search_var.get().lower()
            if not self.sources_list:
                ttk.Label(frame, text="Источники не найдены", foreground="gray").pack(pady=20)
                return
            for src in sorted(self.sources_list):
                if query in src.lower():
                    ttk.Button(frame, text=src, command=lambda s=src: self._open_source_details(s)).pack(fill=tk.X,
                                                                                                         padx=5, pady=1)

        search_var.trace_add('write', lambda *a: render_list())
        render_list()

    def _open_source_details(self, src_name):
        clean_name = src_name.replace('.txt', '').replace('.docx', '')
        try:
            # 🔹 Загрузка данных об источнике из JSON
            lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
            json_path = os.path.join(lexemes_dir, f"{clean_name}.json")

            cache_data = {}
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

            # 🔹 Формируем словарь с данными (аналогично graph_window.py)
            src_dict = {
                "name": clean_name,
                "file": f"{clean_name}.txt",
                "url": cache_data.get("url", ""),
                "date": cache_data.get("date", ""),
                "deputies": cache_data.get("deputies", []),
                "description": cache_data.get("description", "")
            }

            from gui.editors.sources_editor import SourceDetailsWindow
            SourceDetailsWindow(self.window, self.db_path, src_dict,
                            on_update_callback=lambda d, old: self._refresh_sources_stats())
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть сведения: {e}")

    def _refresh_sources_stats(self):
        """Пересчитывает источники и обновляет лейблы после изменения источника."""
        fresh_sources, dates = self.editor._get_subject_stats(self.name_part, self.faction)
        self.sources_list = fresh_sources
        self.lbl_sources_count.config(text=f"Источники: {len(fresh_sources)}")
        self.lbl_period.config(text=f"Период: {dates[0]} — {dates[-1]}" if dates else "Период: Не указан")

    def _toggle_edit(self):
        if not self.edit_mode:
            self.edit_mode = True
            self.ent_name.config(state="normal")
            if self.ent_faction:
                self.ent_faction.config(state="readonly")  # Combobox: только выбор из списка
            self.text_desc.config(state="normal")
            self.btn_edit.config(text="Сохранить")
            self.ent_name.focus_set()
            self.ent_name.select_range(0, tk.END)
        else:
            self._save_changes()

    def _save_changes(self):
        new_name = self.ent_name.get().strip()
        raw_desc = self.text_desc.get("1.0", tk.END)
        new_desc = raw_desc.rstrip('\n').strip()
        new_faction = self.ent_faction.get() if self.ent_faction else self.faction

        if not new_name:
            messagebox.showwarning("Ошибка", "Название/ФИО не может быть пустым.")
            return

        # 🔹 Экранируем переносы и формируем 4-ю колонку: Фракция@Описание
        new_desc_escaped = new_desc.replace('\n', '\\n')
        faction_part = f"{new_faction}@{new_desc_escaped}" if new_desc_escaped else new_faction

        # Проверяем, есть ли у editor атрибут original_deputies
        if hasattr(self.editor, 'original_deputies') and self.editor.original_deputies:
            found = False
            for item in self.editor.original_deputies:
                if item['display'] == self.display_str:
                    # Разбиваем новое ФИО на части
                    name_parts = new_name.split(' ', 2)
                    item['parts'][0] = name_parts[0] if len(name_parts) > 0 else ""
                    item['parts'][1] = name_parts[1] if len(name_parts) > 1 else ""
                    item['parts'][2] = name_parts[2] if len(name_parts) > 2 else ""

                    # Обновляем фракцию с описанием в модели
                    item['parts'][3] = faction_part
                    item['faction'] = new_faction
                    item['display'] = f"{new_name} — {new_faction}"
                    found = True
                    break

            if found:
                self.editor.save_deputies()
                self.editor._refresh_listbox()
                messagebox.showinfo("Успех", "Изменения сохранены.")
            else:
                messagebox.showerror("Ошибка", "Не удалось найти запись для обновления.")

        self.window.destroy()

class DeputiesEditorWindow:
    def __init__(self, parent, db_path, is_defaults=False):
        self.parent = parent
        self.db_path = db_path
        self.changes_made = False
        self.is_defaults = is_defaults
        self.deputies_descriptions = {}
        self.deputies_file_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)

        self.window = tk.Toplevel(parent)
        self.window.title("Список субъектов")
        self.window.geometry("980x650")
        self.window.transient(parent)
        self.window.grab_set()

        # 🔹 ВКЛАДКИ (Notebook)
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Фреймы для вкладок
        self.tabs = {
            "All": ttk.Frame(self.notebook),
            "SPZI": ttk.Frame(self.notebook),
            "Deputy": ttk.Frame(self.notebook),
            "Senator": ttk.Frame(self.notebook),
            "Legislative": ttk.Frame(self.notebook)
        }

        tab_names = {
            "All": "Все",
            "SPZI": "Федеральные СПЗИ",
            "Deputy": "Депутаты Государственной Думы",
            "Senator": "Сенаторы Российской Федерации",
            "Legislative": "Законодательные (представительные) органы"
        }

        self.listboxes = {}

        for key, frame in self.tabs.items():
            self.notebook.add(frame, text=tab_names[key])

            lb = tk.Listbox(frame)
            sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            self.listboxes[key] = lb
            lb.bind('<Double-1>', lambda e: self.show_details())
            lb.bind('<Delete>', lambda e: self.delete_selected())

        self.original_deputies = []  # Хранилище всех данных (кортежи)

        # 🔹 ПОИСК
        self.deputies_search_var = tk.StringVar()
        ttk.Label(self.window, text="Поиск:").pack(anchor=tk.W, padx=10, pady=(0, 5))
        self.deputies_search_entry = ttk.Entry(self.window, textvariable=self.deputies_search_var)
        self.deputies_search_entry.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.deputies_search_var.trace_add('write', lambda *args: self._filter_list())

        # Кнопки управления
        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        self.add_btn = ttk.Button(button_frame, text="Добавить", command=self.add_deputy)
        self.add_btn.pack(side=tk.LEFT, padx=5)
        self.details_btn = ttk.Button(button_frame, text="Сведения", command=self.show_details)
        self.details_btn.pack(side=tk.LEFT, padx=5)
        self.del_btn = ttk.Button(button_frame, text="Удалить", command=self.delete_selected)
        self.del_btn.pack(side=tk.LEFT, padx=5)
        self.import_btn = ttk.Button(button_frame, text="Импортировать", command=self.import_from_file)
        self.import_btn.pack(side=tk.LEFT, padx=5)

        if not self.is_defaults:
            ttk.Button(button_frame, text="Добавить значения по умолчанию", command=self._merge_defaults).pack(
                side=tk.LEFT, padx=5)
        self.delete_all_btn = ttk.Button(button_frame, text="Удалить всё", command=self.delete_all)
        self.delete_all_btn.pack(side=tk.LEFT, padx=5)
        self.close_btn = ttk.Button(button_frame, text="Закрыть", command=self.on_close)
        self.close_btn.pack(side=tk.RIGHT, padx=5)

        self._refresh_listbox()
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: self._filter_list())

    def delete_all(self):
        if not self.original_deputies: return
        dlg = tk.Toplevel(self.window)
        dlg.title("Удаление всех субъектов")
        dlg.geometry("400x150")
        dlg.transient(self.window)
        dlg.grab_set()
        ttk.Label(dlg, text="Для удаления всех субъектов введите \"УДАЛИТЬ\":").pack(pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()

        def execute():
            if entry.get().strip() == "УДАЛИТЬ":
                self.original_deputies.clear()
                for lb in self.listboxes.values():
                    lb.delete(0, tk.END)
                self.changes_made = True
                dlg.destroy()
                messagebox.showinfo("Успех", "Все субъекты удалены.")
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")

        ttk.Button(dlg, text="Удалить", command=execute).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=2)

    def _search_deputies(self):
        query = self.deputies_search_var.get().strip().lower()

        # Получаем активную вкладку
        active_tab = self.notebook.tab(self.notebook.select(), "text")
        type_map = {
            "Все": "All", "Федеральные СПЗИ": "SPZI", "Депутаты Государственной Думы": "Deputy",
            "Сенаторы Российской Федерации": "Senator", "Законодательные (представительные) органы": "Legislative"
        }
        active_key = type_map.get(active_tab, "All")
        active_lb = self.listboxes[active_key]

        active_lb.delete(0, tk.END)

        # Если поиск пустой или совпадает с плейсхолдером → показываем всё
        if not query or query == "поиск":
            for dep in self.original_deputies:
                active_lb.insert(tk.END, dep["display"])
            return

        for dep in self.original_deputies:
            name_part = dep["display"].split(' — ')[0].lower()
            if query in name_part or any(query in word for word in name_part.split()):
                active_lb.insert(tk.END, dep["display"])

    def _refresh_listbox(self):
        """Очищает все вкладки, перезагружает данные из файла и удаляет дубликаты."""
        for lb in self.listboxes.values():
            lb.delete(0, tk.END)
        self.original_deputies.clear()

        if not os.path.exists(self.deputies_file_path):
            self._filter_list()
            return

        seen_keys = set()
        duplicates_found = 0

        with open(self.deputies_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue

                parts = line.split('\t')
                if len(parts) >= 4:
                    surname, name, patronymic, raw_faction = parts[0], parts[1], parts[2], parts[3]

                    if '@' in raw_faction:
                        faction, _ = raw_faction.split('@', 1)
                    else:
                        faction = raw_faction

                    full_name = f"{surname} {name} {patronymic}".strip()
                    display = f"{full_name} — {faction}"

                    key = self._get_subject_key(full_name, faction)
                    if key in seen_keys:
                        duplicates_found += 1
                        continue  # 🔹 Пропускаем дубликат
                    seen_keys.add(key)

                    type_val = self._get_type_by_faction(faction)
                    self.original_deputies.append({
                        "display": display,
                        "faction": faction,
                        "type": type_val,
                        "parts": [surname, name, patronymic, raw_faction]
                    })

        if duplicates_found > 0:
            print(f"[ДЕДУПЛИКАЦИЯ] Удалено {duplicates_found} повторяющихся записей при загрузке.")

        self._filter_list()

    def _filter_list(self):
        query = self.deputies_search_var.get().lower()
        active_tab = self.notebook.tab(self.notebook.select(), "text")

        # Очищаем все списки
        for lb in self.listboxes.values():
            lb.delete(0, tk.END)

        tab_type_map = {
            "Все": None,
            "Федеральные СПЗИ": "SPZI",
            "Депутаты Государственной Думы": "Deputy",
            "Сенаторы Российской Федерации": "Senator",
            "Законодательные (представительные) органы": "Legislative"
        }

        target_type = tab_type_map.get(active_tab)

        # 1. Собираем подходящие элементы во временный список
        filtered_items = []
        for item in self.original_deputies:
            if target_type and item["type"] != target_type:
                continue
            if query and query not in item["display"].lower():
                continue
            filtered_items.append(item)

        # 2. 🔹 СОРТИРОВКА по ФИО (display)
        filtered_items.sort(key=lambda x: x["display"].lower())

        # 3. Вставляем в Listbox
        for item in filtered_items:
            list_key = "All" if target_type is None else target_type
            if list_key in self.listboxes:
                self.listboxes[list_key].insert(tk.END, item["display"])

    def _get_db_factions(self):
        f_path = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        if os.path.exists(f_path):
            with open(f_path, 'r', encoding='utf-8') as f:
                return {l.strip() for l in f if l.strip()}
        return {"Фракция не определена"}

    def _merge_defaults(self):
        if not messagebox.askyesno("Подтверждение", "Добавить субъектов по умолчанию?"): return
        def_path = os.path.join(DEFAULTS_DIR, DEPUTIES_FILE_NAME)
        if not os.path.exists(def_path): return
        valid_facs = self._get_db_factions()

        # 🔹 Собираем текущие уникальные ключи
        current_keys = {self._get_subject_key(d["display"].split(' — ')[0], d["faction"]) for d in
                        self.original_deputies}

        added = 0
        with open(def_path, 'r', encoding='utf-8') as f:
            for line in f:
                p = line.strip().split('\t')
                if len(p) >= 4:
                    faction = p[3].strip()
                    type_val = self._get_type_by_faction(faction)
                    full_name = f"{p[0]} {p[1]} {p[2]}".strip()
                    display = f"{full_name} — {faction}"

                    key = self._get_subject_key(full_name, faction)
                    if faction in valid_facs and key not in current_keys:
                        current_keys.add(key)
                        self.original_deputies.append({
                            "display": display,
                            "faction": faction,
                            "type": type_val,
                            "parts": p
                        })
                        added += 1

        if added > 0:
            self.changes_made = True
            self._filter_list()
            messagebox.showinfo("Готово", f"Добавлено {added} субъектов.")
        else:
            messagebox.showinfo("Информация", "Все субъекты уже существуют или фракции отсутствуют.")

    def _edit_selected(self):
        sel = self.listbox.curselection()
        if not sel: return
        item = self.listbox.get(sel[0])
        name_part, fac_part = item.rsplit(' — ', 1)
        parts = name_part.strip().split(' ', 2)

        dlg = tk.Toplevel(self.window);
        dlg.title("Редактировать субъекта");
        dlg.geometry("400x300");
        dlg.transient(self.window);
        dlg.grab_set()
        ttk.Label(dlg, text="Фамилия:").pack(pady=2);
        s_ent = ttk.Entry(dlg);
        s_ent.pack(pady=2);
        s_ent.insert(0, parts[0])
        ttk.Label(dlg, text="Имя:").pack(pady=2);
        n_ent = ttk.Entry(dlg);
        n_ent.pack(pady=2);
        n_ent.insert(0, parts[1] if len(parts) > 1 else "")
        ttk.Label(dlg, text="Отчество:").pack(pady=2);
        p_ent = ttk.Entry(dlg);
        p_ent.pack(pady=2);
        p_ent.insert(0, parts[2] if len(parts) > 2 else "")
        ttk.Label(dlg, text="Фракция:").pack(pady=2)
        fac_var = tk.StringVar(value=fac_part.strip())
        ttk.Combobox(dlg, textvariable=fac_var, values=sorted(self._get_db_factions()), state="readonly").pack(pady=2)

        def apply():
            s, n, p, f = s_ent.get().strip(), n_ent.get().strip(), p_ent.get().strip(), fac_var.get()
            if not s or not n:
                messagebox.showwarning("Внимание", "Фамилия и имя обязательны.")
                return

            new_display = f"{s} {n} {p}".strip() + f" — {f}"

            # 1. Обновляем визуальный список
            self.listbox.delete(sel[0])
            self.listbox.insert(sel[0], new_display)
            self.listbox.selection_set(sel[0])

            # 2. БЕЗОПАСНОЕ обновление master-списка (original_deputies)
            # Ищем индекс по старому значению (item), а не по визуальному индексу sel[0]
            if item in self.original_deputies:
                master_idx = self.original_deputies.index(item)
                self.original_deputies[master_idx] = new_display
            else:
                # Фоллбэк: если поиск не активен и индексы совпадают
                self.original_deputies[sel[0]] = new_display

            self.changes_made = True
            dlg.destroy()

        ttk.Button(dlg, text="Сохранить", command=apply).pack(pady=10)

    def _get_subject_key(self, name, faction):
        """Возвращает нормализованный ключ для проверки уникальности (ФИО/Название + Фракция)."""
        norm_name = re.sub(r'\s+', ' ', name.strip().lower().replace('ё', 'е'))
        norm_faction = faction.strip().lower().replace('ё', 'е')
        return (norm_name, norm_faction)

    def add_deputy(self):
        add_win = tk.Toplevel(self.window)
        add_win.title("Добавление субъекта права законодательной инициативы")
        add_win.geometry("780x400")
        add_win.transient(self.window)
        add_win.grab_set()

        nb = ttk.Notebook(add_win)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        factions = []
        factions_file = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        if os.path.exists(factions_file):
            with open(factions_file, 'r', encoding='utf-8') as f:
                factions = [line.strip() for line in f if line.strip()]

        # 🔹 Вкладка 1: Федеральные СПЗИ
        f1 = ttk.Frame(nb);
        ttk.Label(f1, text="Название органа:").pack(anchor=tk.W, padx=20, pady=(10, 2))
        fed_name_var = tk.StringVar();
        ttk.Entry(f1, textvariable=fed_name_var).pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(f1, text="Фракция: Федеральный СПЗИ", foreground="gray").pack(anchor=tk.W, padx=20)
        nb.add(f1, text="Федеральный СПЗИ")

        # 🔹 Вкладка 2: Депутат ГД
        f2 = ttk.Frame(nb)
        dep_surname, dep_name, dep_patronym, dep_faction = tk.StringVar(), tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(f2, text="Фамилия:").pack(anchor=tk.W, padx=20, pady=(5, 0));
        ttk.Entry(f2, textvariable=dep_surname).pack(fill=tk.X, padx=20, pady=2)
        ttk.Label(f2, text="Имя:").pack(anchor=tk.W, padx=20);
        ttk.Entry(f2, textvariable=dep_name).pack(fill=tk.X, padx=20, pady=2)
        ttk.Label(f2, text="Отчество:").pack(anchor=tk.W, padx=20);
        ttk.Entry(f2, textvariable=dep_patronym).pack(fill=tk.X, padx=20, pady=2)
        ttk.Label(f2, text="Фракция:").pack(anchor=tk.W, padx=20)

        # 🔹 ФИЛЬТРАЦИЯ СИСТЕМНЫХ ФРАКЦИЙ ДЛЯ ДЕПУТАТОВ
        allowed_deputy_factions = [f for f in factions if f not in SYSTEM_FACTIONS]
        ttk.Combobox(f2, textvariable=dep_faction, values=sorted(allowed_deputy_factions), state="readonly").pack(
            fill=tk.X, padx=20, pady=5)
        nb.add(f2, text="Депутат Государственной Думы")

        # 🔹 Вкладка 3: Сенатор РФ
        f3 = ttk.Frame(nb)
        sen_surname, sen_name, sen_patronym = tk.StringVar(), tk.StringVar(), tk.StringVar()
        ttk.Label(f3, text="Фамилия:").pack(anchor=tk.W, padx=20, pady=(5, 0));
        ttk.Entry(f3, textvariable=sen_surname).pack(fill=tk.X, padx=20, pady=2)
        ttk.Label(f3, text="Имя:").pack(anchor=tk.W, padx=20);
        ttk.Entry(f3, textvariable=sen_name).pack(fill=tk.X, padx=20, pady=2)
        ttk.Label(f3, text="Отчество:").pack(anchor=tk.W, padx=20);
        ttk.Entry(f3, textvariable=sen_patronym).pack(fill=tk.X, padx=20, pady=2)
        ttk.Label(f3, text="Фракция: Сенатор Российской Федерации", foreground="gray").pack(anchor=tk.W, padx=20)
        nb.add(f3, text="Сенатор Российской Федерации")

        # 🔹 Вкладка 4: Законодательные органы
        f4 = ttk.Frame(nb)
        leg_name_var = tk.StringVar()
        ttk.Label(f4, text="Название органа:").pack(anchor=tk.W, padx=20, pady=(10, 2))
        ttk.Entry(f4, textvariable=leg_name_var).pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(f4, text="Фракция: Законодательный (представительный) орган", foreground="gray").pack(anchor=tk.W,
                                                                                                        padx=20)
        nb.add(f4, text="Законодательные (представительные) органы")

        def confirm_add():
            sel_tab = nb.tab(nb.select(), "text").strip()
            raw_item = ""
            if sel_tab == "Федеральный СПЗИ":
                name = fed_name_var.get().strip()
                if not name: messagebox.showwarning("Предупреждение", "Введите название СПЗИ."); return
                raw_item = f"{name}\tФедеральный СПЗИ\t\tФедеральный СПЗИ"
            elif sel_tab == "Депутат Государственной Думы":
                s, n, p, f = dep_surname.get().strip(), dep_name.get().strip(), dep_patronym.get().strip(), dep_faction.get().strip()
                if not s or not n or not f: messagebox.showwarning("Предупреждение", "Заполните ФИО и Фракцию."); return
                raw_item = f"{s}\t{n}\t{p}\t{f}"
            elif sel_tab == "Сенатор Российской Федерации":
                s, n, p = sen_surname.get().strip(), sen_name.get().strip(), sen_patronym.get().strip()
                if not s or not n: messagebox.showwarning("Предупреждение", "Заполните ФИО."); return
                raw_item = f"{s}\t{n}\t{p}\tСенатор Российской Федерации"
            elif sel_tab == "Законодательные (представительные) органы":
                name = leg_name_var.get().strip()
                if not name: messagebox.showwarning("Предупреждение", "Введите название органа."); return
                raw_item = f"{name}\tЗаконодательный (представительный) орган\t\tЗаконодательный (представительный) орган"

            parts = raw_item.split('\t')
            fio = f"{parts[0]} {parts[1]} {parts[2]}".strip() if len(parts) >= 3 else parts[0]
            faction_val = parts[-1]

            # 🔹 ПРОВЕРКА НА ДУБЛИКАТ ПО ФИО + ФРАКЦИЯ
            new_key = self._get_subject_key(fio, faction_val)
            existing_keys = {self._get_subject_key(d["display"].split(' — ')[0], d["faction"]) for d in
                             self.original_deputies}

            if new_key in existing_keys:
                messagebox.showwarning("Дубликат", f"Субъект '{fio}' с фракцией '{faction_val}' уже существует в базе.")
                return

            display_item = f"{fio} — {faction_val}"
            type_map = {
                "Федеральный СПЗИ": "SPZI",
                "Депутат Государственной Думы": "Deputy",
                "Сенатор Российской Федерации": "Senator",
                "Законодательные (представительные) органы": "Legislative"
            }

            self.original_deputies.append({
                "display": display_item,
                "faction": faction_val,
                "type": type_map.get(sel_tab, "Deputy"),
                "parts": parts
            })
            self.changes_made = True
            self._filter_list()
            add_win.destroy()

        ttk.Button(add_win, text="Добавить", command=confirm_add).pack(pady=10)

    def on_import_btn_hover(self, text):
        self.hide_tooltip()
        x, y, _, _ = self.import_btn.bbox("insert")
        x += self.import_btn.winfo_rootx() + 25;
        y += self.import_btn.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.window);
        self.tooltip.wm_overrideredirect(True);
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                          font=("tahoma", "8", "normal"))
        label.pack(ipadx=1, ipady=1)

    def hide_tooltip(self):
        if self.tooltip: self.tooltip.destroy(); self.tooltip = None

    def delete_selected(self):
        active_tab = self.notebook.tab(self.notebook.select(), "text")
        type_map = {
            "Все": "All", "Федеральные СПЗИ": "SPZI", "Депутаты Государственной Думы": "Deputy",
            "Сенаторы Российской Федерации": "Senator", "Законодательные (представительные) органы": "Legislative"
        }
        active_key = type_map.get(active_tab)
        if not active_key or active_key not in self.listboxes: return

        active_lb = self.listboxes[active_key]
        sel = active_lb.curselection()
        if not sel: return

        idx = sel[0]
        item_text = active_lb.get(idx)
        active_lb.delete(idx)

        # Удаляем из master-списка
        self.original_deputies = [d for d in self.original_deputies if d["display"] != item_text]
        self.changes_made = True

    def import_from_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите файл с субъектами",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path: return

        valid_facs = self._get_db_factions()
        missing_facs = set()
        skipped_lines = []
        skipped_duplicates = 0

        # 🔹 Собираем текущие уникальные ключи
        current_keys = {self._get_subject_key(d["display"].split(' — ')[0], d["faction"]) for d in
                        self.original_deputies}
        added = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line: continue

                    if ' — ' not in line:
                        skipped_lines.append(f"Строка {line_num}: нет разделителя ' — '")
                        continue

                    parts = line.split(' — ', 1)
                    name_part = parts[0].strip()
                    imported_faction_raw = parts[1].strip().replace('—', '-')

                    if '@' in imported_faction_raw:
                        imp_faction = imported_faction_raw.split('@', 1)[0].strip()
                    else:
                        imp_faction = imported_faction_raw

                    if not name_part or not imp_faction: continue
                    if imp_faction not in valid_facs:
                        missing_facs.add(imp_faction)
                        continue

                    # 🔹 ПРОВЕРКА НА ДУБЛИКАТ
                    new_key = self._get_subject_key(name_part, imp_faction)
                    if new_key in current_keys:
                        skipped_duplicates += 1
                        continue

                    current_keys.add(new_key)
                    display_item = f"{name_part} — {imp_faction}"
                    type_val = self._get_type_by_faction(imp_faction)

                    self.original_deputies.append({
                        "display": display_item,
                        "faction": imp_faction,
                        "type": type_val,
                        "parts": [name_part, "", "", imported_faction_raw]
                    })
                    added += 1

            self.changes_made = True
            self._filter_list()

            if missing_facs:
                factions_path = os.path.join(self.db_path, FACTIONS_FILE_NAME)
                if messagebox.askyesno("Добавить фракции?",
                                       f"Не найдены фракции:\n• {'\n• '.join(sorted(missing_facs))}\n\nДобавить автоматически?"):
                    with open(factions_path, 'a', encoding='utf-8') as ff:
                        for fac in sorted(missing_facs): ff.write(f"{fac}\n")
                    messagebox.showinfo("Успех", f"Добавлено {len(missing_facs)} фракций.")

            msg_parts = []
            if added > 0: msg_parts.append(f"Успешно добавлено: {added}")
            if skipped_duplicates > 0: msg_parts.append(f"Пропущено дубликатов: {skipped_duplicates}")
            if missing_facs: msg_parts.append(f"Пропущено (нет фракции): {len(missing_facs)}")
            if skipped_lines: msg_parts.append(f"Ошибки формата: {len(skipped_lines)}")

            if not msg_parts:
                messagebox.showinfo("Импорт", "Новых субъектов не найдено или все уже существуют.")
            else:
                messagebox.showinfo("Результат импорта", "\n".join(msg_parts))

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось импортировать файл:\n{str(e)}")

    def _get_type_by_faction(self, faction):
        """Определяет тип вкладки на основе названия фракции."""
        if faction == "Сенатор Российской Федерации": return "Senator"
        if faction == "Законодательный (представительный) орган": return "Legislative"
        if faction == "Федеральный СПЗИ": return "SPZI"
        return "Deputy"

    def on_close(self):
        if self.changes_made and messagebox.askyesno("Сохранить изменения?", "Сохранить изменения в списке субъектов?"):
            self.save_deputies()
        self.window.destroy()

    def save_deputies(self):
        try:
            with open(self.deputies_file_path, 'w', encoding='utf-8') as f:
                for item in self.original_deputies:
                    if isinstance(item, dict):
                        parts = item.get("parts", [])
                        if len(parts) >= 4:
                            surname, name, patronymic, raw_faction = parts
                            # 🔹 raw_faction уже содержит экранированное описание. Пишем как есть.
                            f.write(f"{surname}\t{name}\t{patronymic}\t{raw_faction}\n")
                    elif isinstance(item, str) and ' — ' in item:
                        # Обратная совместимость
                        name_part, fac_part = item.rsplit(' — ', 1)
                        n_parts = name_part.strip().split(' ', 2)
                        s, n, p = (n_parts[i] if i < len(n_parts) else " " for i in range(3))
                        f.write(f"{s}\t{n}\t{p}\t{fac_part}\n")

            os.utime(self.db_path, None)
            messagebox.showinfo("Сохранение", "Список субъектов сохранён.")
            self.changes_made = False
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл: {str(e)}")

    def show_details(self):
        active_tab = self.notebook.tab(self.notebook.select(), "text")
        type_map = {
            "Все": "All", "Федеральные СПЗИ": "SPZI", "Депутаты Государственной Думы": "Deputy",
            "Сенаторы Российской Федерации": "Senator", "Законодательные (представительные) органы": "Legislative"
        }
        active_key = type_map.get(active_tab)
        if not active_key or active_key not in self.listboxes: return

        active_lb = self.listboxes[active_key]
        sel = active_lb.curselection()
        if not sel:
            messagebox.showwarning("Внимание", "Выберите субъект для просмотра сведений.")
            return
        display_str = active_lb.get(sel[0])
        DeputyDetailsWindow(self.window, self, display_str)

    def _get_subject_stats(self, subject_name, faction):
        """Сканирует папку lexemes и собирает статистику упоминаний."""
        sources = []
        dates = []
        lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)

        if not os.path.exists(lexemes_dir):
            return sources, dates

        # Нормализуем имя для поиска
        norm_subject = ' '.join(subject_name.split()).strip().lower().replace('ё', 'е')
        surname = norm_subject.split()[0] if norm_subject.split() else ""

        json_files = [f for f in os.listdir(lexemes_dir) if f.endswith('.json')]

        for fname in json_files:
            try:
                with open(os.path.join(lexemes_dir, fname), 'r', encoding='utf-8') as f:
                    data = json.load(f)

                deputies_list = data.get('deputies', [])
                found = False

                for dep_str in deputies_list:
                    dep_str_lower = dep_str.lower().strip().replace('ё', 'е')
                    dep_norm = ' '.join(dep_str.split()).lower().replace('ё', 'е')

                    # Извлекаем ФИО без фракции
                    dep_name = dep_str.split(' — ')[0].strip().lower().replace('ё',
                                                                               'е') if ' — ' in dep_str else dep_str_lower

                    # ПРОВЕРКА 1: Точное совпадение ФИО
                    if norm_subject == dep_name:
                        found = True
                        break

                    # ПРОВЕРКА 2: ФИО с фракцией
                    if f"{norm_subject} — {faction.lower().replace('ё', 'е')}" == dep_str_lower:
                        found = True
                        break

                    # ПРОВЕРКА 3: По фамилии (если имя совпадает с началом строки)
                    if surname and dep_name.startswith(surname):
                        # Дополнительная проверка - совпадает ли остальная часть
                        if norm_subject in dep_name or dep_name in norm_subject:
                            found = True
                            break

                    # ПРОВЕРКА 4: Частичное совпадение
                    if norm_subject in dep_str_lower or dep_name in norm_subject:
                        found = True
                        break

                if found:
                    sources.append(fname.replace('.json', '.txt'))
                    if 'date' in data and data['date']:
                        dates.append(data['date'])

            except Exception as e:
                print(f"DEBUG: Ошибка чтения {fname}: {e}")
                pass

        return sources, sorted(dates)

    def _update_subject_in_file(self, old_display_str, new_name_str, new_faction_str):
        """Обновляет запись в deputies.txt по старому отображаемому имени."""
        old_name, old_faction = old_display_str.rsplit(" — ", 1)
        old_parts = old_name.strip().split(" ", 2)
        target_tsv = f"{old_parts[0]}\t{old_parts[1] if len(old_parts) > 1 else ''}\t{old_parts[2] if len(old_parts) > 2 else ''}\t{old_faction.strip()}"

        new_parts = new_name_str.split(" ", 2)
        s = new_parts[0]
        n = new_parts[1] if len(new_parts) > 1 else (old_parts[1] if len(old_parts) > 1 else "")
        p = new_parts[2] if len(new_parts) > 2 else (old_parts[2] if len(old_parts) > 2 else "")
        new_tsv = f"{s}\t{n}\t{p}\t{new_faction_str}\n"

        with open(self.deputies_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        with open(self.deputies_file_path, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.strip() == target_tsv:
                    f.write(new_tsv)
                else:
                    f.write(line)