import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import shutil
import webbrowser
from datetime import datetime
import re

from config import SOURCES_DIR_NAME, DEPUTIES_FILE_NAME, LEXEMES_DIR_NAME, SOURCES_LIST_FILE_NAME, SYSTEM_FACTIONS

# Безопасные импорты окон сведений
try:
    from gui.editors.factions_editor import FactionDetailsWindow
    from gui.editors.deputies_editor import DeputyDetailsWindow
except ImportError:
    FactionDetailsWindow = None
    DeputyDetailsWindow = None

class _StubDeputyEditor:
    """Заглушка для передачи в DeputyDetailsWindow из окна сведений источника."""
    def __init__(self, db_path):
        self.db_path = db_path
        self.deputies_descriptions = {}
    def _refresh_listbox(self): pass
    def _get_subject_stats(self, *a): return [], []
    def save_deputies(self): pass


class SourcesListWindow:
    """Главное окно списка источников с inline-кнопками и автосохранением."""

    def __init__(self, parent, db_path):
        self.parent = parent
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("Список источников")
        self.window.geometry("920x620")
        self.window.transient(parent)
        self.window.grab_set()
        self.changes_made = False
        self.sources = self._load_sources_data()
        self._build_ui()

    def _load_sources_data(self):
        src_file = os.path.join(self.db_path, SOURCES_LIST_FILE_NAME)
        sources = []
        if not os.path.exists(src_file): return sources

        with open(src_file, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f if l.strip()]

        for fname in lines:
            base = os.path.splitext(fname)[0]
            jpath = os.path.join(self.db_path, LEXEMES_DIR_NAME, f"{base}.json")
            # 🔹 Сохраняем original_name для отслеживания переименований при сохранении
            data = {"name": base, "file": fname, "original_name": base,
                    "url": "", "date": "", "deputies": [], "description": ""}
            if os.path.exists(jpath):
                try:
                    with open(jpath, 'r', encoding='utf-8') as jf:
                        jd = json.load(jf)
                        data.update({"url": jd.get("url", ""), "date": jd.get("date", ""),
                                     "deputies": jd.get("deputies", []), "description": jd.get("description", "")})
                except:
                    pass
            sources.append(data)
        return sources

    def _build_ui(self):
        # Поиск
        self.s_var = tk.StringVar()
        ttk.Label(self.window, text="Поиск источников:").pack(anchor=tk.W, padx=10, pady=(5, 2))
        ttk.Entry(self.window, textvariable=self.s_var).pack(fill=tk.X, padx=10, pady=2)
        self.s_var.trace_add('write', lambda *a: self._render())

        # Список с прокруткой
        cf = ttk.Frame(self.window)
        cf.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(cf)
        sb = ttk.Scrollbar(cf, orient=tk.VERTICAL, command=self.canvas.yview)
        self.sf = ttk.Frame(self.canvas)
        self.sf.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.sf, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Нижние кнопки: Удалить всё, Закрыть
        bf = ttk.Frame(self.window)
        bf.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(bf, text="Удалить всё", command=self.delete_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Закрыть", command=self._on_close).pack(side=tk.RIGHT, padx=5)

        self._render()

    def _render(self):
        for w in self.sf.winfo_children():
            w.destroy()
        q = self.s_var.get().lower()
        for src in self.sources:
            if q in src['name'].lower():
                row = ttk.Frame(self.sf)
                row.pack(fill=tk.X, pady=2, padx=5)

                # Название источника
                ttk.Label(row, text=src['name'], width=55, anchor=tk.W).pack(side=tk.LEFT, padx=5)

                # 🔹 Кнопки-действия: пошире, выровнены строго по правому краю
                btn_f = ttk.Frame(row)
                btn_f.pack(side=tk.RIGHT)
                ttk.Button(btn_f, text="Открыть", width=12, command=lambda s=src: self._open_src(s)).pack(side=tk.LEFT,
                                                                                                          padx=2)
                ttk.Button(btn_f, text="Сведения", width=12, command=lambda s=src: self._show_details(s)).pack(
                    side=tk.LEFT, padx=2)
                ttk.Button(btn_f, text="Удалить", width=12, command=lambda s=src: self._del_src(s)).pack(side=tk.LEFT,
                                                                                                         padx=2)

        self.window.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _open_src(self, src):
        fp = os.path.join(self.db_path, SOURCES_DIR_NAME, src['file'])
        if os.path.exists(fp):
            try:
                os.startfile(fp)
            except:
                webbrowser.open('file://' + fp)
        else:
            messagebox.showwarning("Ошибка", f"Файл '{src['file']}' не найден.")

    def _show_details(self, src):
        try:
            from gui.editors.sources_editor import SourceDetailsWindow
            SourceDetailsWindow(self.window, self.db_path, src, self._update_src)
        except ImportError:
            messagebox.showerror("Ошибка", "Не удалось открыть окно сведений.")

    def _update_src(self, updated, old_name):
        for i, s in enumerate(self.sources):
            if s['name'] == old_name:
                # 🔹 ГАРАНТИЯ СОХРАНЕНИЯ СЛУЖЕБНЫХ ПОЛЕЙ
                # Берем путь к файлу и оригинальное имя из старой записи, если они не были переданы
                updated['file'] = s.get('file', updated.get('file', f"{old_name}.txt"))
                updated['original_name'] = s.get('original_name', old_name)

                self.sources[i] = updated
                self.changes_made = True
                break
        self._render()
        self._save_to_disk(silent=True)

    def _del_src(self, src):
        if messagebox.askyesno("Удаление", f"Удалить '{src['name']}' из списка?"):
            self.sources.remove(src)
            self.changes_made = True
            self._save_to_disk(silent=True)  # Автосохранение
            self._render()

    def delete_all(self):
        if not self.sources:
            messagebox.showinfo("Внимание", "Список источников пуст.")
            return

        dlg = tk.Toplevel(self.window)
        dlg.title("Удаление всех источников")
        dlg.geometry("420x160")
        dlg.transient(self.window)
        dlg.grab_set()
        ttk.Label(dlg, text="Это удалит ВСЕ источники и их метаданные.\nДля подтверждения введите \"УДАЛИТЬ\":").pack(
            pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()

        def execute():
            if entry.get().strip() == "УДАЛИТЬ":
                src_dir = os.path.join(self.db_path, SOURCES_DIR_NAME)
                lex_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
                # Удаляем файлы и JSON с диска
                for src in self.sources:
                    fpath = os.path.join(src_dir, src['file'])
                    if os.path.exists(fpath): os.remove(fpath)
                    jpath = os.path.join(lex_dir, f"{src['name']}.json")
                    if os.path.exists(jpath): os.remove(jpath)

                self.sources.clear()
                self._save_to_disk(silent=True)  # Обновляет sources_list.txt на диске
                self._render()
                dlg.destroy()
                messagebox.showinfo("Успех", "Все источники удалены.")
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")

        ttk.Button(dlg, text="Удалить", command=execute).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=2)

    def _save_to_disk(self, silent=False):
        src_dir = os.path.join(self.db_path, SOURCES_DIR_NAME)
        list_f = os.path.join(self.db_path, SOURCES_LIST_FILE_NAME)
        lex_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)

        new_files = []
        for src in self.sources:
            old_name = src.get('original_name', src['name'])
            new_name = src['name']
            old_txt = os.path.join(src_dir, f"{old_name}.txt")
            new_txt = os.path.join(src_dir, f"{new_name}.txt")
            old_json = os.path.join(lex_dir, f"{old_name}.json")
            new_json = os.path.join(lex_dir, f"{new_name}.json")

            # 🔹 1. Переименование файлов на диске, если имя источника изменилось
            if old_name != new_name:
                if os.path.exists(old_txt) and not os.path.exists(new_txt): os.rename(old_txt, new_txt)
                if os.path.exists(old_json) and not os.path.exists(new_json): os.rename(old_json, new_json)

            # 🔹 2. Копирование нового файла, если в сведениях был выбран другой
            if src.get('file_path') and os.path.exists(src['file_path']):
                new_fn = os.path.basename(src['file_path'])
                dest = os.path.join(src_dir, new_fn)
                try:
                    if not os.path.exists(dest):
                        shutil.copy2(src['file_path'], dest)
                except PermissionError:
                    messagebox.showwarning("Файл занят",
                                           f"Не удалось обновить '{new_fn}'.\n"
                                           f"Файл открыт в другой программе. Закройте его и сохраните снова.")
                    # Не очищаем file_path, оставляем для повторной попытки без перезагрузки окна
                except Exception as e:
                    print(f"Ошибка копирования {new_fn}: {e}")

                # Обновляем связи только если файл успешно скопирован или уже существовал
                if os.path.exists(dest):
                    old = os.path.join(src_dir, src['file'])
                    if os.path.exists(old) and old != dest:
                        try:
                            os.remove(old)
                        except:
                            pass
                    src['file'] = new_fn
                    src.pop('file_path', None)

            new_files.append(f"{new_name}.txt")

            # 🔹 3. Сохранение/обновление JSON метаданных
            d = {"url": src['url'], "date": src['date'], "deputies": src['deputies'],
                 "description": src.get('description', '')}
            with open(new_json, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False, indent=2)

        # Перезаписываем sources_list.txt
        with open(list_f, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_files) + '\n')

        self.changes_made = False
        if not silent: messagebox.showinfo("Успех", "Изменения сохранены на диск.")

    def _on_close(self):
        if self.changes_made:
            if messagebox.askyesno("Сохранить изменения?", "Вы хотите сохранить изменения в списке источников?"):
                self._save_to_disk(silent=True)
        self.window.destroy()

