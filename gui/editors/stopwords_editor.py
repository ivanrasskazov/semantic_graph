import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
from config import DEFAULTS_DIR, STOPWORDS_FILE_NAME

# Список категорий (вкладок)
CATEGORIES = ["Местоимения", "Предлоги", "Союзы", "Рекомендуемое", "Прочее"]


class StopwordsEditorWindow:
    def __init__(self, parent, db_path, is_defaults=False):
        self.parent = parent
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("Список стоп-слов")
        self.window.geometry("880x620")
        self.window.transient(parent)
        self.window.grab_set()
        self.changes_made = False
        self.stopwords_file = os.path.join(db_path, STOPWORDS_FILE_NAME)
        self.is_defaults = is_defaults

        # Хранилище: список кортежей (word, category)
        self.stopwords = []

        # Загрузка данных
        self._load_stopwords()

        # UI: Notebook для вкладок
        ttk.Label(self.window, text="Стоп-слова по категориям:").pack(anchor=tk.W, padx=10, pady=(5, 0))

        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.listboxes = {}

        # Создаем вкладки
        tabs_order = ["Все"] + CATEGORIES
        for cat in tabs_order:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=cat)

            lb = tk.Listbox(frame, font=("Segoe UI", 9))
            sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)

            lb.bind('<Delete>', lambda e: self.delete_selected())
            self.listboxes[cat] = lb

        # Событие переключения вкладки
        self.notebook.bind('<<NotebookTabChanged>>', lambda e: self._filter_and_refresh())

        # Поиск
        self.search_var = tk.StringVar()
        search_frame = ttk.Frame(self.window)
        search_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(search_frame, text="Поиск:").pack(side=tk.LEFT, padx=(0, 5))
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_var.trace_add('write', lambda *args: self._filter_and_refresh())

        # Кнопки управления
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Добавить", command=self._open_add_dialog).pack(side=tk.LEFT, padx=5)

        self.import_btn = ttk.Button(btn_frame, text="Импортировать", command=self.import_from_file)
        self.import_btn.pack(side=tk.LEFT, padx=5)
        self._setup_tip(self.import_btn, "Формат: \"слово\tкатегория\" или просто \"слово\" (категория \"Прочее\").")

        if not self.is_defaults:
            ttk.Button(btn_frame, text="Добавить по умолчанию", command=self._merge_defaults).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Удалить всё", command=self.delete_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.on_close).pack(side=tk.RIGHT, padx=5)

        self._filter_and_refresh()

    def _load_stopwords(self):
        """Загружает стоп-слова из файла БД или дефолтов."""
        self.stopwords = []
        target_file = self.stopwords_file if os.path.exists(self.stopwords_file) else os.path.join(DEFAULTS_DIR,
                                                                                                   STOPWORDS_FILE_NAME)

        if os.path.exists(target_file):
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        parts = line.split('\t')
                        word = parts[0].strip().lower()
                        # Определяем категорию
                        category = parts[1].strip() if len(parts) > 1 else "Прочее"
                        if category not in CATEGORIES: category = "Прочее"
                        self.stopwords.append((word, category))
            except Exception as e:
                print(f"Ошибка загрузки стоп-слов: {e}")

    def _filter_and_refresh(self):
        """Обновляет списки на всех вкладках с учётом поиска."""
        query = self.search_var.get().lower()
        active_tab = self.notebook.tab(self.notebook.select(), "text")

        # Очищаем все списки
        for lb in self.listboxes.values():
            lb.delete(0, tk.END)

        # Фильтрация и сортировка
        filtered_items = []
        for word, cat in self.stopwords:
            if query and query not in word: continue
            filtered_items.append((word, cat))

        # Сортировка: по категории (для порядка), потом по слову
        filtered_items.sort(key=lambda x: (CATEGORIES.index(x[1]) if x[1] in CATEGORIES else 99, x[0]))

        # Заполнение вкладок
        for word, cat in filtered_items:
            # Вкладка "Все": показываем "слово — категория"
            if active_tab == "Все":
                display = f"{word} — {cat}"
                self.listboxes["Все"].insert(tk.END, display)

            # Вкладки категорий: показываем только слово, если категория совпадает
            if cat == active_tab and active_tab != "Все":
                self.listboxes[active_tab].insert(tk.END, word)

    def _open_add_dialog(self):
        """Диалог добавления стоп-слова с выбором категории."""
        dlg = tk.Toplevel(self.window)
        dlg.title("Добавить стоп-слово")
        dlg.geometry("350x260")  # Чуть увеличил высоту для предупреждения
        dlg.transient(self.window)
        dlg.grab_set()

        ttk.Label(dlg, text="Стоп-слово:").pack(anchor=tk.W, padx=10, pady=(10, 2))
        word_var = tk.StringVar()
        word_entry = ttk.Entry(dlg, textvariable=word_var)
        word_entry.pack(fill=tk.X, padx=10, pady=(0, 5))

        # 🔹 НОВОЕ: Предупреждение о запрете символов
        warning_label = ttk.Label(
            dlg,
            text="⚠️ Запрещены пробелы, знаки препинания (включая дефис) и цифры.",
            foreground="red",
            font=("Segoe UI", 8)
        )
        warning_label.pack(anchor=tk.W, padx=10, pady=(0, 10))

        ttk.Label(dlg, text="Категория:").pack(anchor=tk.W, padx=10, pady=(0, 2))
        cat_var = tk.StringVar(value="Прочее")
        cat_combo = ttk.Combobox(dlg, textvariable=cat_var, values=CATEGORIES, state="readonly")
        cat_combo.pack(fill=tk.X, padx=10, pady=(0, 10))

        def confirm():
            word = word_var.get().strip().lower()
            cat = cat_var.get()

            if not word:
                messagebox.showwarning("Ошибка", "Введите слово.")
                return

            # 🔹 ПРОВЕРКА 1: Только буквы (кириллица/латиница)
            # ^ - начало строки, $ - конец строки. + - один или более символов.
            if not re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', word):
                messagebox.showwarning(
                    "Ошибка ввода",
                    "Стоп-слово может содержать ТОЛЬКО буквы.\n"
                    "Пробелы, дефисы, цифры и знаки препинания запрещены."
                )
                return

            # 🔹 ПРОВЕРКА 2: Уникальность слова (независимо от категории)
            # Проверяем, есть ли такое слово (w) в любом кортеже списка self.stopwords
            if any(w == word for w, c in self.stopwords):
                messagebox.showwarning(
                    "Дубликат",
                    f"Стоп-слово '{word}' уже существует в списке.\n"
                    "Добавление дубликатов запрещено вне зависимости от категории."
                )
                return

            # Если всё хорошо — добавляем
            self.stopwords.append((word, cat))
            self.changes_made = True
            self._filter_and_refresh()
            dlg.destroy()

        ttk.Button(dlg, text="Добавить", command=confirm).pack(pady=10)
        word_entry.focus()

    def delete_selected(self):
        """Удаляет выделенное стоп-слово."""
        active_tab = self.notebook.tab(self.notebook.select(), "text")
        lb = self.listboxes[active_tab]
        sel = lb.curselection()
        if not sel: return

        idx = sel[0]
        display_text = lb.get(idx)

        word, cat = "", ""
        # Парсинг отображаемого текста
        if active_tab == "Все":
            if " — " in display_text:
                parts = display_text.split(" — ", 1)
                word = parts[0].strip()
                cat = parts[1].strip()
            else:
                return
        else:
            word = display_text
            cat = active_tab

        # Удаление из хранилища
        if (word, cat) in self.stopwords:
            self.stopwords.remove((word, cat))
            self.changes_made = True
            self._filter_and_refresh()

    def delete_all(self):
        """Удаляет все стоп-слова с подтверждением."""
        if not self.stopwords: return
        dlg = tk.Toplevel(self.window)
        dlg.title("Удаление всех стоп-слов")
        dlg.geometry("400x150")
        dlg.transient(self.window)
        dlg.grab_set()
        ttk.Label(dlg, text="Для удаления всех стоп-слов введите \"УДАЛИТЬ\":").pack(pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()

        def execute():
            if entry.get().strip() == "УДАЛИТЬ":
                self.stopwords.clear()
                self.changes_made = True
                self._filter_and_refresh()
                dlg.destroy()
                messagebox.showinfo("Успех", "Все стоп-слова удалены.")
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")

        ttk.Button(dlg, text="Удалить", command=execute).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=2)

    def _merge_defaults(self):
        """Добавляет стоп-слова из настроек по умолчанию."""
        if not messagebox.askyesno("Подтверждение", "Добавить стоп-слова по умолчанию?"): return
        def_path = os.path.join(DEFAULTS_DIR, STOPWORDS_FILE_NAME)
        if not os.path.exists(def_path): return

        defaults = []
        try:
            with open(def_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    parts = line.split('\t')
                    word = parts[0].strip().lower()
                    category = parts[1].strip() if len(parts) > 1 else "Прочее"
                    if category not in CATEGORIES: category = "Прочее"
                    defaults.append((word, category))
        except:
            return

        added = 0
        for item in defaults:
            if item not in self.stopwords:
                self.stopwords.append(item)
                added += 1

        if added > 0:
            self.changes_made = True
            self._filter_and_refresh()
            messagebox.showinfo("Готово", f"Добавлено {added} стоп-слов.")
        else:
            messagebox.showinfo("Информация", "Все стоп-слова уже существуют.")

    def import_from_file(self):
        """Импорт стоп-слов из файла."""
        file_path = filedialog.askopenfilename(
            title="Выберите файл со стоп-словами",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if not file_path: return

        added_count = 0
        skipped_invalid = 0  # Пропущено из-за знаков/пробелов
        skipped_duplicate = 0  # Пропущено из-за дубликата

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line: continue

                    parts = line.split('\t')
                    word = parts[0].strip().lower()
                    category = parts[1].strip() if len(parts) > 1 else "Прочее"

                    # 🔹 ПРОВЕРКА 1: Формат слова (только буквы)
                    if not re.match(r'^[a-zA-Zа-яА-ЯёЁ]+$', word):
                        skipped_invalid += 1
                        continue

                    # 🔹 ПРОВЕРКА 2: Уникальность слова (независимо от категории)
                    if any(w == word for w, c in self.stopwords):
                        skipped_duplicate += 1
                        continue

                    # Проверка корректности категории
                    if category not in CATEGORIES:
                        category = "Прочее"

                    # Добавление
                    self.stopwords.append((word, category))
                    added_count += 1

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось импортировать файл: {e}")
            return

        # Формирование итогового сообщения
        msg_parts = [f"Успешно добавлено: {added_count}"]
        if skipped_invalid > 0:
            msg_parts.append(f"Пропущено (неверный формат): {skipped_invalid}")
        if skipped_duplicate > 0:
            msg_parts.append(f"Пропущено (дубликаты): {skipped_duplicate}")

        if added_count > 0:
            self.changes_made = True
            self._filter_and_refresh()
            messagebox.showinfo("Импорт", "\n".join(msg_parts))
        else:
            messagebox.showinfo("Импорт", "Новых стоп-слов не найдено или все они недопустимы.")

    def on_close(self):
        """Сохраняет изменения при закрытии."""
        if self.changes_made and messagebox.askyesno("Сохранить изменения?", "Сохранить список стоп-слов?"):
            try:
                with open(self.stopwords_file, 'w', encoding='utf-8') as f:
                    # Сортировка при сохранении: по категории, потом по слову
                    for word, cat in sorted(self.stopwords,
                                            key=lambda x: (CATEGORIES.index(x[1]) if x[1] in CATEGORIES else 99, x[0])):
                        f.write(f"{word}\t{cat}\n")
                os.utime(self.db_path, None)
                messagebox.showinfo("Успех", "Список стоп-слов сохранён.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        self.window.destroy()

    def _setup_tip(self, widget, text):
        """Всплывающая подсказка."""
        tw = None

        def show(e):
            nonlocal tw
            if tw and tw.winfo_exists(): tw.destroy()
            tw = tk.Toplevel(self.window)
            tw.wm_overrideredirect(True)
            ttk.Label(tw, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                      font=("tahoma", "8", "normal")).pack(ipadx=4, ipady=2)
            x, y = widget.winfo_rootx() + widget.winfo_width() + 5, widget.winfo_rooty() + 5
            tw.wm_geometry(f"+{x}+{y}")

        def hide(e):
            nonlocal tw
            if tw and tw.winfo_exists(): tw.destroy(); tw = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)