import tkinter as tk
from tkinter import ttk, messagebox
import os
import shutil
import json
from datetime import datetime
import time

from config import TEXTDATA_DIR, MAIN_FILE_NAME


class DatabaseDetailsWindow:
    def __init__(self, parent, db_path, on_rename_callback=None):
        self.on_rename_callback = on_rename_callback
        self.parent = parent
        self.db_path = db_path
        self.edit_mode = False

        # Пути к файлам БД
        self.metadata_file = os.path.join(db_path, "metadata.json")
        self.sources_dir = os.path.join(db_path, "sources")
        self.deputies_file = os.path.join(db_path, "deputies.txt")
        self.factions_file = os.path.join(db_path, "factions.txt")

        # Загружаем текущие данные
        self.name_val = os.path.basename(db_path)
        self.desc_val = ""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    self.name_val = meta.get("name", self.name_val)
                    self.desc_val = meta.get("description", "")
            except:
                pass

        # Создаем окно
        self.window = tk.Toplevel(parent)
        self.window.title(f"Сведения: {self.name_val}")
        self.window.geometry("650x600")
        self.window.transient(parent)
        self.window.grab_set()

        self._build_ui()
        self._update_stats()

    def _build_ui(self):
        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- НАЗВАНИЕ ---
        ttk.Label(main_frame, text="Название базы данных:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        self.entry_name = ttk.Entry(main_frame, width=50)
        self.entry_name.pack(fill=tk.X, pady=(0, 15))
        self.entry_name.insert(0, self.name_val)
        self.entry_name.config(state="readonly")  # По умолчанию только чтение

        # --- ОПИСАНИЕ ---
        ttk.Label(main_frame, text="Описание:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        frame_desc = ttk.Frame(main_frame)
        frame_desc.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.text_desc = tk.Text(frame_desc, height=8, wrap=tk.WORD, font=("Segoe UI", 9))
        sb_desc = ttk.Scrollbar(frame_desc, orient=tk.VERTICAL, command=self.text_desc.yview)
        self.text_desc.configure(yscrollcommand=sb_desc.set)

        self.text_desc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_desc.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_desc.insert(tk.END, self.desc_val)
        self.text_desc.config(state="disabled")  # По умолчанию только чтение

        # --- СТАТИСТИКА (LabelFrame) ---
        stats_frame = ttk.LabelFrame(main_frame, text="Статистика базы данных", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 15))

        self.lbl_sources = ttk.Label(stats_frame, text="Источники: ...")
        self.lbl_sources.pack(anchor=tk.W, pady=2)

        self.lbl_deputies = ttk.Label(stats_frame, text="Субъекты: ...")
        self.lbl_deputies.pack(anchor=tk.W, pady=2)

        self.lbl_factions = ttk.Label(stats_frame, text="Фракции: ...")
        self.lbl_factions.pack(anchor=tk.W, pady=2)

        # --- КНОПКИ ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        # Кнопка Редактировать/Сохранить
        self.btn_toggle = ttk.Button(btn_frame, text="Редактировать", command=self.toggle_edit)
        self.btn_toggle.pack(side=tk.LEFT)

        # Кнопка Закрыть
        ttk.Button(btn_frame, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT)

    def _update_stats(self):
        """Считает файлы и обновляет лейблы"""
        # 1. Источники
        count_sources = 0
        if os.path.exists(self.sources_dir):
            count_sources = len([f for f in os.listdir(self.sources_dir) if f.endswith('.txt')])
        self.lbl_sources.config(text=f"Источники: {count_sources}")

        # 2. Субъекты
        count_deps = 0
        if os.path.exists(self.deputies_file):
            with open(self.deputies_file, 'r', encoding='utf-8') as f:
                count_deps = sum(1 for line in f if line.strip())
        self.lbl_deputies.config(text=f"Субъекты: {count_deps}")

        # 3. Фракции
        count_facs = 0
        if os.path.exists(self.factions_file):
            with open(self.factions_file, 'r', encoding='utf-8') as f:
                count_facs = sum(1 for line in f if line.strip())
        self.lbl_factions.config(text=f"Фракции: {count_facs}")

    def toggle_edit(self):
        """Переключает режим редактирования"""
        if not self.edit_mode:
            # Включаем редактирование
            self.edit_mode = True
            self.entry_name.config(state="normal")
            self.text_desc.config(state="normal")
            self.btn_toggle.config(text="Сохранить")
            self.entry_name.focus()
        else:
            # Сохраняем
            self.save_data()

    def save_data(self):
        new_name = self.entry_name.get().strip()
        new_desc = self.text_desc.get("1.0", tk.END).strip()
        if not new_name:
            messagebox.showwarning("Ошибка", "Название базы данных не может быть пустым.")
            return

        try:
            old_path = self.db_path
            new_path = os.path.join(os.path.dirname(old_path), new_name)

            # 🔹 ИСПРАВЛЕНИЕ: Проверяем существование, но ИГНОРИРУЕМ, если путь совпадает с текущим
            if os.path.exists(new_path) and os.path.abspath(new_path) != os.path.abspath(old_path):
                messagebox.showerror("Ошибка", "База с таким названием уже существует.")
                return

            # Переименовываем папку ТОЛЬКО если имя реально изменилось
            if os.path.abspath(old_path) != os.path.abspath(new_path):
                os.rename(old_path, new_path)
                self.db_path = new_path
                self.name_val = new_name

            # 2. Сохраняем metadata.json (всегда, даже если имя не менялось)
            data = {"name": new_name, "description": new_desc, "last_modified": datetime.now().isoformat()}
            with open(os.path.join(self.db_path, "metadata.json"), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 3. Обновляем UI
            messagebox.showinfo("Успех", "Изменения сохранены.")
            self.edit_mode = False
            self.entry_name.config(state="readonly")
            self.text_desc.config(state="disabled")
            self.btn_toggle.config(text="Редактировать")
            self.window.title(f"Сведения: {new_name}")

            # 4. Сообщаем списку баз обновиться
            if self.on_rename_callback:
                self.on_rename_callback()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{e}")

class DatabaseListWindow:
    def __init__(self, parent, open_callback):
        self.parent = parent
        self.open_callback = open_callback
        self.window = tk.Toplevel(parent)
        self.window.title("Открыть базу данных")
        self.window.geometry("850x520")
        self.window.transient(parent)
        self.window.grab_set()

        # 🔹 1. Шапка таблицы
        hdr = ttk.Frame(self.window)
        hdr.pack(fill=tk.X, padx=10, pady=(10, 2))
        ttk.Label(hdr, text="Название", width=32, anchor=tk.W).pack(side=tk.LEFT, padx=5)
        ttk.Label(hdr, text="Дата создания", width=20, anchor=tk.CENTER).pack(side=tk.LEFT, padx=5)
        ttk.Label(hdr, text="Дата изменения", width=20, anchor=tk.CENTER).pack(side=tk.LEFT, padx=5)
        ttk.Label(hdr, text="Действия", width=22, anchor=tk.CENTER).pack(side=tk.LEFT, padx=5)
        ttk.Separator(self.window, orient="horizontal").pack(fill=tk.X, padx=10)

        # 🔹 Поисковая строка с плейсхолдером
        self.db_search_var = tk.StringVar()
        self.db_search_entry = tk.Entry(self.window, textvariable=self.db_search_var,
                                        fg="gray", font=("Segoe UI", 9, "italic"))
        self.db_search_entry.insert(0, "Поиск")
        self.db_search_entry.pack(fill=tk.X, padx=10, pady=(2, 5))

        def _on_focus_in(e):
            if self.db_search_entry.get() == "Поиск":
                self.db_search_entry.delete(0, tk.END)
                self.db_search_entry.config(fg="black", font=("Segoe UI", 9, "normal"))

        def _on_focus_out(e):
            if not self.db_search_entry.get():
                self.db_search_entry.insert(0, "Поиск")
                self.db_search_entry.config(fg="gray", font=("Segoe UI", 9, "italic"))

        self.db_search_entry.bind('<FocusIn>', _on_focus_in)
        self.db_search_entry.bind('<FocusOut>', _on_focus_out)
        self.db_search_entry.bind('<KeyRelease>', lambda e: self._filter_dbs())

        # 🔹 2. Контейнер для Canvas и Scrollbar (занимает всё доступное место)
        scroll_container = ttk.Frame(self.window)
        scroll_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(scroll_container)
        sb = ttk.Scrollbar(scroll_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)

        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        # 🔹 Привязка колесика мыши (восстановлено: работает и на canvas, и на контенте)
        def _on_mousewheel(e):
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        self.canvas.bind("<MouseWheel>", _on_mousewheel)
        self.content.bind("<MouseWheel>", _on_mousewheel)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # 🔹 3. Сканирование и первичная отрисовка
        self.all_dbs = self._scan_databases()
        self._filter_dbs()

        # 🔹 4. Кнопка закрытия (ВНЕ области прокрутки, всегда внизу)
        ttk.Button(self.window, text="Закрыть", command=self.window.destroy).pack(pady=10)

    def _filter_dbs(self, event=None):
        """Обновляет список баз данных в соответствии с поисковым запросом."""
        query = self.db_search_var.get().strip().lower()
        if query == "поиск":
            query = ""  # Игнорируем текст-плейсхолдер, чтобы изначально показывать все базы

        # Очищаем текущий список
        for widget in self.content.winfo_children():
            widget.destroy()

        # Отрисовываем только подходящие элементы
        for name, created, modified in self.all_dbs:
            if query in name.lower():
                row = ttk.Frame(self.content)
                row.pack(fill=tk.X, pady=2, padx=5)
                ttk.Label(row, text=name, width=32, anchor=tk.W).pack(side=tk.LEFT, padx=5)
                ttk.Label(row, text=created, width=20, anchor=tk.CENTER).pack(side=tk.LEFT, padx=5)
                ttk.Label(row, text=modified, width=20, anchor=tk.CENTER).pack(side=tk.LEFT, padx=5)

                btns = ttk.Frame(row)
                btns.pack(side=tk.LEFT, padx=5)
                # Формируем полный путь один раз, чтобы избежать проблем с замыканиями
                db_path = os.path.join(TEXTDATA_DIR, name)

                # Передаём имя базы в замыкание правильно
                ttk.Button(btns, text="Открыть", command=lambda n=name: self._open_db(n)).pack(side=tk.LEFT, padx=2)
                ttk.Button(btns, text="Сведения", command=lambda n=name: self.open_details_with_refresh(n)).pack(side=tk.LEFT, padx=2)
                ttk.Button(btns, text="Удалить", command=lambda n=name: self._confirm_delete_db(n)).pack(side=tk.LEFT,
                                                                                                         padx=2)
        # Обновляем область прокрутки
        self.window.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _confirm_delete_db(self, db_name):
        if not messagebox.askyesno("Внимание",
                                   f"Вы уверены, что хотите удалить базу данных '{db_name}'? Это действие нельзя отменить."):
            return

        dlg = tk.Toplevel(self.window)
        dlg.title("Подтверждение удаления")
        dlg.geometry("400x150")
        dlg.transient(self.window)
        dlg.grab_set()

        ttk.Label(dlg, text=f'Для удаления введите "УДАЛИТЬ": ').pack(pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()

        def do_del():
            if entry.get().strip() == "УДАЛИТЬ":
                dlg.destroy()
                db_path = os.path.join(TEXTDATA_DIR, db_name)
                try:
                    shutil.rmtree(db_path)
                    messagebox.showinfo("Успех", f'База данных "{db_name}" удалена.')
                    # Обновляем список баз данных
                    self.all_dbs = self._scan_databases()
                    self._filter_dbs()
                except Exception as e:
                    messagebox.showerror("Ошибка", str(e))
            else:
                messagebox.showwarning("Ошибка", 'Вы не ввели "УДАЛИТЬ".')
                entry.delete(0, tk.END)

        ttk.Button(dlg, text="Удалить", command=do_del).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=5)

    def open_details_with_refresh(self, db_name):
        """Открывает окно сведений и передаёт колбэк для обновления списка после переименования"""
        db_path = os.path.join(TEXTDATA_DIR, db_name)

        def refresh_callback():
            # Пересканируем папку и перерисовываем список
            self.all_dbs = self._scan_databases()
            self._filter_dbs()

        DatabaseDetailsWindow(self.window, db_path, on_rename_callback=refresh_callback)

    def _scan_databases(self):
        """Сканирует директорию TEXTDATA_DIR и возвращает список кортежей (name, created, modified)."""
        dbs = []
        if not os.path.exists(TEXTDATA_DIR): return dbs
        for item in os.listdir(TEXTDATA_DIR):
            fp = os.path.join(TEXTDATA_DIR, item)
            if os.path.isdir(fp) and os.path.exists(os.path.join(fp, MAIN_FILE_NAME)):
                cr, mod = "Неизвестно", time.strftime("%d.%m.%Y %H:%M", time.localtime(os.path.getmtime(fp)))
                try:
                    with open(os.path.join(fp, MAIN_FILE_NAME), 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith("created_at="):
                                cr = datetime.fromisoformat(line.split("=", 1)[1].strip()).strftime("%d.%m.%Y %H:%M")
                                break
                except:
                    pass
                dbs.append((item, cr, mod))
        return sorted(dbs, key=lambda x: x[0])

    def _open_db(self, name):
        self.window.destroy()
        self.open_callback(name)