class SourceDetailsWindow:
    """Окно сведений и редактирования источника."""
    def __init__(self, parent, db_path, source_data, on_update_callback=None):
        self.parent = parent
        self.db_path = db_path

        self.data = source_data.copy()
        fallback_name = os.path.splitext(self.data.get('file', ''))[0] or 'unnamed'
        self.current_file_path = os.path.join(self.db_path, SOURCES_DIR_NAME, self.data.get('file', ''))
        self.original_name = self.data.get('name', os.path.basename(self.current_file_path).split('.')[
            0] if self.current_file_path else 'unnamed')
        self.source_name = self.original_name
        self.on_update_callback = on_update_callback
        self.edit_mode = False
        self._is_rendering = False
        self.all_deputies = self._load_all_deputies()
        self.desc_val = self.data.get('description', '')
        self.url_val = self.data.get('url', '')
        self.date_val = self.data.get('date', '')

        self.window = tk.Toplevel(parent)
        self.window.title(f"Сведения: {self.data['name']}")
        self.window.geometry("720x750")
        self.window.transient(parent)
        self.window.grab_set()
        self._build_ui()

    def _load_all_deputies(self):
        deps = []
        dep_file = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        if os.path.exists(dep_file):
            with open(dep_file, 'r', encoding='utf-8') as f:
                for line in f:
                    p = line.strip().split('\t')
                    if len(p) >= 4:
                        surname, name, patronymic, raw_faction = (x.strip() for x in p[:4])

                        # 🔹 ИСПРАВЛЕНИЕ: Очищаем название фракции от описания (@),
                        # чтобы формат строки совпадал с данными из JSON импорта
                        faction = raw_faction.split('@')[0] if '@' in raw_faction else raw_faction

                        full_name = surname if (
                                    name == faction or not name) else f"{surname} {name} {patronymic}".strip()
                        deps.append(f"{full_name} — {faction}")
        return sorted(deps)

    def _open_deputy_details(self, parent_win, helper, dep_str):
        """Открывает сведения о субъекте с правильной обработкой SourceDetailsWindow."""
        try:
            from gui.editors.deputies_editor import DeputyDetailsWindow
            DeputyDetailsWindow(parent_win, helper, dep_str)
        except ImportError:
            pass

    def _format_date_field(self, event):
        if self.ent_date.cget('state') in ('readonly', 'disabled'): return
        entry = self.ent_date
        value = entry.get()
        cursor_pos = entry.index(tk.INSERT)

        digits_only = ''.join(filter(str.isdigit, value))
        formatted = ""
        for i, digit in enumerate(digits_only):
            if i == 2 or i == 4: formatted += '.'
            formatted += digit
        formatted = formatted[:10]

        dots_before = sum(1 for i in range(min(cursor_pos, len(digits_only))) if i == 2 or i == 4)
        new_cursor = min(len(formatted), cursor_pos + dots_before)

        entry.delete(0, tk.END)
        entry.insert(0, formatted)
        entry.icursor(new_cursor)

    def _build_ui(self):
        main = ttk.Frame(self.window, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        self.selected_dep_set = set(self.data.get('deputies', []))

        # Название
        ttk.Label(main, text="Название:").pack(anchor=tk.W)
        self.ent_name = ttk.Entry(main)
        self.ent_name.insert(0, self.data.get('name', ''))
        self.ent_name.config(state="readonly")
        self.ent_name.pack(fill=tk.X, pady=(0, 5))

        # 🔹 Описание (уменьшено)
        ttk.Label(main, text="Описание:").pack(anchor=tk.W)
        desc_f = ttk.Frame(main)
        desc_f.pack(fill=tk.BOTH, expand=False, pady=(0, 5))
        self.txt_desc = tk.Text(desc_f, height=2, wrap=tk.WORD, font=("Segoe UI", 9))
        sb_d = ttk.Scrollbar(desc_f, orient=tk.VERTICAL, command=self.txt_desc.yview)
        self.txt_desc.configure(yscrollcommand=sb_d.set)
        self.txt_desc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_d.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_desc.insert("1.0", self.data.get('description', ''))
        self.txt_desc.config(state="disabled")

        # URL
        ttk.Label(main, text="URL-адрес:").pack(anchor=tk.W)
        self.ent_url = ttk.Entry(main)
        self.ent_url.insert(0, self.data.get('url', ''))
        self.ent_url.config(state="readonly")
        self.ent_url.pack(fill=tk.X, pady=(0, 5))

        # Дата
        ttk.Label(main, text="Дата регистрации:").pack(anchor=tk.W)
        self.ent_date = ttk.Entry(main, width=12)
        raw_dt = self.data.get('date', '')
        if raw_dt:
            try: raw_dt = datetime.strptime(raw_dt, "%Y-%m-%d").strftime("%d.%m.%Y")
            except: pass
        self.ent_date.insert(0, raw_dt)
        self.ent_date.config(state="readonly")
        self.ent_date.bind('<KeyRelease>', self._format_date_field)
        self.ent_date.pack(anchor=tk.W, pady=(0, 5))

        # Файл
        ttk.Label(main, text="Файл:").pack(anchor=tk.W)
        self.ent_file = ttk.Entry(main)
        self.ent_file.insert(0, self.current_file_path)
        self.ent_file.config(state="readonly")
        self.ent_file.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(main, text="Поиск субъектов:").pack(anchor=tk.W)
        self.deputy_search_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.deputy_search_var).pack(fill=tk.X, pady=(0, 5))
        self.deputy_search_var.trace_add('write', lambda *a: self._render_deputies())

        # Субъекты
        ttk.Label(main, text="Субъекты права законодательной инициативы:").pack(anchor=tk.W)
        dep_f = ttk.Frame(main)
        dep_f.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.lb_deps = tk.Listbox(dep_f, selectmode=tk.MULTIPLE, height=4, font=("Segoe UI", 9), exportselection=False)
        sb_dep = ttk.Scrollbar(dep_f, orient=tk.VERTICAL, command=self.lb_deps.yview)
        self.lb_deps.configure(yscrollcommand=sb_dep.set)
        self.lb_deps.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_dep.pack(side=tk.RIGHT, fill=tk.Y)
        current_deps = self.data.get('deputies', [])
        for d in self.all_deputies:
            self.lb_deps.insert(tk.END, d)
            if d in current_deps: self.lb_deps.selection_set(self.lb_deps.size()-1)
        self.lb_deps.bind('<<ListboxSelect>>', self._on_dep_select)
        self.lb_deps.config(state=tk.NORMAL)
        self._render_deputies()  # <-- Вызывается сразу

        # Кнопки управления
        btn_f = ttk.Frame(main)
        btn_f.pack(fill=tk.X, pady=5)
        self.btn_factions = ttk.Button(btn_f, text="Фракции", command=self._show_factions)
        self.btn_factions.pack(side=tk.LEFT, padx=2)
        self.btn_subjects = ttk.Button(btn_f, text="Субъекты", command=self._show_subjects)
        self.btn_subjects.pack(side=tk.LEFT, padx=2)
        self.btn_edit = ttk.Button(btn_f, text="Редактировать", command=self._toggle_edit)
        self.btn_edit.pack(side=tk.LEFT, padx=2)

        ttk.Button(btn_f, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_f, text="Открыть", command=self._open_file).pack(side=tk.RIGHT, padx=2)

    def _open_file(self):
        """Открывает файл источника в программе по умолчанию."""
        if os.path.exists(self.current_file_path):
            try:
                os.startfile(self.current_file_path)  # Для Windows
            except Exception as e:
                # Для других ОС или если не получилось
                import webbrowser
                webbrowser.open('file://' + self.current_file_path)
        else:
            messagebox.showwarning("Файл не найден",
                                   f"Файл не найден по пути:\n{self.current_file_path}")

    def _on_dep_select(self, event=None):
        # 🔹 ИГНОРИРУЕМ СОБЫТИЕ, ЕСЛИ ИДЁТ ПРОГРАММНАЯ ОТРИСОВКА (ПОИСК/ФИЛЬТР)
        if getattr(self, '_is_rendering', False): return
        if not self.edit_mode: return
        if self.edit_mode:
            # 1. Собираем элементы, выбранные в текущем (возможно отфильтрованном) списке
            current_visible_selected = set()
            for idx in self.lb_deps.curselection():
                current_visible_selected.add(self.lb_deps.get(idx))

            # 2. Находим элементы, которые были выбраны ранее, но сейчас скрыты из-за поиска
            all_currently_visible = {self.lb_deps.get(i) for i in range(self.lb_deps.size())}
            hidden_selected = self.selected_dep_set - all_currently_visible

            # 3. Обновляем общее множество: скрытые выбранные + новые видимые выбранные
            self.selected_dep_set = hidden_selected | current_visible_selected

            # 4. Перерисовываем список, чтобы обновить выделение и сортировку
            # Используем after, чтобы дать Tkinter завершить обработку клика
            self.window.after(10, self._render_deputies)

    def _render_deputies(self):
        # 🔹 ЗАЩИТА ОТ РЕКУРСИИ ПРИ БЫСТРОМ ВВОДЕ В ПОИСК
        if getattr(self, '_is_rendering', False): return
        self._is_rendering = True

        self.lb_deps.delete(0, tk.END)
        query = self.deputy_search_var.get().lower()
        filtered = [d for d in self.all_deputies if not query or query in d.lower()]
        sorted_deps = sorted(filtered, key=self._get_dep_sort_key)

        for d in sorted_deps:
            self.lb_deps.insert(tk.END, d)
            if d in self.selected_dep_set:
                self.lb_deps.selection_set(self.lb_deps.size() - 1)

        self._is_rendering = False

    def _pick_file(self):
        p = filedialog.askopenfilename(filetypes=[("Text/Word", "*.txt;*.docx")])
        if p:
            self.current_file_path = os.path.abspath(p)  # Сохраняем абсолютный путь
            self.ent_file.delete(0, tk.END)
            self.ent_file.insert(0, self.current_file_path)

    def _toggle_edit(self):
        if not self.edit_mode:
            self.edit_mode = True
            for w in [self.ent_name, self.ent_url, self.ent_date]: w.config(state="normal")
            self.txt_desc.config(state="normal")
            self.lb_deps.config(state="normal", cursor="xterm")
            self.btn_edit.config(text="Сохранить")
            self.ent_name.focus()
        else: self._save_changes()

    def _save_changes(self):
        if not self.edit_mode: return

        new_name = self.ent_name.get().strip()
        new_url = self.ent_url.get().strip()
        new_date = self.ent_date.get().strip()
        new_desc = self.txt_desc.get("1.0", tk.END).strip()

        # 1. Валидация
        if not new_name:
            messagebox.showwarning("Ошибка", "Название не может быть пустым.");
            return
        if re.search(r'[<>:"/\\|?*]', new_name) or any(ord(c) < 32 for c in new_name):
            messagebox.showwarning("Ошибка", "Название содержит недопустимые символы.");
            return
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', new_date):
            messagebox.showwarning("Ошибка", "Дата должна быть в формате ДД.ММ.ГГГГ.");
            return

        # 2. Гарантируем наличие имени файла для сохранения
        if not hasattr(self, 'source_name') or not self.source_name:
            self.source_name = self.data.get('name', os.path.basename(self.current_file_path).split('.')[0])

        # 3. Обновляем локальный словарь данных
        self.data['name'] = new_name
        self.data['url'] = new_url
        self.data['description'] = new_desc
        self.data['original_name'] = self.source_name
        try:
            self.data['date'] = datetime.strptime(new_date, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            self.data['date'] = new_date
        self.data['deputies'] = list(self.selected_dep_set)

        # 4. Прямая запись в JSON (работает независимо от callback)
        lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
        json_path = os.path.join(lexemes_dir, f"{self.source_name}.json")
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файл:\n{e}")
            return

        # 5. Возвращаем интерфейс в режим только для чтения
        self.edit_mode = False
        for w in [self.ent_name, self.ent_url, self.ent_date]: w.config(state="readonly")
        self.txt_desc.config(state="disabled")
        self.lb_deps.config(state="normal")  # 🔹 Блокируем список обратно
        self.btn_edit.config(text="Редактировать")

        # Обновляем служебные переменные для следующих сохранений
        self.original_name = new_name
        self.window.title(f"Сведения: {self.data['name']}")

        # Уведомляем родителя, если callback передан
        if self.on_update_callback:
            self.on_update_callback(self.data, self.source_name)

        messagebox.showinfo("Успех", "Изменения сохранены.")

    def _get_dep_sort_key(self, dep_str):
        """Возвращает кортеж для сортировки по правилам:
        1. Выбранные субъекты первыми.
        2. Внутри групп: системные фракции -> несистемные (по алфавиту).
        3. Внутри фракций: по алфавиту ФИО."""
        if " — " in dep_str:
            fio, faction = dep_str.split(" — ", 1)
        else:
            fio, faction = dep_str, ""

        fio_clean = fio.strip().lower()
        faction_clean = faction.strip()

        # 0 = в начало списка, 1 = в конец
        is_selected = 0 if dep_str in self.selected_dep_set else 1
        is_system = 0 if faction_clean in SYSTEM_FACTIONS else 1

        return (is_selected, is_system, faction_clean.lower(), fio_clean)

    def _get_factions_from_deps(self):
        facs = set()
        for d in self.data.get('deputies', []):
            if " — " in d: facs.add(d.split(" — ", 1)[1].strip())
        return sorted(facs) if facs else ["Фракция не определена"]

    def _open_filtered_multi_list(self, title, items, pre_selected):
        """Открывает окно с поиском и мульти-выделением (логика как в ImportWindow)."""
        win = tk.Toplevel(self.window)
        win.title(title)
        win.geometry("420x400")
        win.transient(self.window)
        win.grab_set()

        ttk.Label(win, text="Поиск:").pack(anchor=tk.W, padx=10, pady=(5, 2))
        search_var = tk.StringVar()
        ttk.Entry(win, textvariable=search_var).pack(fill=tk.X, padx=10, pady=(0, 5))

        list_frame = ttk.Frame(win)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        lb = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, height=12, exportselection=False)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        selected_set = set(pre_selected)

        def render():
            lb.delete(0, tk.END)
            q = search_var.get().lower()
            for item in items:
                if not q or q in item.lower():
                    lb.insert(tk.END, item)
                    if item in selected_set: lb.selection_set(lb.size() - 1)

        search_var.trace_add('write', lambda *a: render())
        render()
        ttk.Button(win, text="Закрыть", command=win.destroy).pack(pady=10)

    def _show_factions(self):
        win = tk.Toplevel(self.window)
        win.title("Фракции источника")
        win.geometry("350x400")
        win.transient(self.window)
        win.grab_set()

        ttk.Label(win, text="Поиск:").pack(anchor=tk.W, padx=5, pady=(5, 0))
        s_var = tk.StringVar()
        ttk.Entry(win, textvariable=s_var).pack(fill=tk.X, padx=5, pady=(0, 5))

        cf = ttk.Frame(win);
        cf.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        cvs = tk.Canvas(cf);
        sb = ttk.Scrollbar(cf, orient=tk.VERTICAL, command=cvs.yview)
        sf = ttk.Frame(cvs);
        sf.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=sf, anchor="nw");
        cvs.configure(yscrollcommand=sb.set)
        cvs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True);
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def render():
            for w in sf.winfo_children(): w.destroy()
            q = s_var.get().lower()
            facs = self._get_factions_from_deps()
            if not facs or (facs == ["Фракция не определена"] and not self.data.get('deputies')):
                # 🔹 НОВОЕ: Сообщение если фракций нет
                ttk.Label(sf, text="Фракции не найдены", foreground="gray").pack(pady=20)
                return
            for fac in (facs if not q else [f for f in facs if q in f.lower()]):
                ttk.Button(sf, text=fac, width=40,
                           command=lambda f=fac: self._show_faction_details(f)).pack(fill=tk.X, pady=2)

        s_var.trace_add('write', lambda *a: render())
        render()

    def _show_faction_details(self, fac_name):
        try:
            from gui.editors.factions_editor import FactionDetailsWindow
            class _Stub:
                def __init__(self, p):
                    self.db_path = p
                    self.deputies_descriptions = {}
                    self.desc_file = os.path.join(p, "factions_desc.json")  # 🔹 ДОБАВЛЕНО

                def _refresh_listbox(self): pass

                def _get_subject_stats(self, *a): return [], []

                def save_deputies(self): pass

            FactionDetailsWindow(self.window, fac_name, self.db_path)
        except ImportError:
            messagebox.showerror("Ошибка", "Не удалось открыть сведения о фракции.")

    def _show_subjects(self):
        win = tk.Toplevel(self.window)
        win.title("Субъекты источника")
        win.geometry("450x400")
        win.transient(self.window)
        win.grab_set()

        ttk.Label(win, text="Поиск:").pack(anchor=tk.W, padx=5, pady=(5, 0))
        s_var = tk.StringVar()
        ttk.Entry(win, textvariable=s_var).pack(fill=tk.X, padx=5, pady=(0, 5))

        cf = ttk.Frame(win);
        cf.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        cvs = tk.Canvas(cf);
        sb = ttk.Scrollbar(cf, orient=tk.VERTICAL, command=cvs.yview)
        sf = ttk.Frame(cvs);
        sf.bind("<Configure>", lambda e: cvs.configure(scrollregion=cvs.bbox("all")))
        cvs.create_window((0, 0), window=sf, anchor="nw");
        cvs.configure(yscrollcommand=sb.set)
        cvs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True);
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 🔹 ЗАМЕНА _Stub на класс, вычисляющий статистику "на лету"
        class _SubjectHelper:
            def __init__(self, db_path):
                self.db_path = db_path
                self.deputies_descriptions = {}
                self.original_deputies = []
                self.save_deputies = lambda: None
                self._load_db()

            def _load_db(self):
                dep_file = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
                if os.path.exists(dep_file):
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

                norm_target = re.sub(r'\s+', ' ', subject_name.lower().replace('ё', 'е')).strip()
                for fname in os.listdir(lex_dir):
                    if not fname.endswith('.json'): continue
                    try:
                        with open(os.path.join(lex_dir, fname), 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        for dep_str in data.get('deputies', []):
                            if ' — ' not in dep_str: continue
                            dep_name = dep_str.split(' — ', 1)[0].strip().lower().replace('ё', 'е')
                            if norm_target == dep_name or norm_target in dep_name:
                                sources.append(fname.replace('.json', '.txt'))
                                d = data.get('date')
                                if d: dates.append(d)
                                break
                    except:
                        pass
                return sources, sorted(dates)

        helper = _SubjectHelper(self.db_path)

        def render():
            for w in sf.winfo_children(): w.destroy()
            q = s_var.get().lower()
            deps = self.data.get('deputies', [])
            for dep in (deps if not q else [d for d in deps if q in d.lower()]):
                try:
                    from gui.editors.deputies_editor import DeputyDetailsWindow
                    # 🔹 Передаём helper вместо _Stub
                    ttk.Button(sf, text=dep, width=50,
                               command=lambda d=dep: self._open_deputy_details(win, helper, d)).pack(fill=tk.X, pady=2)
                except ImportError:
                    pass

        s_var.trace_add('write', lambda *a: render())
        render()