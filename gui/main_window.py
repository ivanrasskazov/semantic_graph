import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sys
import re
from datetime import datetime
import shutil
import zipfile
import tempfile

from config import *
from gui.editors.factions_editor import FactionsEditorWindow
from gui.editors.deputies_editor import DeputiesEditorWindow
from gui.editors.ngrams_editor import NgramsEditorWindow
from gui.editors.sources_editor import SourcesListWindow
from gui.editors.stopwords_editor import StopwordsEditorWindow
from gui.editors.abbreviations_editor import AbbreviationsEditorWindow
from gui.dialogs.modules_dialog import ModulesListWindow

# --- Конфигурация путей и констант ---
from config import (
    TEXTDATA_DIR, MAIN_FILE_NAME,
    DOWNLOADS_DIR_NAME,
)

from gui.dialogs.export_dialog import ExportWindow
from gui.dialogs.import_dialog import ImportWindow
from gui.utils.validators import is_valid_db_name
from gui.dialogs.create_db_dialog import CreateDBWindow
from gui.dialogs.database_list_dialog import DatabaseListWindow
from widgets.graph_window import GraphWindow
from gui.dialogs.default_params_dialog import DefaultParamsWindow

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.root.title("Программа визуализации данных")

        win_width, win_height = 720, 425
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - win_width) // 2
        y = (screen_height - win_height) // 2
        self.root.geometry(f"{win_width}x{win_height}+{x}+{y}")

        self.root.option_add('*tearOff', False)
        self.current_db_path = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_app)
        self.setup_initial_ui()

    def _on_close_app(self):
        if self.current_db_path: self.cleanup_downloads()
        for win in self.root.winfo_children():
            if isinstance(win, tk.Toplevel) and win.winfo_exists(): win.destroy()
        self.root.quit()
        sys.exit(0)  # ✅ Полное завершение процессов

    def cleanup_downloads(self):
        downloads_path = os.path.join(self.current_db_path, DOWNLOADS_DIR_NAME)
        if self.current_db_path and os.path.exists(downloads_path):
            try:
                import shutil
                shutil.rmtree(downloads_path)
                print(f"Папка {downloads_path} удалена.")
            except Exception as e:
                print(f"Не удалось удалить папку {downloads_path}: {e}")

    def close_current_db(self):
        if self.current_db_path:
            self.cleanup_downloads()
            self.current_db_path = None
        self.setup_initial_ui()

    def setup_initial_ui(self):
        self.clear_frame()
        self.root.deiconify()
        ttk.Label(self.root, text="Программа визуализации данных", font=("Arial", 16)).pack(pady=20)
        ttk.Label(self.root, text="ПРОТОТИП. ВОЗМОЖНЫ ОШИБКИ", foreground="red", font=("Arial", 10)).pack(pady=(0, 15))

        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=20)
        ttk.Button(button_frame, text="СОЗДАТЬ БАЗУ ДАННЫХ", command=self.create_db, width=30).pack(pady=5)

        # 🔹 РАЗДЕЛЁННЫЕ КНОПКИ
        ttk.Button(button_frame, text="ОТКРЫТЬ БАЗУ ДАННЫХ", command=lambda: DatabaseListWindow(self.root, self.load_db_by_name), width=30).pack(pady=5)
        ttk.Button(button_frame, text="ЗАГРУЗИТЬ БАЗУ ДАННЫХ", command=self.import_db, width=30).pack(pady=5)

        ttk.Button(button_frame, text="ПАРАМЕТРЫ ПО УМОЛЧАНИЮ", command=self.open_default_params, width=30).pack(pady=5)
        ttk.Button(button_frame, text="МОДУЛИ", command=self.open_modules, width=30).pack(pady=5)
        ttk.Button(button_frame, text="ЗАВЕРШИТЬ РАБОТУ", command=self.root.quit, width=30).pack(pady=5)

        ttk.Label(self.root,
                  text="В программе используется морфологический анализатор MyStem и библиотека navec, разработанные компанией «Яндекс»",
                  foreground="gray").pack(
            side=tk.BOTTOM, anchor=tk.W, padx=10, pady=10
        )

        bottom_frame = ttk.Frame(self.root)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=0)
        ttk.Label(bottom_frame, text="© Рассказов И. А., СПбГЭТУ «ЛЭТИ»", foreground="gray").pack(
            side=tk.LEFT)
        ttk.Label(bottom_frame, text="Версия 0.1. ПРОТОТИП", foreground="gray").pack(side=tk.RIGHT)

    def open_modules(self):
        ModulesListWindow(self.root, self.current_db_path)

    def clear_frame(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def create_db(self):
        CreateDBWindow(self.root, self.load_db_by_name)

    def import_db(self):
        """Импортирует базу данных из zip-архива."""
        downloads_dir = os.path.expanduser("~/Downloads")
        if not os.path.exists(downloads_dir): downloads_dir = os.getcwd()

        archive_path = filedialog.askopenfilename(
            initialdir=downloads_dir,
            title="Выберите архив базы данных",
            filetypes=[("Zip архивы", "*.zip"), ("Все файлы", "*.*")]
        )
        if not archive_path: return

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(archive_path, 'r') as z:
                    z.extractall(temp_dir)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось распаковать архив: {e}")
                return

            try:
                # Поиск папки с базой данных внутри архива
                db_root = None
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, MAIN_FILE_NAME)):
                        db_root = item_path
                        break
                    if os.path.isfile(item_path) and item == MAIN_FILE_NAME:
                        db_root = temp_dir
                        break

                if not db_root:
                    messagebox.showerror("Ошибка", "В архиве не найдена база данных (отсутствует файл main).")
                    return

                # 🔹 ИСПРАВЛЕНИЕ: Убрана sanitize_filename, которая удаляла пробелы.
                # Теперь сохраняются все пробелы, отсекаются только недопустимые символы ФС.
                raw_name = os.path.basename(db_root) if db_root != temp_dir else \
                os.path.splitext(os.path.basename(archive_path))[0]
                db_name = re.sub(r'[<>:"/\|?*]', '', raw_name).strip()
                if not db_name: db_name = "База данных"

                target_path = os.path.join(TEXTDATA_DIR, db_name)

                if os.path.exists(target_path):
                    if not messagebox.askyesno("Существует", f"База '{db_name}' уже есть. Перезаписать?"):
                        return
                    shutil.rmtree(target_path)

                shutil.copytree(db_root, target_path)
                messagebox.showinfo("Успех", "База данных успешно импортирована из архива.")
                self.current_db_path = target_path
                self.setup_main_menu(db_name)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Ошибка импорта: {e}")

    def open_default_params(self):
        """Открывает глобальное окно настроек по умолчанию."""
        # Убедитесь, что класс DefaultParamsWindow добавлен в файл выше
        DefaultParamsWindow(self.root)

    def load_db_by_name(self, db_name):
        full = os.path.abspath(os.path.join(TEXTDATA_DIR, db_name))
        if os.path.exists(full):
            self.current_db_path = full
            self.setup_main_menu(db_name)
        else:
            messagebox.showerror("Ошибка", f"База данных не найдена по пути:\n{full}")

    def setup_main_menu(self, db_name):
        self.clear_frame()

        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(header, text=f"Текущая база данных: {db_name}", font=("Arial", 12, "bold")).pack(anchor=tk.W)

        warning = ttk.Label(self.root,
                            text="Все изменения сохраняются немедленно. При необходимости сделайте резервную копию.",
                            foreground="red", wraplength=580)
        warning.pack(pady=5, padx=10, anchor=tk.NW)

        # Используем Grid вместо Pack для точного управления строками и объединением ячеек
        btn_frame_main = ttk.Frame(self.root)
        btn_frame_main.pack(pady=20)

        btn_width = 30
        pad = 5

        # ==========================================
        # ЛЕВАЯ КОЛОНКА (column 0)
        # ==========================================
        ttk.Button(btn_frame_main, text="ЗАКРЫТЬ БАЗУ ДАННЫХ", width=btn_width,
                   command=self.close_current_db).grid(row=0, column=0, pady=pad, padx=5)

        # 🔹 Декоративное пустое место (сдвиг вниз на 1 кнопку)
        ttk.Label(btn_frame_main, text=" ", width=btn_width).grid(row=1, column=0, pady=pad, padx=5)

        ttk.Button(btn_frame_main, text="ИМПОРТИРОВАТЬ ДАННЫЕ", width=btn_width,
                   command=lambda: ImportWindow(self.root, self.current_db_path)).grid(row=2, column=0, pady=pad,
                                                                                       padx=5)
        ttk.Button(btn_frame_main, text="ЭКСПОРТИРОВАТЬ ДАННЫЕ", width=btn_width,
                   command=lambda: ExportWindow(self.root, self.current_db_path)).grid(row=3, column=0, pady=pad,
                                                                                       padx=5)

        # 🔹 Декоративное пустое место (перед последней кнопкой)
        ttk.Label(btn_frame_main, text=" ", width=btn_width).grid(row=4, column=0, pady=pad, padx=5)

        # 🔹 Кнопка растягивается на 2 строки (высота последних двух кнопок справа)
        ttk.Button(btn_frame_main, text="РАБОТА С ДАННЫМИ", width=btn_width,
                   command=lambda: GraphWindow(self.root, self.current_db_path)).grid(row=5, column=0,
                                                                                      pady=pad, padx=5, sticky="ns")

        # ==========================================
        # РАЗДЕЛИТЕЛЬ (column 1)
        # Растягиваем на все 7 строк (0-6), чтобы линия шла через все кнопки
        # ==========================================
        ttk.Separator(btn_frame_main, orient='vertical').grid(row=0, column=1, rowspan=7, padx=10, sticky="ns")

        # ==========================================
        # ПРАВАЯ КОЛОНКА (column 2)
        # ==========================================
        ttk.Button(btn_frame_main, text="СПИСОК ИСТОЧНИКОВ", width=btn_width,
                   command=lambda: SourcesListWindow(self.root, self.current_db_path)).grid(row=0, column=2, pady=pad,
                                                                                            padx=5)
        ttk.Button(btn_frame_main, text="СПИСОК ФРАКЦИЙ", width=btn_width,
                   command=lambda: FactionsEditorWindow(self.root, self.current_db_path)).grid(row=1, column=2,
                                                                                               pady=pad, padx=5)
        ttk.Button(btn_frame_main, text="СПИСОК СУБЪЕКТОВ", width=btn_width,
                   command=lambda: DeputiesEditorWindow(self.root, self.current_db_path)).grid(row=2, column=2,
                                                                                               pady=pad, padx=5)
        ttk.Button(btn_frame_main, text="СПИСОК СТОП-СЛОВ", width=btn_width,
                   command=lambda: StopwordsEditorWindow(self.root, self.current_db_path)).grid(row=3, column=2,
                                                                                                pady=pad, padx=5)
        ttk.Button(btn_frame_main, text="СПИСОК N-ГРАММ", width=btn_width,
                   command=lambda: NgramsEditorWindow(self.root, self.current_db_path)).grid(row=4, column=2, pady=pad,
                                                                                             padx=5)
        ttk.Button(btn_frame_main, text="СПИСОК ОБОЗНАЧЕНИЙ", width=btn_width,
                   command=lambda: AbbreviationsEditorWindow(self.root, self.current_db_path)).grid(row=5, column=2,
                                                                                                       pady=pad, padx=5)

        # Выравниваем колонки по ширине
        btn_frame_main.columnconfigure(0, weight=1, minsize=btn_width * 7)
        btn_frame_main.columnconfigure(2, weight=1, minsize=btn_width * 7)

        ttk.Separator(btn_frame_main, orient='horizontal').grid(row=7, column=0, columnspan=3, sticky="ew", pady=10,
                                                                padx=20)

        # 🔹 Фрейм растягивается на всю ширину колонки (sticky="ew")
        db_mgr_frame = ttk.Frame(btn_frame_main)
        db_mgr_frame.grid(row=8, column=0, columnspan=3, sticky="ew", padx=40, pady=5)

        # 🔹 Кнопки располагаются вертикально и заполняют всю доступную ширину (fill=tk.X)
        ttk.Button(db_mgr_frame, text="ЭКСПОРТИРОВАТЬ БАЗУ ДАННЫХ",
                   command=lambda: self.export_db(db_name)).pack(fill=tk.X, pady=2)

        ttk.Button(db_mgr_frame, text="ДУБЛИРОВАТЬ БАЗУ ДАННЫХ",
                   command=lambda: self.duplicate_db(db_name)).pack(fill=tk.X, pady=2)

        ttk.Button(db_mgr_frame, text="УДАЛИТЬ БАЗУ ДАННЫХ",
                   command=lambda: self.delete_db(db_name)).pack(fill=tk.X, pady=2)

    def export_db(self, db_name):
        src_dir = os.path.join(TEXTDATA_DIR, db_name)
        path = filedialog.asksaveasfilename(title="Сохранить архив", initialfile=db_name, defaultextension=".zip",
                                            filetypes=[("Zip Archive", "*.zip")])
        if path:
            # shutil.make_archive требует путь без расширения
            base_name = os.path.splitext(path)[0]
            try:
                shutil.make_archive(base_name, 'zip', src_dir)
                messagebox.showinfo("Успех", f"База '{db_name}' экспортирована в {path}")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

    def duplicate_db(self, db_name):
        src_dir = os.path.join(TEXTDATA_DIR, db_name)
        dlg = tk.Toplevel(self.root)
        dlg.title("Дублирование базы данных")
        dlg.geometry("450x180")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, text="Введите название новой базы (макс. 50 символов):").pack(pady=(10, 5))
        name_var = tk.StringVar(value=f"{db_name} — Дубликат")
        name_entry = ttk.Entry(dlg, textvariable=name_var, width=45)
        name_entry.pack(pady=5)
        name_entry.select_range(0, tk.END)
        name_entry.focus()

        switch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dlg, text="Перейти в новую базу данных после дублирования", variable=switch_var).pack(pady=5)

        def do_dup():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("Внимание", "Введите название.");
                return
            if not is_valid_db_name(new_name)[0]:
                messagebox.showerror("Ошибка", is_valid_db_name(new_name)[1]);
                return
            dst_dir = os.path.join(TEXTDATA_DIR, new_name)
            if os.path.exists(dst_dir):
                messagebox.showerror("Ошибка", "База с таким именем уже существует.");
                return

            try:
                shutil.copytree(src_dir, dst_dir)
                os.utime(dst_dir, None)  # Обновляем дату создания дубликата

                main_file = os.path.join(dst_dir, MAIN_FILE_NAME)
                if os.path.exists(main_file):
                    with open(main_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    new_ts = f"created_at={datetime.now().isoformat()}\n"
                    with open(main_file, 'w', encoding='utf-8') as f:
                        for line in lines:
                            if line.startswith("created_at="):
                                f.write(new_ts)
                            else:
                                f.write(line)

                dlg.destroy()
                messagebox.showinfo("Успех", f"Дубликат '{new_name}' успешно создан.")
                if switch_var.get():
                    self.close_current_db()
                    self.load_db_by_name(new_name)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать дубликат:\n{e}")

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Создать дубликат", command=do_dup).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Отмена", command=dlg.destroy).pack(side=tk.LEFT, padx=10)

    def delete_db(self, db_name):
        if not messagebox.askyesno("Внимание",
                                   f"Вы уверены, что хотите удалить базу данных '{db_name}'? Это действие нельзя отменить."): return
        dlg = tk.Toplevel(self.root);
        dlg.title("Подтверждение удаления");
        dlg.geometry("400x150");
        dlg.transient(self.root);
        dlg.grab_set()
        ttk.Label(dlg, text=f"Для удаления введите \"УДАЛИТЬ\":").pack(pady=10)
        entry = ttk.Entry(dlg, width=30);
        entry.pack(pady=5);
        entry.focus()

        def do_del():
            if entry.get().strip() == "УДАЛИТЬ":
                dlg.destroy()
                src_dir = os.path.join(TEXTDATA_DIR, db_name)
                try:
                    shutil.rmtree(src_dir)
                    messagebox.showinfo("Успех", f"База данных \"{db_name}\" удалена.")
                    self.close_current_db()
                except Exception as e:
                    messagebox.showerror("Ошибка", str(e))
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")
                entry.delete(0, tk.END)

        ttk.Button(dlg, text="Удалить", command=do_del).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=5)