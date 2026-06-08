import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import zipfile
import shutil
import tempfile
from config import MODULES_DIR
import importlib.util
import sys


class ModulesListWindow:
    """Окно управления модулями программы."""

    def __init__(self, parent, db_path=None):
        self.parent = parent
        self.db_path = db_path
        self.modules_dir = MODULES_DIR
        self.modules = []
        self._load_modules()
        self._build_ui()

    def _load_modules(self):
        """Сканирует папку modules и загружает метаданные из module_data.json"""
        self.modules.clear()
        if not os.path.exists(self.modules_dir):
            return

        for folder in os.listdir(self.modules_dir):
            json_path = os.path.join(self.modules_dir, folder, "module_data.json")
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data['folder'] = folder
                        self.modules.append(data)
                except Exception:
                    pass
        # Сортировка по названию
        self.modules.sort(key=lambda x: x.get('name', ''))

    def _build_ui(self):
        self.window = tk.Toplevel(self.parent)
        self.window.title("Модули")
        self.window.geometry("850x620")
        self.window.transient(self.parent)
        self.window.grab_set()

        # Поиск
        ttk.Label(self.window, text="Поиск модулей:").pack(anchor=tk.W, padx=10, pady=(5, 2))
        self.search_var = tk.StringVar()
        ttk.Entry(self.window, textvariable=self.search_var).pack(fill=tk.X, padx=10, pady=2)
        self.search_var.trace_add('write', lambda *a: self._render())

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

        # Кнопки внизу
        bf = ttk.Frame(self.window)
        bf.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(bf, text="Импортировать", command=self._import_module).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

        self._render()

    def _render(self):
        """Отрисовка строк модулей"""
        for w in self.sf.winfo_children():
            w.destroy()

        query = self.search_var.get().lower()
        for mod in self.modules:
            name = mod.get('name', 'Без названия')
            if query in mod.get('name', '').lower() or query in mod.get('description', '').lower():
                row = ttk.Frame(self.sf)
                row.pack(fill=tk.X, pady=3, padx=5)

                display_name = name
                tooltip_text = None

                if len(name) > 47:
                    display_name = name[:47] + "..."
                    tooltip_text = name

                name_label = ttk.Label(row, text=display_name, width=50, anchor=tk.W)
                name_label.pack(side=tk.LEFT, padx=5)

                if tooltip_text:
                    self._bind_tooltip(name_label, tooltip_text)

                btn_f = ttk.Frame(row)
                btn_f.pack(side=tk.RIGHT)

                ttk.Button(btn_f, text="Запустить", width=10,
                           command=lambda m=mod: self._run_module(m)).pack(side=tk.LEFT, padx=2)
                ttk.Button(btn_f, text="Сведения", width=10,
                           command=lambda m=mod: ModuleDetailsWindow(self.window, m)).pack(side=tk.LEFT, padx=2)
                ttk.Button(btn_f, text="Экспорт", width=10, command=lambda m=mod: self._export_module(m)).pack(
                    side=tk.LEFT, padx=2)
                ttk.Button(btn_f, text="Удалить", width=10, command=lambda m=mod: self._delete_module(m)).pack(
                    side=tk.LEFT, padx=2)

        self.window.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _bind_tooltip(self, widget, text):
        """Создает всплывающую подсказку для виджета"""
        tooltip = None

        def show_tooltip(event):
            nonlocal tooltip
            if not tooltip:
                # Позиционируем тултип рядом с курсором
                x, y = widget.winfo_rootx() + 20, widget.winfo_rooty() + 20
                tooltip = tk.Toplevel(widget)
                tooltip.wm_overrideredirect(True)
                tooltip.wm_geometry(f"+{x}+{y}")
                label = tk.Label(tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                                 font=("tahoma", 8, "normal"), justify=tk.LEFT)
                label.pack(ipadx=4, ipady=2)

        def hide_tooltip(event):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

    def _run_module(self, mod):
        try:
            module_folder = mod.get('folder')
            if not module_folder:
                messagebox.showerror("Ошибка", "Не указана папка модуля.")
                return

            main_file = mod.get('entry_point') or mod.get('main_file') or 'run.py'
            main_path = os.path.join(self.modules_dir, module_folder, main_file)

            if not os.path.exists(main_path):
                messagebox.showerror("Ошибка", f"Файл запуска не найден: {main_file}")
                return

            # Добавляем папку модуля в sys.path, чтобы работали внутренние импорты (например, from deputies_import import ...)
            module_dir = os.path.dirname(main_path)
            if module_dir not in sys.path:
                sys.path.insert(0, module_dir)

            # Динамически загружаем файл модуля
            spec = importlib.util.spec_from_file_location("module_entry", main_path)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)

            # Вызываем стандартную точку входа
            if hasattr(runner, 'run'):
                runner.run(self.db_path, self.parent)
            else:
                messagebox.showerror("Ошибка", "В модуле отсутствует функция run(db_path, parent_window)")

        except Exception as e:
            messagebox.showerror("Ошибка запуска", f"Не удалось запустить модуль:\n{str(e)}")

    def _import_module(self):
        """Импорт модуля из ZIP-архива"""
        zip_path = filedialog.askopenfilename(
            title="Импортировать модуль",
            filetypes=[("Zip Archive", "*.zip"), ("All Files", "*.*")]
        )
        if not zip_path:
            return

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(temp_dir)

                # Ищем module_data.json в распакованном архиве
                json_path = None
                for root, _, files in os.walk(temp_dir):
                    if "module_data.json" in files:
                        json_path = os.path.join(root, "module_data.json")
                        break

                if not json_path:
                    messagebox.showerror("Ошибка", "В архиве не найден файл module_data.json.")
                    return

                # Читаем метаданные
                with open(json_path, 'r', encoding='utf-8') as f:
                    mod_data = json.load(f)

                # Определяем ID/имя папки
                module_id = mod_data.get('id') or mod_data.get('name', 'unknown_module').lower().replace(' ', '_')
                target_dir = os.path.join(self.modules_dir, module_id)

                # Проверка на существование
                if os.path.exists(target_dir):
                    if not messagebox.askyesno("Существует", f"Модуль '{module_id}' уже существует. Перезаписать?"):
                        return
                    shutil.rmtree(target_dir)

                os.makedirs(target_dir)

                # Копируем все файлы из папки, содержащей module_data.json
                src_dir = os.path.dirname(json_path)
                for item in os.listdir(src_dir):
                    s = os.path.join(src_dir, item)
                    d = os.path.join(target_dir, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)

                # Обновляем список
                self._load_modules()
                self._render()
                messagebox.showinfo("Успех", f"Модуль '{mod_data.get('name', module_id)}' успешно импортирован.")

        except Exception as e:
            messagebox.showerror("Ошибка импорта", str(e))

    def _export_module(self, mod):
        """Экспорт модуля в ZIP-архив"""
        folder_name = mod.get('folder', mod.get('id', 'module'))
        src_dir = os.path.join(self.modules_dir, folder_name)
        if not os.path.exists(src_dir):
            messagebox.showerror("Ошибка", "Папка модуля не найдена.")
            return

        path = filedialog.asksaveasfilename(
            title="Экспорт модуля",
            initialfile=folder_name,
            defaultextension=".zip",
            filetypes=[("Zip Archive", "*.zip")]
        )
        if path:
            try:
                base_name = os.path.splitext(path)[0]
                shutil.make_archive(base_name, 'zip', src_dir)
                messagebox.showinfo("Успех", f"Модуль '{mod.get('name')}' экспортирован в:\n{path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось экспортировать модуль:\n{e}")

    def _delete_module(self, mod):
        """Удаление модуля с двойным подтверждением"""
        mod_name = mod.get('name', 'Модуль')
        if not messagebox.askyesno("Удаление", f"Вы уверены, что хотите удалить модуль '{mod_name}'?"):
            return

        dlg = tk.Toplevel(self.window)
        dlg.title("Подтверждение удаления")
        dlg.geometry("420x160")
        dlg.transient(self.window)
        dlg.grab_set()
        ttk.Label(dlg, text=f"Для удаления модуля '{mod_name}' введите \"УДАЛИТЬ\":").pack(pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()

        def execute():
            if entry.get().strip() == "УДАЛИТЬ":
                folder_name = mod.get('folder', mod.get('id', 'module'))
                target_dir = os.path.join(self.modules_dir, folder_name)
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)

                # Обновляем внутренний список и интерфейс
                self.modules = [m for m in self.modules if m.get('folder') != folder_name]
                self._render()
                dlg.destroy()
                messagebox.showinfo("Успех", f"Модуль '{mod_name}' успешно удалён.")
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")

        ttk.Button(dlg, text="Удалить", command=execute).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=2)


