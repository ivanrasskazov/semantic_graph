import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import re

from config import DEFAULTS_DIR, GRAMS_FILE_NAME

class AbbreviationsEditorWindow:
    def __init__(self, parent, db_path, is_defaults=False):
        self.parent = parent
        self.db_path = db_path
        self.changes_made = False
        self.is_defaults = is_defaults
        self.window = tk.Toplevel(parent)
        self.window.title("Список обозначений")
        self.window.geometry("950x600")
        self.window.transient(parent)
        self.window.grab_set()
        self.data_file = os.path.join(db_path, "abbreviations.json")
        self.data = {}

        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                pass
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

        list_frame = ttk.Frame(self.window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.listbox = tk.Listbox(list_frame)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox.bind('<Delete>', lambda e: self.delete_selected())

        self.abbrevs_search_var = tk.StringVar()
        ttk.Label(self.window, text="Поиск обозначений:").pack(anchor=tk.W, padx=10, pady=(5, 0))
        self.abbrevs_search_entry = ttk.Entry(self.window, textvariable=self.abbrevs_search_var)
        self.abbrevs_search_entry.pack(fill=tk.X, padx=10, pady=(0, 5))
        self.abbrevs_search_var.trace_add('write', lambda *args: self._search_abbrevs())

        self._refresh_listbox()

        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Добавить", command=self._open_add_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self._edit_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_selected).pack(side=tk.LEFT, padx=5)

        self.import_btn = ttk.Button(btn_frame, text="Импортировать", command=self.import_from_file)
        self.import_btn.pack(side=tk.LEFT, padx=5)
        self._setup_tip(self.import_btn, "JSON формат: {\"Расшифровка\": [\"Обозначение1\"]}")

        if not self.is_defaults:
            ttk.Button(btn_frame, text="Добавить значения по умолчанию", command=self._merge_defaults).pack(
                side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="Удалить всё", command=self.delete_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.on_close).pack(side=tk.RIGHT, padx=5)

    def delete_all(self):
        ui = getattr(self, 'tree', getattr(self, 'listbox', None))
        has_items = False
        if hasattr(ui, 'size'): has_items = ui.size() > 0
        elif hasattr(ui, 'get_children'): has_items = bool(ui.get_children())
        if not has_items: return

        dlg = tk.Toplevel(self.window)
        dlg.title("Удаление всех обозначений")
        dlg.geometry("400x150")
        dlg.transient(self.window)
        dlg.grab_set()
        ttk.Label(dlg, text="Для удаления всех обозначений введите \"УДАЛИТЬ\":").pack(pady=10)
        entry = ttk.Entry(dlg, width=30)
        entry.pack(pady=5)
        entry.focus()
        def execute():
            if entry.get().strip() == "УДАЛИТЬ":
                if hasattr(self, 'tree'):
                    for item in self.tree.get_children(): self.tree.delete(item)
                    self.data.clear()
                elif hasattr(self, 'listbox'):
                    self.listbox.delete(0, tk.END)
                self.changes_made = True
                dlg.destroy()
                messagebox.showinfo("Успех", "Все обозначения удалены.")
            else:
                messagebox.showwarning("Ошибка", "Вы не ввели \"УДАЛИТЬ\".")
        ttk.Button(dlg, text="Удалить", command=execute).pack(pady=10)
        ttk.Button(dlg, text="Отмена", command=dlg.destroy).pack(pady=2)

    def _search_abbrevs(self):
        query = self.abbrevs_search_var.get().lower()
        self.listbox.delete(0, tk.END)
        for full in sorted(self.data.keys()):
            abrs = self.data[full]
            if query in full.lower() or any(query in a.lower() for a in abrs):
                self.listbox.insert(tk.END, f"{full} | {', '.join(abrs)}")

    def _abbr_exists_globally(self, new_abbr, exclude_full=None):
        """Проверяет, встречается ли обозначение уже в любой расшифровке (кроме текущей)."""
        clean = re.sub(r'[^\w\s]', '', new_abbr.lower()).strip()
        if not clean: return False
        for full_key, abrs in self.data.items():
            if exclude_full and full_key == exclude_full: continue
            for a in abrs:
                if re.sub(r'[^\w\s]', '', a.lower()).strip() == clean:
                    return True
        return False

    def _sync_to_ngrams(self, text):
        """Если текст похож на N-грамму (пробелы/слова), добавляет в grams.txt."""
        clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
        if ' ' not in clean or len(clean.split()) < 2: return
        grams_file = os.path.join(self.db_path, GRAMS_FILE_NAME)
        existing = set()
        if os.path.exists(grams_file):
            try:
                with open(grams_file, 'r', encoding='utf-8') as f:
                    existing = {l.strip().lower() for l in f if l.strip()}
            except:
                pass
        if clean not in existing:
            with open(grams_file, 'a', encoding='utf-8') as f:
                f.write(f"{text.strip()}\n")

    def _refresh_listbox(self):
        self.listbox.delete(0, tk.END)
        for full in sorted(self.data.keys()):
            self.listbox.insert(tk.END, f"{full} | {', '.join(self.data[full])}")

    def _setup_tip(self, widget, text):
        tw = None

        def show(e):
            nonlocal tw
            if tw and tw.winfo_exists(): tw.destroy()
            tw = tk.Toplevel(self.window)
            tw.wm_overrideredirect(True)
            ttk.Label(tw, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                      font=("tahoma", "8", "normal")).pack(ipadx=4, ipady=2)
            tw.wm_geometry(f"+{widget.winfo_rootx() + 5}+{widget.winfo_rooty() + 5}")

        def hide(e):
            nonlocal tw
            if tw and tw.winfo_exists(): tw.destroy()
            tw = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    def _open_add_dialog(self):
        dlg = tk.Toplevel(self.window)
        dlg.title("Добавить обозначение")
        dlg.geometry("380x260")
        dlg.transient(self.window)
        dlg.grab_set()

        ttk.Label(dlg, text="Расшифровка: ").pack(anchor=tk.W, padx=10, pady=(10, 2))
        full_entry = ttk.Entry(dlg, width=40)
        full_entry.pack(padx=10, pady=(0, 10))

        ttk.Label(dlg, text="Обозначения (через запятую): ").pack(anchor=tk.W, padx=10, pady=(0, 2))
        abbr_text = tk.Text(dlg, height=5, width=40)
        abbr_text.pack(padx=10, pady=(0, 10))

        def confirm():
            full, abrs_raw = full_entry.get().strip(), abbr_text.get("1.0", tk.END).strip()
            if not full or not abrs_raw:
                messagebox.showwarning("Ошибка", "Заполните оба поля.");
                return
            new_abrs = [a.strip() for a in re.split(r'[,;\n]', abrs_raw) if a.strip()]
            if not new_abrs:
                messagebox.showwarning("Ошибка", "Введите обозначения.");
                return

            # 🔹 Проверка на дубликаты обозначений
            for a in new_abrs:
                if self._abbr_exists_globally(a):
                    messagebox.showerror("Дубликат", f"Обозначение '{a}' уже используется для другой расшифровки.");
                    return

            if full in self.data:
                existing = set(self.data[full])
                self.data[full] = list(existing | set(new_abrs))
            else:
                self.data[full] = new_abrs

            for a in new_abrs: self._sync_to_ngrams(a)
            self._sync_to_ngrams(full)

            self._refresh_listbox()
            self.changes_made = True
            dlg.destroy()

        ttk.Button(dlg, text="Добавить", command=confirm).pack(pady=10)
        full_entry.focus()

    def _edit_selected(self):
        sel = self.listbox.curselection()
        if not sel: return
        display = self.listbox.get(sel[0])
        full, abrs = display.split(' | ')[0], display.split(' | ')[1].split(', ')

        dlg = tk.Toplevel(self.window)
        dlg.title("Редактировать обозначение")
        dlg.geometry("380x260")
        dlg.transient(self.window)
        dlg.grab_set()

        ttk.Label(dlg, text="Расшифровка: ").pack(pady=5)
        f_ent = ttk.Entry(dlg, width=40)
        f_ent.pack(pady=5)
        f_ent.insert(0, full)

        ttk.Label(dlg, text="Обозначения (через запятую): ").pack(pady=5)
        a_txt = tk.Text(dlg, height=5, width=40)
        a_txt.pack(pady=5)
        a_txt.insert("1.0", ", ".join(abrs))

        def apply():
            nf, na = f_ent.get().strip(), [x.strip() for x in a_txt.get("1.0", tk.END).split(',') if x.strip()]
            if not nf or not na:
                messagebox.showwarning("Внимание", "Заполните поля.");
                return

            # 🔹 Проверка дубликатов обозначений (исключая текущее редактируемое)
            for a in na:
                if self._abbr_exists_globally(a, exclude_full=full):
                    messagebox.showerror("Дубликат", f"Обозначение '{a}' уже занято другой расшифровкой.");
                    return

            self.data.pop(full, None)
            self.data[nf] = na

            for a in na: self._sync_to_ngrams(a)
            self._sync_to_ngrams(nf)

            self._refresh_listbox()
            self.changes_made = True
            dlg.destroy()

        ttk.Button(dlg, text="Сохранить", command=apply).pack(pady=5)

    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel: return
        full = self.listbox.get(sel[0]).split(' | ')[0]
        self.data.pop(full, None)
        self._refresh_listbox()
        self.changes_made = True

    def _merge_defaults(self):
        if not messagebox.askyesno("Подтверждение", "Добавить обозначения по умолчанию?"): return
        def_path = os.path.join(DEFAULTS_DIR, "abbreviations.json")
        if not os.path.exists(def_path): return
        with open(def_path, 'r', encoding='utf-8') as f:
            defaults = json.load(f)
        merged, added = 0, 0
        for full, abrs in defaults.items():
            if full in self.data:
                old_set = set(self.data[full])
                self.data[full] = list(old_set | set(abrs))
                merged += 1
            else:
                self.data[full] = abrs
                added += 1
        self._refresh_listbox()
        self.changes_made = True
        if merged or added: messagebox.showinfo("Готово", f"Обновлено: {merged}, Добавлено: {added}")

    def import_from_file(self):
        file_path = filedialog.askopenfilename(title="Выберите JSON", filetypes=[("JSON files", "*.json")])
        if not file_path: return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported = json.load(f)
            for k, v in imported.items():
                if isinstance(v, list):
                    if k in self.data:
                        self.data[k] = list(set(self.data[k]) | set(v))
                    else:
                        self.data[k] = v
            self._refresh_listbox()
            self.changes_made = True
            messagebox.showinfo("Импорт", "Данные импортированы.")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def on_close(self):
        if self.changes_made and messagebox.askyesno("Сохранить изменения?",
                                                     "Вы хотите сохранить изменения в списке обозначений?"):
            try:
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.utime(self.db_path, None)
                messagebox.showinfo("Успех", "Список обозначений сохранён.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))
        self.window.destroy()