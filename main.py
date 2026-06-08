import tkinter as tk
from tkinter import ttk
import os
from config import TEXTDATA_DIR
from gui.main_window import MainApp
from core.nlp import init_nlp_models
init_nlp_models()

def show_splash_and_run():
    root = tk.Tk()
    root.withdraw()

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.geometry("400x200")

    # Центрирование по экрану
    splash.update_idletasks()
    width = splash.winfo_width()
    height = splash.winfo_height()
    x = (splash.winfo_screenwidth() // 2) - (width // 2)
    y = (splash.winfo_screenheight() // 2) - (height // 2)
    splash.geometry(f"+{x}+{y}")

    ttk.Label(splash, text="Загрузка...", font=("Segoe UI", 12, "bold")).pack(pady=30)
    progress = ttk.Progressbar(splash, length=300, mode='indeterminate')
    progress.pack()
    progress.start()
    splash.update()

    def start_app():
        splash.destroy()
        root.deiconify()
        MainApp(root)

    root.after(100, start_app)
    root.mainloop()

if __name__ == "__main__":
    os.makedirs(TEXTDATA_DIR, exist_ok=True)
    show_splash_and_run()