class ModuleDetailsWindow:
    """Окно сведений о модуле (стиль аналогичен DatabaseDetailsWindow)."""

    def __init__(self, parent, mod_data):
        self.parent = parent
        self.mod_data = mod_data

        self.window = tk.Toplevel(parent)
        self.window.title(f"Сведения: {mod_data.get('name', 'Модуль')}")
        self.window.geometry("620x580")
        self.window.transient(parent)
        self.window.grab_set()
        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.window, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # --- НАЗВАНИЕ ---
        ttk.Label(main, text=self.mod_data.get('name', ''), font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
        ttk.Separator(main, orient='horizontal').pack(fill=tk.X, pady=10)

        # --- ИНФОРМАЦИЯ (Автор, Версия, ID) ---
        info_frame = ttk.LabelFrame(main, text="Информация о модуле", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 15))
        ttk.Label(info_frame, text=f"Автор: {self.mod_data.get('author', 'Не указан')}").pack(anchor=tk.W, pady=2)
        ttk.Label(info_frame, text=f"Версия: {self.mod_data.get('version', '0.0.0')}").pack(anchor=tk.W, pady=2)
        ttk.Label(info_frame, text=f"ID: {self.mod_data.get('id', 'Не задан')}").pack(anchor=tk.W, pady=2)

        # --- ОПИСАНИЕ ---
        ttk.Label(main, text="Описание:", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        desc_frame = ttk.Frame(main)
        desc_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        desc_text = tk.Text(desc_frame, height=8, wrap=tk.WORD, font=("Segoe UI", 9))
        sb_desc = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=desc_text.yview)
        desc_text.configure(yscrollcommand=sb_desc.set)
        desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_desc.pack(side=tk.RIGHT, fill=tk.Y)
        desc_text.insert(tk.END, self.mod_data.get('description', 'Описание отсутствует.'))
        desc_text.config(state=tk.DISABLED)

        # --- КНОПКИ ---
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(btn_frame, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT)