import tkinter as tk
from tkinter import messagebox
from deputies_import import DeputiesImportModule

def run(db_path, parent_window):
    """
    Точка входа в модуль.
    """
    try:
        module = DeputiesImportModule(db_path, parent_window)
        module.show_main_menu()
    except Exception as e:
        messagebox.showerror("Ошибка модуля", f"Не удалось запустить модуль:\n{e}")