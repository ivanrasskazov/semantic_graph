import tkinter as tk
from tkinter import ttk, messagebox
import os
from datetime import datetime

from config import TEXTDATA_DIR, SOURCES_DIR_NAME, LEXEMES_DIR_NAME, GRAPH_DATA_DIR_NAME, MAIN_FILE_NAME
from core.database import apply_defaults_to_new_db
from gui.utils.validators import is_valid_db_name

class CreateDBWindow:
    def __init__(self, parent, on_create_callback):
        self.parent = parent
        self.on_create_callback = on_create_callback
        self.window = tk.Toplevel(parent)
        self.window.title("Создать базу данных")
        self.window.geometry("400x150")
        self.window.transient(parent)
        self.window.grab_set()

        ttk.Label(self.window, text="Введите название базы данных (макс. 50 символов):").pack(pady=10)
        self.entry = ttk.Entry(self.window, width=50)
        self.entry.pack(pady=5)
        vcmd = (self.window.register(self.validate_length), '%P')
        self.entry.config(validate='key', validatecommand=vcmd)

        button_frame = ttk.Frame(self.window)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="OK", command=self.create_db).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

    def validate_length(self, new_value):
        return len(new_value) <= 50

    def create_db(self):
        name = self.entry.get().strip()
        is_valid, msg = is_valid_db_name(name)
        if not is_valid:
            messagebox.showerror("Ошибка", msg);
            return

        full_path = os.path.join(TEXTDATA_DIR, name)
        if os.path.exists(full_path):
            if messagebox.askyesno("База существует", f"База '{name}' уже есть. Открыть?"):
                self.on_create_callback(name);
                self.window.destroy()
        else:
            os.makedirs(full_path, exist_ok=True)
            for subdir in [SOURCES_DIR_NAME, LEXEMES_DIR_NAME, GRAPH_DATA_DIR_NAME]:
                os.makedirs(os.path.join(full_path, subdir), exist_ok=True)

            # 🔹 ПРИМЕНЕНИЕ ПАРАМЕТРОВ ПО УМОЛЧАНИЮ
            apply_defaults_to_new_db(full_path)

            with open(os.path.join(full_path, MAIN_FILE_NAME), 'w', encoding='utf-8') as f:
                f.write(f"name={name}\ncreated_at={datetime.now().isoformat()}\n")
            self.on_create_callback(name)
            self.window.destroy()