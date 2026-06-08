import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import re
import tempfile
import traceback
import webbrowser
from datetime import datetime
import urllib.parse
from urllib.parse import urlparse
import threading

from collections import Counter

import chardet
import requests
from bs4 import BeautifulSoup
from docx import Document

from config import (
    SOURCES_DIR_NAME, LEXEMES_DIR_NAME,
    DOWNLOADS_DIR_NAME, DEPUTIES_FILE_NAME,
    GRAMS_FILE_NAME, SOURCES_LIST_FILE_NAME
)

from core.parser import (
     _extract_title_from_html_fixed,
     _extract_initiators_from_html_fixed,
     _extract_registration_date_from_html_fixed,
     find_explanatory_note_link,
 )

from core.nlp import remove_header, get_active_stopwords, process_source_text_to_lemmas, preprocess_ngrams_mapping
from gui.utils.validators import is_valid_source_name, sanitize_filename

def _has_cyrillic(text: str) -> bool:
    return any('\u0400' <= c <= '\u04FF' for c in text)

def _looks_like_mojibake(text: str) -> bool:
    # Характерные паттерны CP1251, прочитанного как Latin-1/Windows-1252
    mojibake_signs = ['âî', 'Ã©', 'Ã±', 'Ã¢', 'Ã¤', 'Ã«', 'Ã¼', 'Ã¶', 'ÃŸ', 'Ð', 'Ò']
    if any(p in text for p in mojibake_signs):
        return True
    # Если много расширенных латинских символов, но нет кириллицы → скорее всего кракозябры
    if not _has_cyrillic(text) and len([c for c in text if 128 <= ord(c) <= 255]) > 15:
        return True
    return False

def auto_decode_text(file_path: str) -> str:
    """
    Автоматически декодирует файл, исправляет кракозябры и возвращает валидный UTF-8 текст.
    """
    with open(file_path, 'rb') as f:
        raw = f.read()
    if not raw:
        return ""

    # 1️⃣ Попытка через chardet
    det = chardet.detect(raw)
    enc = det.get('encoding', 'utf-8')
    try:
        text = raw.decode(enc)
        if _has_cyrillic(text) and not _looks_like_mojibake(text):
            return text
    except (UnicodeDecodeError, LookupError):
        pass

    # 2️⃣ Прямой перебор стандартных кириллических кодировок
    for e in ['cp1251', 'utf-8', 'utf-8-sig', 'koi8-r', 'mac_cyrillic', 'iso-8859-5']:
        try:
            text = raw.decode(e)
            if _has_cyrillic(text) and not _looks_like_mojibake(text):
                return text
        except (UnicodeDecodeError, LookupError):
            continue

    # 3️⃣ Исправление классических кракозябр (CP1251 → Latin-1 → CP1251)
    try:
        # Читаем как UTF-8 (даже с заменой битых байт)
        text_utf = raw.decode('utf-8', errors='replace')
        if _looks_like_mojibake(text_utf):
            # Latin-1 сохраняет байты 1:1, cp1251 правильно интерпретирует их как кириллицу
            fixed = text_utf.encode('latin-1', errors='ignore').decode('cp1251', errors='ignore')
            if _has_cyrillic(fixed):
                return fixed
    except Exception:
        pass

    # 4️⃣ Фоллбэк: читаем как CP1251 напрямую
    try:
        text = raw.decode('cp1251')
        if _has_cyrillic(text):
            return text
    except UnicodeDecodeError:
        pass

    # 5️⃣ Если всё сломалось → возвращаем как есть, заменяя битые символы
    return raw.decode('utf-8', errors='replace')

def smart_read_text(file_path):
    """Автоматически определяет кодировку и исправляет mojibake (кракозябры)."""
    encodings = ['utf-8', 'utf-8-sig', 'cp1251', 'koi8-r', 'mac_cyrillic', 'iso-8859-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc, errors='strict') as f:
                content = f.read()
            # Если нашли кириллицу — считаем, что угадали
            if any('\u0400' <= c <= '\u04FF' for c in content):
                return content
        except (UnicodeDecodeError, UnicodeError):
            continue

    # Если не вышло — читаем как latin-1 и пробуем восстановить двойную перекодировку
    with open(file_path, 'r', encoding='latin-1') as f:
        raw = f.read()

    # Исправление классических кракозябр (CP1251, прочитанный как UTF-8/Latin-1)
    try:
        return raw.encode('latin-1').decode('cp1251')
    except Exception:
        return raw

def safe_read_file(file_path):
    """Безопасное чтение файла с автоопределением/фоллбэком кодировки"""
    with open(file_path, 'rb') as f:
        raw = f.read()

    # Попытка прочитать как UTF-8
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        pass

    # Попытка прочитать как CP1251 (стандарт для Windows/RU)
    try:
        return raw.decode('cp1251')
    except UnicodeDecodeError:
        pass

    # Фоллбэк: читаем как latin-1 (гарантированно читает любые байты) и чистим кракозябры
    # Если файл всё-таки UTF-8, но повреждён, можно попробовать декодировать с errors='replace'
    try:
        return raw.decode('utf-8', errors='replace').encode('latin-1', errors='ignore').decode('cp1251',
                                                                                               errors='ignore')
    except Exception:
        return raw.decode('utf-8', errors='replace')  # На крайний случай

def _process_html_note(html_content) -> str:
    """
    Обрабатывает HTML-файл пояснительной записки:
    1) Находит ВТОРОЕ вхождение 'пояснительная' (регистронезависимо)
    2) Обрезает всё до этого места (второе вхождение сохраняет)
    3) Удаляет строки с 'Документ разместил'
    4) Извлекает список депутатов после слова 'Депутаты'
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    text = soup.get_text(separator='\n', strip=True)
    lines = text.split('\n')

    # 🔹 Поиск ВТОРОГО вхождения 'пояснительная'
    count = 0
    start_idx = 0
    for i, line in enumerate(lines):
        if 'пояснительная' in line.lower():
            count += 1
            if count == 2:
                start_idx = i
                break

    # Обрезаем с этого места
    cleaned = lines[start_idx:] if start_idx else lines

    # 🔹 Удаляем строки с 'Документ разместил'
    cleaned = [l for l in cleaned if 'документ разместил' not in l.lower()]

    # 🔹 Извлекаем депутатов (если есть блок "Депутаты ...")
    result = []
    deputies_block = False
    for line in cleaned:
        if line.strip().lower().startswith('депутаты'):
            deputies_block = True
            # Сохраняем саму строку с депутатами
            result.append(line.strip())
        elif deputies_block:
            # Если следующая строка пустая или не похожа на ФИО — выходим из блока
            if not line.strip() or (line.strip() and not re.match(r'^[А-ЯЁ][а-яё\.]+\s*[А-ЯЁ]?\.', line.strip())):
                deputies_block = False
                result.append(line.strip())
            else:
                result.append(line.strip())
        else:
            result.append(line.strip())

    # 🔹 Удаляем пустые строки в начале и конце, но оставляем внутренние
    while result and not result[0].strip():
        result.pop(0)
    while result and not result[-1].strip():
        result.pop()

    return '\n'.join(result).strip()


def _extract_text_from_rtf(rtf_path: str) -> str:
    """Извлекает текст из .rtf, корректно обрабатывая кириллицу CP1251."""
    import re
    with open(rtf_path, 'r', encoding='utf-8', errors='ignore') as f:
        rtf = f.read()

    # Декодируем hex-символы формата \'XX (часто CP1251 в RTF)
    def hex_replace(match):
        try:
            return bytes([int(match.group(1), 16)]).decode('cp1251', errors='ignore')
        except:
            return ''

    text = re.sub(r"\\'([0-9a-fA-F]{2})", hex_replace, rtf)

    # Удаляем RTF-теги и управляющие последовательности
    text = re.sub(r'\\[a-z]+[0-9-]*[ ]?', '', text)
    text = re.sub(r'[{}\\\*]', '', text)
    text = re.sub(r'\r\n?', '\n', text)

    # Чистим лишние пробелы и пустые строки
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)

class ImportWindow:
    def __init__(self, parent, db_path):
        self.parent = parent
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("Импорт данных")
        self.window.geometry("900x780")  # Увеличили высоту
        self.window.transient(parent)
        self.window.grab_set()

        self.parsing_in_progress = False
        self.selected_file_path = tk.StringVar()
        self.source_name_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.registration_date_var = tk.StringVar()
        self.deputy_selection_vars = {}
        self.sigs_status = "<...>"

        file_frame = ttk.Frame(self.window)
        file_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(file_frame, text="Загрузить файл", command=self.select_file).pack(side=tk.LEFT)
        self.file_label = ttk.Label(file_frame, textvariable=self.selected_file_path, relief=tk.SUNKEN)
        self.file_label.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        name_frame = ttk.Frame(self.window)
        name_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(name_frame, text="Название источника (макс. 50 символов):").pack(anchor=tk.W)
        self.name_entry = ttk.Entry(name_frame, textvariable=self.source_name_var)
        self.name_entry.pack(fill=tk.X, pady=(0, 5))

        url_frame = ttk.Frame(self.window)
        url_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(url_frame, text="URL законопроекта в СОЗД:").pack(anchor=tk.W)
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(fill=tk.X, pady=(0, 5))
        self.url_var.trace_add("write", self.on_url_change)

        index_btn_frame = ttk.Frame(self.window)
        index_btn_frame.pack(fill=tk.X, padx=10, pady=2)
        self.index_btn = ttk.Button(index_btn_frame, text="Проиндексировать", command=self.index_project)
        self.index_btn.pack()
        # Изначально отключена
        self.index_btn.config(state=tk.DISABLED)
        # Всплывающая подсказка
        self.tooltip_index = None
        self.index_btn.bind("<Enter>", lambda e: self.on_index_btn_hover(
            "Автоматически считывает название законопроекта, субъектов права законодательной инициативы и дату регистрации законопроекта и материалов к нему."))
        self.index_btn.bind("<Leave>", lambda e: self.hide_index_tooltip())

        # --- Инициализация переменных галочек ---
        self.remove_header_var = tk.BooleanVar(value=True)
        self.download_file_var = tk.BooleanVar(value=False)
        self.index_signatures_var = tk.BooleanVar(value=False)
        self.delete_signatures_var = tk.BooleanVar(value=False)
        self.auto_create_subjects_var = tk.BooleanVar(value=False)
        self.auto_create_signers_var = tk.BooleanVar(value=False)

        self.tooltip = None

        # Загрузка сохранённого состояния
        self._load_checkbox_states()

        # --- Фрейм с тремя колонками опций ---
        options_frame = ttk.Frame(self.window)
        options_frame.pack(fill=tk.X, padx=10, pady=5)

        col1 = ttk.Frame(options_frame)
        col1.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        col2 = ttk.Frame(options_frame)
        col2.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        col3 = ttk.Frame(options_frame)
        col3.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Колонка 1 (рабочие)
        self.remove_header_cb = ttk.Checkbutton(col1, variable=self.remove_header_var, text="Удалить заголовок",
                                                command=self._save_checkbox_states)
        self.remove_header_cb.pack(anchor=tk.W, pady=2)
        self.remove_header_cb.bind("<Enter>", lambda e: self.on_enter_tooltip("Если включено, удалит текст в документе от первого символа до второго вхождения кавычки. Внимание! Рекомендуется применять эту опцию для .rtf- и .html-файлов для корректной работы программы."))
        self.remove_header_cb.bind("<Leave>", self.on_leave_tooltip)

        self.download_file_check = ttk.Checkbutton(col1, variable=self.download_file_var,
                                                   text="Скачать и загрузить файл", command=self._save_checkbox_states)
        self.download_file_check.pack(anchor=tk.W, pady=2)
        self.tooltip_download = None
        self.download_file_check.bind("<Enter>", lambda e: self.on_download_check_hover("Еслю включено, автоматически скачает и загрузит в базу данных текст раздела / .html-файла / .docx-файла / .rtf-файла «Пояснительная записка»."))
        self.download_file_check.bind("<Leave>", self.hide_download_tooltip)

        # Колонка 2
        self.index_signatures_cb = ttk.Checkbutton(col2, variable=self.index_signatures_var,
                                                  text="Индексировать подписи",
                                                  command=self._save_checkbox_states)
        self.index_signatures_cb.pack(anchor=tk.W, pady=2)
        self.index_signatures_cb.bind("<Enter>", lambda e: self.on_index_sig_hover(
            "Если включено, автоматически ищет подписи (при наличии) и обрабатывает указанных субъектов."))
        self.index_signatures_cb.bind("<Leave>", self.hide_index_sig_tooltip)

        self.delete_signatures_cb = ttk.Checkbutton(col2, variable=self.delete_signatures_var, text="Удалять подписи",
                                                   command=self._save_checkbox_states)
        self.delete_signatures_cb.pack(anchor=tk.W, pady=2)
        self.delete_signatures_cb.bind("<Enter>", lambda e: self.on_del_sig_hover(
            "Если включено, удаляет блок подписей (при наличии) из файла после индексации (если индексация подписей включена)."))
        self.delete_signatures_cb.bind("<Leave>", self.hide_del_sig_tooltip)

        # Колонка 3
        self.auto_create_subjects_cb = ttk.Checkbutton(col3, variable=self.auto_create_subjects_var,
                                                       text="Автоматически создавать субъектов",
                                                       command=self._save_checkbox_states)
        self.auto_create_subjects_cb.pack(anchor=tk.W, pady=2)
        self.auto_create_subjects_cb.bind("<Enter>", lambda e: self.on_auto_create_hover(
            "Если включено, уведомляет о ненайденных СПЗИ и автоматически добавляет их в список субъектов с соответствующим описанием и фракцией \"Фракция не определена\"."))
        self.auto_create_subjects_cb.bind("<Leave>", self.hide_auto_create_tooltip)

        self.auto_create_signers_cb = ttk.Checkbutton(col3, variable=self.auto_create_signers_var,
                                                      text="Автоматически создавать подписавшихся субъектов",
                                                      command=self._save_checkbox_states)
        self.auto_create_signers_cb.pack(anchor=tk.W, pady=2)
        self.auto_create_signers_cb.bind("<Enter>", lambda e: self.on_auto_create_signers_hover(
            "Если включено, уведомляет о ненайденных подписавшихся и автоматически добавляет их в список субъектов с описанием \"Добавлен автоматически из подписи к источнику.\" и фракцией \"Фракция не определена\"."))
        self.auto_create_signers_cb.bind("<Leave>", self.hide_auto_create_signers_tooltip)

        reg_date_frame = ttk.Frame(self.window)
        reg_date_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(reg_date_frame, text="Дата регистрации законопроекта и материалов к нему (ДД.ММ.ГГГГ):").pack(
            anchor=tk.W)
        self.reg_date_entry = ttk.Entry(reg_date_frame, textvariable=self.registration_date_var, width=12)
        self.reg_date_entry.pack(anchor=tk.W)
        self.reg_date_entry.bind('<KeyRelease>', self.format_date_field)  # Используем существующий метод форматирования

        deputies_search_frame = ttk.Frame(self.window)
        deputies_search_frame.pack(fill=tk.X, padx=10, pady=(0, 2))
        ttk.Label(deputies_search_frame, text="Поиск субъектов:").pack(side=tk.LEFT, padx=(0, 5))
        self.deputies_search_var = tk.StringVar()
        deputies_search_entry = ttk.Entry(deputies_search_frame, textvariable=self.deputies_search_var, width=30)
        deputies_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.deputies_search_var.trace_add('write', lambda *a: self._filter_deputies_list())

        deputies_frame = ttk.Frame(self.window)
        deputies_frame.pack(fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(deputies_frame, text="Субъекты права законодательной инициативы:").pack(anchor=tk.W)

        self.all_deputies_for_import = []  # Полный список строк
        self.selected_deputies_set = set()  # Множество выбранных строк
        self._is_rendering = False  # Флаг защиты от сброса выделения при фильтрации

        self.deputies_listbox = tk.Listbox(deputies_frame, selectmode=tk.MULTIPLE, height=8, exportselection=False)  # 🔹 Увеличили с 4 до 8
        self.deputies_scrollbar = ttk.Scrollbar(deputies_frame, orient=tk.VERTICAL, command=self.deputies_listbox.yview)
        self.deputies_listbox.configure(yscrollcommand=self.deputies_scrollbar.set)
        self.deputies_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.deputies_listbox.bind('<<ListboxSelect>>', self._on_deputy_selection_change)
        self.deputies_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.load_deputies_for_selection()  # Заполняет self.all_deputies_for_import
        self._render_deputies_list()

        desc_frame = ttk.Frame(self.window)
        desc_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(0, 5))  # 🔹 expand=False, чтобы не растягивалось
        ttk.Label(desc_frame, text="Описание источника:").pack(anchor=tk.W)
        self.desc_text = tk.Text(desc_frame, height=3, wrap=tk.WORD, font=("Segoe UI", 9))  # 🔹 Уменьшили с 5 до 3
        sb_desc = ttk.Scrollbar(desc_frame, orient=tk.VERTICAL, command=self.desc_text.yview)
        self.desc_text.configure(yscrollcommand=sb_desc.set)
        self.desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_desc.pack(side=tk.RIGHT, fill=tk.Y)

        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        self.import_btn = ttk.Button(button_frame, text="Импортировать", command=self.import_file)
        self.import_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Отмена", command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

        self.deputies_list_from_db = self.load_deputies_list_from_db()
        print("DEBUG: deputies_list_from_db =", self.deputies_list_from_db)

    def on_auto_create_signers_hover(self, text):
        if hasattr(self, 'auto_create_signers_tooltip') and self.auto_create_signers_tooltip:
            self.auto_create_signers_tooltip.destroy()
        x, y, _, _ = self.auto_create_signers_cb.bbox("insert")
        x += self.auto_create_signers_cb.winfo_rootx() + 25
        y += self.auto_create_signers_cb.winfo_rooty() + 25
        self.auto_create_signers_tooltip = tk.Toplevel(self.window)
        self.auto_create_signers_tooltip.wm_overrideredirect(True)
        self.auto_create_signers_tooltip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.auto_create_signers_tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                  font=("tahoma", "8", "normal")).pack(ipadx=1, ipady=1)

    def hide_auto_create_signers_tooltip(self, event=None):
        if hasattr(self, 'auto_create_signers_tooltip') and self.auto_create_signers_tooltip:
            self.auto_create_signers_tooltip.destroy()

    def _on_deputy_selection_change(self, event=None):
        # Игнорируем событие, если идёт программная перерисовка списка
        if self._is_rendering:
            return

        # 1. Собираем элементы, выбранные в текущем (возможно отфильтрованном) списке
        current_visible_selected = set()
        for idx in self.deputies_listbox.curselection():
            current_visible_selected.add(self.deputies_listbox.get(idx))

        # 2. Находим элементы, которые были выбраны ранее, но сейчас скрыты из-за поиска
        all_currently_visible = {self.deputies_listbox.get(i) for i in range(self.deputies_listbox.size())}
        hidden_selected = self.selected_deputies_set - all_currently_visible

        # 3. Обновляем общее множество: скрытые выбранные + новые видимые выбранные
        self.selected_deputies_set = hidden_selected | current_visible_selected

        # 4. Перерисовываем список, чтобы выбранные поднялись наверх
        self.window.after(10, self._render_deputies_list)

    def _load_checkbox_states(self):
        settings_path = os.path.join(self.db_path, ".import_settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    states = json.load(f)
                self.remove_header_var.set(states.get("remove_header", True))
                self.download_file_var.set(states.get("download_file", False))
                self.index_signatures_var.set(states.get("index_signatures", False))
                self.delete_signatures_var.set(states.get("delete_signatures", False))
                self.auto_create_subjects_var.set(states.get("auto_create_subjects", False))
                self.auto_create_signers_var.set(states.get("auto_create_signers", False))
            except Exception: pass

    def _save_checkbox_states(self, event=None):
        settings_path = os.path.join(self.db_path, ".import_settings.json")
        states = {
            "remove_header": self.remove_header_var.get(),
            "download_file": self.download_file_var.get(),
            "index_signatures": self.index_signatures_var.get(),
            "delete_signatures": self.delete_signatures_var.get(),
            "auto_create_subjects": self.auto_create_subjects_var.get(),
            "auto_create_signers": self.auto_create_signers_var.get()
        }
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(states, f)

    def on_auto_create_hover(self, text):
        if hasattr(self, 'auto_create_tooltip') and self.auto_create_tooltip:
            self.auto_create_tooltip.destroy()
        x, y, _, _ = self.auto_create_subjects_cb.bbox("insert")
        x += self.auto_create_subjects_cb.winfo_rootx() + 25
        y += self.auto_create_subjects_cb.winfo_rooty() + 25
        self.auto_create_tooltip = tk.Toplevel(self.window)
        self.auto_create_tooltip.wm_overrideredirect(True)
        self.auto_create_tooltip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.auto_create_tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1, font=("tahoma", "8", "normal")).pack(ipadx=1, ipady=1)

    def hide_auto_create_tooltip(self, event=None):
        if hasattr(self, 'auto_create_tooltip') and self.auto_create_tooltip:
            self.auto_create_tooltip.destroy()

    def _filter_deputies_list(self):
        self._render_deputies_list()

    def on_url_change(self, *args):
        url = self.url_var.get().strip()
        if url:
            self.index_btn.config(state=tk.NORMAL)
        else:
            self.index_btn.config(state=tk.DISABLED)

    def hide_index_tooltip(self):
        if self.tooltip_index:
            self.tooltip_index.destroy()
            self.tooltip_index = None

    def on_index_btn_hover(self, text):
        self.hide_index_tooltip()
        x, y, _, _ = self.index_btn.bbox("insert")
        x += self.index_btn.winfo_rootx() + 25
        y += self.index_btn.winfo_rooty() + 25
        self.tooltip_index = tk.Toplevel(self.window)
        self.tooltip_index.wm_overrideredirect(True)
        self.tooltip_index.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip_index, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                          font=("tahoma", "8", "normal"))
        label.pack(ipadx=1, ipady=1)

    # --- НОВОЕ: Подсказка для галочки ---
    def hide_download_tooltip(self, event=None):
        if hasattr(self, 'tooltip_download') and self.tooltip_download:
            self.tooltip_download.destroy()
            self.tooltip_download = None

    def on_download_check_hover(self, text):
        self.hide_download_tooltip()
        x, y, _, _ = self.download_file_check.bbox("insert")
        x += self.download_file_check.winfo_rootx() + 25
        y += self.download_file_check.winfo_rooty() + 25
        self.tooltip_download = tk.Toplevel(self.window)
        self.tooltip_download.wm_overrideredirect(True)
        self.tooltip_download.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip_download, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                          font=("tahoma", "8", "normal"))
        label.pack(ipadx=1, ipady=1)

    def load_deputies_list_from_db(self):
        deputies_file_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        deputies = []
        if os.path.exists(deputies_file_path):
            with open(deputies_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 4:
                        surname, name, patronymic, faction = (x.strip() for x in parts[:4])
                        # 🔹 ИСПРАВЛЕНИЕ: Для СПЗИ/Органов (Имя == Фракция или пусто) берём ТОЛЬКО название из первой колонки
                        if (not name or name == faction) and ' — ' not in surname:
                            full_name = surname
                        else:
                            full_name = f"{surname} {name} {patronymic}".strip()
                        deputies.append((full_name, faction))
        return deputies

    def index_project(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Предупреждение", "Сначала введите URL законопроекта в СОЗД.")
            return

        parsed_url = urlparse(url)
        if parsed_url.netloc != "sozd.duma.gov.ru":
            if parsed_url:
                messagebox.showerror("Ошибка", f"Некорректный домен: {parsed_url.netloc}. Ожидался sozd.duma.gov.ru.")
            else:
                messagebox.showerror("Ошибка", f"Некорректный домен. Ожидался sozd.duma.gov.ru.")
            return

        if not messagebox.askyesno("Подтверждение",
                                   "Программа откроет ссылку в браузере по умолчанию и проиндексирует страницу. Продолжить?"):
            return

        # 1. Открываем в браузере
        webbrowser.open(url, new=2)

        # 2. Запускаем парсинг
        self.window.after(1000, self._perform_full_parsing, url)

    def _perform_full_parsing(self, url):
        errors = []
        title = None
        registration_date = None
        initiators_raw = []

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')

            # 🔹 КРИТИЧНО: сохраняем распаршенный HTML для поиска пояснительной записки
            self.parsed_soup = soup

            # --- Извлечение данных ---
            title = _extract_title_from_html_fixed(soup)
            if not title or title == "Название не найдено":
                errors.append("Название законопроекта не найдено")

            # Подготовка названия для отображения и сохранения
            desc_text_title = title
            title = sanitize_filename(title)
            desc_text_title = re.sub(r'_', ' ', desc_text_title)

            if len(title) > 50:
                if "-" in title and title.index("-") < 50:
                    title = title[:title.index("-") + 2]
                else:
                    title = title[:50]

            registration_date = _extract_registration_date_from_html_fixed(soup)
            if registration_date is None:
                errors.append("Дата регистрации не найдена")

            initiators_raw = _extract_initiators_from_html_fixed(soup)
            if not initiators_raw:
                errors.append("Субъекты права законодательной инициативы не найдены")

        except Exception as e:
            errors.append(f"Ошибка загрузки/парсинга: {str(e)}")

        # Если есть ошибки — показываем ОДНО окно и НЕ меняем поля
        if errors:
            msg = "При индексации возникли ошибки:\n" + "\n".join(f"• {err}" for err in errors)
            messagebox.showerror("Ошибки индексации", msg)
            return

        # Если всё OK — обновляем поля интерфейса
        self.source_name_var.set(title)
        self.registration_date_var.set(registration_date)
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", desc_text_title)

        # --- СОПОСТАВЛЕНИЕ ИНИЦИАТОРОВ С БАЗОЙ И АВТО-ВЫДЕЛЕНИЕ ---
        found_deputies_in_db = []
        unknown_deputies = []

        for name_str in initiators_raw:
            matched_name = self.match_deputy(name_str, self.deputies_list_from_db)
            if matched_name:
                found_deputies_in_db.append(matched_name)
            else:
                unknown_deputies.append(name_str)

        self.selected_deputies_set.clear()
        listbox_items = [self.deputies_listbox.get(i) for i in range(self.deputies_listbox.size())]

        for matched_name in found_deputies_in_db:
            norm_matched = re.sub(r'\s+', ' ', matched_name).strip().lower().replace('ё', 'е')
            for item in listbox_items:
                item_name_part = item.rsplit(' — ', 1)[0].strip().lower().replace('ё', 'е')
                if norm_matched == item_name_part or norm_matched in item:
                    self.selected_deputies_set.add(item)
                    break

        # 🔹 ПРИМЕНЯЕМ НОВУЮ СОРТИРОВКУ И ВОССТАНАВЛИВАЕМ ВЫДЕЛЕНИЕ
        self._render_deputies_list()

        # --- ШАГ 1: Скачиваем пояснительную записку (если нужно) ---
        # Это нужно сделать ДО парсинга подписей, чтобы файл существовал
        if self.download_file_var.get() and not self.selected_file_path.get().strip():
            self._resolve_explanatory_note()

        # --- ШАГ 2: Читаем файл и парсим подписи ---
        sig_names = []
        unknown_from_sigs = []  # 🔹 Создаём переменную ЗДЕСЬ
        has_sigs = False
        sig_cut_idx = 0

        file_path = self.selected_file_path.get().strip()
        if file_path and os.path.exists(file_path):
            # Читаем содержимое файла
            content = auto_decode_text(file_path)

            # Парсим подписи
            content, sig_names, has_sigs, sig_cut_idx = self._parse_file_signatures(content)

            if has_sigs:
                # Индексация подписей
                if self.index_signatures_var.get():
                    for name in sig_names:
                        matched = self.match_deputy(name, self.deputies_list_from_db)
                        if matched:
                            for db_full, db_faction in self.deputies_list_from_db:
                                if db_full == matched:
                                    self.selected_deputies_set.add(f"{db_full} — {db_faction.split('@')[0].strip()}")
                                    break
                        else:
                            unknown_from_sigs.append(name)

                # Удаление подписей из контента (если включено)
                if self.delete_signatures_var.get():
                    # Обрезаем контент до начала подписей
                    lines = content.split('\n')
                    new_content = '\n'.join(lines[:sig_cut_idx])

                    # Записываем очищенный контент обратно в файл
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)

                self.sigs_status = "удалены" if self.delete_signatures_var.get() else "сохранены"

        # --- ШАГ 3: Объединяем неизвестных из HTML и подписей ---
        all_unknown = list(dict.fromkeys(unknown_deputies + unknown_from_sigs))

        if all_unknown:
            if self.auto_create_subjects_var.get() or self.auto_create_signers_var.get():
                self.deputies_list_from_db = self.load_deputies_list_from_db()
                added_html, added_sigs, skipped = [], [], []
                deputies_file_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
                existing_names = {f[0].lower().replace('ё', 'е').replace('.', '').replace(' ', '') for f in
                                  self.deputies_list_from_db}

                for name_str in all_unknown:
                    name_str = name_str.strip()
                    match = re.match(r'^([А-ЯЁ])\.?\s*([А-ЯЁ])\.?\s*([А-ЯЁ][а-яё]+)$', name_str)
                    formatted = f"{match.group(3)} {match.group(1)} {match.group(2)}" if match else name_str
                    norm = formatted.lower().replace('ё', 'е').replace('.', '').replace(' ', '')

                    if norm in existing_names:
                        skipped.append(formatted)
                        for db_full, db_faction in self.deputies_list_from_db:
                            if db_full.lower().replace('ё', 'е').replace('.', '').replace(' ', '') == norm:
                                self.selected_deputies_set.add(f"{db_full} — {db_faction.split('@')[0].strip()}")
                                break
                    else:
                        is_sig = name_str in unknown_from_sigs
                        desc = "Добавлен автоматически из подписи к источнику." if is_sig and self.auto_create_signers_var.get() else "Добавлен автоматически при импортировании источника."

                        with open(deputies_file_path, 'a', encoding='utf-8') as f:
                            f.write(f"{formatted}\t\t\tФракция не определена@{desc}\n")

                        display = f"{formatted} — Фракция не определена"
                        self.selected_deputies_set.add(display)
                        (added_sigs if is_sig else added_html).append(formatted)

                self.deputies_list_from_db = self.load_deputies_list_from_db()
                self.load_deputies_for_selection()
                self._render_deputies_list()

                msg_parts = []
                if added_html: msg_parts.append(f"Добавлены (инициаторы):\n" + "\n".join(added_html))
                if added_sigs: msg_parts.append(f"Добавлены (подписи):\n" + "\n".join(added_sigs))
                if skipped: msg_parts.append(f"Уже существуют:\n" + "\n".join(skipped))
                messagebox.showinfo("Обработка субъектов", "\n\n".join(msg_parts))
            else:
                messagebox.showinfo("Неизвестные субъекты", f"Не найдены в базе:\n" + ", ".join(all_unknown))

        messagebox.showinfo("Успех", "Индексация завершена. Поля заполнены.")
        self._ensure_date_format(self.registration_date_var.get())

    # --- Вспомогательная функция сопоставления ---
    def match_deputy(self, name_str, deputies_db):
        if not name_str or not isinstance(name_str, str): return None
        raw_name = name_str.strip()
        # Нормализация: убираем точки, лишние пробелы, приводим к нижнему регистру
        norm_input = re.sub(r'[.\s]+', ' ', raw_name).lower().replace('ё', 'е').strip()
        input_words = norm_input.split()
        if not input_words: return None

        # 1. Точное совпадение (для полных имён и названий органов)
        for full_name, _ in deputies_db:
            norm_db = re.sub(r'[.\s]+', ' ', full_name).lower().replace('ё', 'е').strip()
            if norm_input == norm_db or norm_input in norm_db or norm_db in norm_input:
                return full_name

        # 2. Умный поиск по Фамилии + Инициалам (поддерживает "Зольцев В И", "Зольцев В.И.")
        surname_candidates = [w for w in input_words if len(w) > 1]
        initials_candidates = [w for w in input_words if len(w) == 1]

        if len(surname_candidates) == 1 and len(initials_candidates) <= 2:
            target_surname = surname_candidates[0]

            for full_name, _ in deputies_db:
                parts = re.sub(r'[.\s]+', ' ', full_name).lower().replace('ё', 'е').split()
                if not parts: continue

                db_surname = parts[0]
                db_other = parts[1:]

                # Совпадение фамилии
                if db_surname == target_surname or target_surname in db_surname or db_surname in target_surname:
                    db_initials = [p[0] for p in db_other if p]
                    # Инициалы совпадают по множеству первых букв
                    if set(initials_candidates) == set(db_initials) or (not initials_candidates and not db_initials):
                        return full_name

        # 3. Фоллбэк: строгое подмножество слов (для нестандартных записей)
        if len(input_words) > 1:
            input_set = set(input_words)
            for full_name, _ in deputies_db:
                db_words = set(re.sub(r'[.\s]+', ' ', full_name).lower().replace('ё', 'е').split())
                if input_set.issubset(db_words):
                    return full_name
        return None

    def _ensure_date_format(self, current_value):
        """Принудительно приводит значение к формату ДД.ММ.ГГГГ, если возможно."""
        if not current_value or not re.match(r'^\d{2}\.\d{2}\.\d{4}$', current_value):
            # Пытаемся извлечь дату из строки
            date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', current_value)
            if date_match:
                d, m, y = date_match.groups()
                formatted = f"{d}.{m}.{y}"
                self.registration_date_var.set(formatted)
                # Обновляем виджет вручную (т.к. переменная привязана, но иногда не обновляется)
                if hasattr(self, 'reg_date_entry'):
                    self.reg_date_entry.delete(0, tk.END)
                    self.reg_date_entry.insert(0, formatted)
            else:
                # Если не получилось — оставляем как есть (пользователь сам исправит)
                pass

    def format_date_field(self, event):
        entry = self.reg_date_entry  # ← Теперь точно тот же виджет
        value = entry.get()
        cursor_pos_original = entry.index(tk.INSERT)

        # Обработка ввода
        char = event.char
        if event.type == tk.EventType.KeyPress:
            if char.isdigit():
                new_value = value[:cursor_pos_original] + char + value[cursor_pos_original:]
            elif char == '.':
                new_value = value[:cursor_pos_original] + char + value[cursor_pos_original:]
            else:
                return  # игнорируем
        elif event.type == tk.EventType.KeyRelease:
            new_value = entry.get()
            cursor_pos_original = entry.index(tk.INSERT)
        else:
            new_value = entry.get()
            cursor_pos_original = entry.index(tk.INSERT)

        # Оставляем только цифры
        digits_only = ''.join(filter(str.isdigit, new_value))

        # Форматируем: ДД.ММ.ГГГГ
        formatted = ""
        for i, digit in enumerate(digits_only):
            if i == 2 or i == 4:
                formatted += '.'
            formatted += digit
        formatted = formatted[:10]  # максимум 10 символов

        # Устанавливаем курсор
        new_cursor = min(len(formatted), cursor_pos_original + formatted.count('.') - value.count('.'))
        if len(formatted) > 10:
            new_cursor = 10

        # Применяем
        self.registration_date_var.set(formatted)
        entry.delete(0, tk.END)
        entry.insert(0, formatted)
        entry.icursor(new_cursor)

    def _format_digits(self, digits, original_cursor_pos):
        """Вспомогательная функция для форматирования строки из цифр в ДД.ММ.ГГГГ и вычисления новой позиции курсора."""
        formatted = ""
        cursor_offset = 0  # Смещение курсора из-за добавленных точек

        for i, digit in enumerate(digits):
            if i == 2 or i == 4:  # После 2-й и 4-й цифры добавляем точку
                formatted += '.'
                cursor_offset += 1
                if i <= original_cursor_pos:  # Если точка вставлена до или на месте старого курсора
                    cursor_offset += 1  # Увеличиваем смещение, т.к. точка добавлена
            formatted += digit

        # Ограничиваем длину
        if len(formatted) > 10:
            formatted = formatted[:10]

        # Вычисляем новую позицию курсора
        # Позиция зависит от того, сколько точек было добавлено до старой позиции
        dots_before_old_pos = 0
        for i in range(min(original_cursor_pos, len(digits))):
            if i == 2 or i == 4:
                dots_before_old_pos += 1

        # Новая позиция = старая позиция цифр + количество добавленных точек до неё
        # Однако, если мы вставили точку *на* старую позицию, курсор сдвигается вправо
        new_cursor_pos = min(len(formatted), original_cursor_pos + dots_before_old_pos)
        # Если курсор был на границе, где вставляется точка, он может сдвинуться
        if original_cursor_pos in [2, 3] and len(digits) >= 2:  # Было 2 цифры, добавили точку
            if new_cursor_pos == 2:
                new_cursor_pos = 3  # Курсор после точки
        if original_cursor_pos in [4, 5] and len(digits) >= 4:  # Было 4 цифры, добавили точку
            if new_cursor_pos == 4:
                new_cursor_pos = 5  # Курсор после точки

        return formatted, new_cursor_pos

    def load_deputies_for_selection(self):
        deputies_file_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        self.all_deputies_for_import = []
        if os.path.exists(deputies_file_path):
            with open(deputies_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) >= 4:
                        surname, name, patronymic, raw_faction = (x.strip() for x in parts[:4])
                        faction = raw_faction.split('@')[0].strip() if '@' in raw_faction else raw_faction.strip()
                        self.all_deputies_for_import.append({
                            "full_name": f"{surname} {name} {patronymic}".strip(),
                            "faction": faction
                        })

    def _resolve_explanatory_note(self):
        """5-шаговая последовательность поиска пояснительной записки."""
        print("\n[ЗАПИСКА] 🚀 Запущен поиск пояснительной записки...")
        search_dirs = [os.path.join(self.db_path, "Downloads"), self.db_path]

        # 🔹 Вспомогательная функция: ищет <a>, внутри которого есть <span> с нужным классом
        def _find_note_link(icon_class_name):
            if not hasattr(self, 'parsed_soup') or not self.parsed_soup:
                return None
            for a_tag in self.parsed_soup.find_all('a', href=True):
                # BeautifulSoup парсит class в список, но в вашем HTML классы могут быть "слипшиеся"
                # Поэтому проверяем через in, а не точное совпадение
                icon = a_tag.find('span', class_=lambda c: c and icon_class_name in c and 'icon-file' in c)
                link_text = a_tag.get_text(strip=True).lower()
                # Проверяем, что ссылка действительно ведёт на записку
                if icon and any(kw in link_text for kw in ('запис', 'пояснит')):
                    return a_tag
            return None

        # ─────────────────────────────────────────────────────────────
        # 🔹 ШАГ 1: Текст из раздела #bh_note на сайте
        # ─────────────────────────────────────────────────────────────
        print("[ЗАПИСКА] 🔍 Шаг 1: Проверяю раздел #bh_note на странице...")
        if hasattr(self, 'parsed_soup') and self.parsed_soup:
            note_div = self.parsed_soup.find('div', id='bh_note')
            if note_div:
                # Извлекаем текст с сохранением переносов строк для абзацев
                text = note_div.get_text(separator='\n', strip=True)
                text = re.sub(r'\n{3,}', '\n\n', text).strip()  # Оставляем двойные \n для абзацев
                print(f"[ЗАПИСКА] 📝 Извлечено {len(text)} символов.")
                if len(text) > 50:
                    dl_dir = os.path.join(self.db_path, "Downloads")
                    os.makedirs(dl_dir, exist_ok=True)
                    temp_path = os.path.join(dl_dir, "explanatory_note.txt")
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        f.write(text)
                    self.selected_file_path.set(temp_path)
                    self.file_label.config(text=os.path.basename(temp_path))
                    print(f"[ЗАПИСКА] ✅ Шаг 1: Найдено {len(text)} символов в #bh_note.")
                    return True
                else:
                    print("[ЗАПИСКА] ⚠️ Шаг 1: Текст слишком короткий (<50 символов), пропускаю.")
            else:
                print("[ЗАПИСКА] ⏭️ Шаг 1: Раздел #bh_note не найден.")
        else:
            print("[ЗАПИСКА] ⏭️ Шаг 1: Пропущен (нет распаршенного soup).")

        # ─────────────────────────────────────────────────────────────
        # 🔹 ШАГ 2: Ссылка на .html или .docx в странице
        # ─────────────────────────────────────────────────────────────
        print("[ЗАПИСКА] 🔍 Шаг 2: Ищу ссылку на файл записки в странице...")

        # 2А: Поиск HTML (format-html или format-htmlicon)
        # Учитываем, что в вашем HTML класс может быть "format-htmlicon-file" (слитно)
        html_link = _find_note_link('format-html') or _find_note_link('format-htmlicon')
        if html_link:
            full_url = html_link['href']
            if not full_url.startswith('http'):
                full_url = f"https://sozd.duma.gov.ru{full_url}"
            print(f"[ЗАПИСКА] 🌐 Шаг 2а: Нашёл HTML-ссылку: {full_url}")
            try:
                session = requests.Session()
                if hasattr(self, 'url_var') and self.url_var.get():
                    session.get(self.url_var.get(), timeout=10)
                resp = session.get(full_url, timeout=10)
                resp.raise_for_status()
                processed = _process_html_note(resp.content)
                if len(processed) > 50:
                    dl_dir = os.path.join(self.db_path, "Downloads")
                    os.makedirs(dl_dir, exist_ok=True)
                    temp_path = os.path.join(dl_dir, "explanatory_note.txt")
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        f.write(processed)
                    self.selected_file_path.set(temp_path)
                    self.file_label.config(text=os.path.basename(temp_path))
                    print(f"[ЗАПИСКА] ✅ Шаг 2а: HTML-записка загружена и обработана.")
                    return True
                else:
                    print("[ЗАПИСКА] ⚠️ Шаг 2а: Обработанный текст слишком короткий.")
            except Exception as e:
                print(f"[ЗАПИСКА] ⚠️ Шаг 2а: Ошибка загрузки HTML: {e}")

        # 2Б: Поиск DOCX/DOC (format-msword)
        doc_link = _find_note_link('format-msword')
        if doc_link:
            full_url = doc_link['href']
            if not full_url.startswith('http'):
                full_url = f"https://sozd.duma.gov.ru{full_url}"
            print(f"[ЗАПИСКА] 📄 Шаг 2б: Нашёл ссылку на файл Word: {full_url}")
            try:
                dl_dir = os.path.join(self.db_path, "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                local_path = os.path.join(dl_dir, "explanatory_note_temp.docx")

                session = requests.Session()
                if hasattr(self, 'url_var') and self.url_var.get():
                    session.get(self.url_var.get(), timeout=10)
                resp = session.get(full_url, stream=True, timeout=15)
                resp.raise_for_status()

                with open(local_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # 🔍 Проверка заголовка файла: \x50\x4b\x03\x04 = ZIP-архив = .docx
                with open(local_path, 'rb') as f:
                    header = f.read(4)

                if header.startswith(b'\x50\x4b\x03\x04'):
                    print("[ЗАПИСКА] ✅ Шаг 2б: Успешно скачан и подтверждён формат .docx")
                    self.selected_file_path.set(local_path)
                    self.file_label.config(text=os.path.basename(local_path))
                    return True
                else:  # Старый .doc (OLE2)
                    print("[ЗАПИСКА] ⚠️ Шаг 2б: Скачан файл в старом формате .doc")
                    if os.path.exists(local_path):
                        os.remove(local_path)
                    messagebox.showwarning(
                        "Старый формат файла",
                        "Сайт отдал файл в формате .doc.\n"
                        "Программа может обрабатывать только .docx.\n"
                        "Пожалуйста, откройте файл в Word и сохраните как .docx, либо используйте HTML-версию."
                    )
            except Exception as e:
                print(f"[ЗАПИСКА] ⚠️ Шаг 2б: Ошибка скачивания: {e}")

        # 2В: Поиск RTF (format-rtf icon-file)
        rtf_link = _find_note_link('format-rtf')
        if rtf_link:
            full_url = rtf_link['href']
            if not full_url.startswith('http'):
                full_url = f"https://sozd.duma.gov.ru{full_url}"
            print(f"[ЗАПИСКА] 📄 Шаг 2в: Нашёл ссылку на RTF: {full_url}")
            try:
                dl_dir = os.path.join(self.db_path, "Downloads")
                os.makedirs(dl_dir, exist_ok=True)
                local_rtf = os.path.join(dl_dir, "explanatory_note_temp.rtf")

                resp = requests.get(full_url, timeout=15, stream=True)
                resp.raise_for_status()
                with open(local_rtf, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Извлекаем текст из RTF
                rtf_text = _extract_text_from_rtf(local_rtf)
                if len(rtf_text) > 50:
                    temp_txt = os.path.join(dl_dir, "explanatory_note.txt")
                    with open(temp_txt, 'w', encoding='utf-8') as f:
                        f.write(rtf_text)
                    self.selected_file_path.set(temp_txt)
                    self.file_label.config(text="explanatory_note.txt")
                    print("[ЗАПИСКА] ✅ Шаг 2в: RTF успешно конвертирован и загружен.")
                    return True
                else:
                    print("[ЗАПИСКА] ⚠️ Шаг 2в: Извлечённый текст слишком короткий.")
            except Exception as e:
                print(f"[ЗАПИСКА] ⚠️ Шаг 2в: Ошибка обработки RTF: {e}")

        print("[ЗАПИСКА] ⏭️ Шаг 2: Файл на странице не найден или не удалось загрузить.")

        # ─────────────────────────────────────────────────────────────
        # 🔹 ШАГ 3: Локальный .docx
        # ─────────────────────────────────────────────────────────────
        print("[ЗАПИСКА] 🔍 Шаг 3: Ищу локальный .docx файл...")
        for d in search_dirs:
            if not os.path.exists(d): continue
            for fname in os.listdir(d):
                if fname.lower().endswith('.docx') and 'записка' in fname.lower():
                    self.selected_file_path.set(os.path.join(d, fname))
                    self.file_label.config(text=fname)
                    print(f"[ЗАПИСКА] ✅ Шаг 3: Найден локальный .docx: {fname}")
                    return True
        print("[ЗАПИСКА] ⏭️ Шаг 3: Локальный .docx не найден.")

        # ─────────────────────────────────────────────────────────────
        # 🔹 ШАГ 4: Локальный .doc (предупреждение)
        # ─────────────────────────────────────────────────────────────
        print("[ЗАПИСКА] 🔍 Шаг 4: Проверяю наличие .doc файла...")
        for d in search_dirs:
            if not os.path.exists(d): continue
            for fname in os.listdir(d):
                if fname.lower().endswith('.doc') and 'записка' in fname.lower():
                    messagebox.showwarning(
                        "Найден .doc",
                        f"Обнаружен локальный файл '{fname}' в старом формате .doc.\n"
                        "Программа не может его прочитать. Сохраните его как .docx."
                    )
                    return False

        # ─────────────────────────────────────────────────────────────
        # 🔹 ШАГ 5: Ошибка — ничего не найдено
        # ─────────────────────────────────────────────────────────────
        print("[ЗАПИСКА] ❌ Шаг 5: Пояснительная записка не найдена.")

        current_name = self.source_name_var.get().strip()
        if not current_name.endswith("_(-)"):
            self.source_name_var.set(f"{current_name}_(-)")

        current_desc = self.desc_text.get("1.0", tk.END).strip()
        marker = "ПОЯСНИТЕЛЬНАЯ ЗАПИСКА ОТСУТСТВУЕТ."
        if marker not in current_desc:
            new_desc = f"{current_desc}\n{marker}" if current_desc else marker
            self.desc_text.delete("1.0", tk.END)
            self.desc_text.insert("1.0", new_desc)

        if self.download_file_var.get():
            dl_dir = os.path.join(self.db_path, "Downloads")
            os.makedirs(dl_dir, exist_ok=True)
            placeholder_path = os.path.join(dl_dir, "explanatory_note.txt")
            try:
                with open(placeholder_path, 'w', encoding='utf-8') as f:
                    f.write("-")
                self.selected_file_path.set(placeholder_path)
                self.file_label.config(text=os.path.basename(placeholder_path))
                print(f"[ЗАПИСКА] Создан файл-заглушка: {placeholder_path}")
            except Exception as e:
                print(f"[ЗАПИСКА] Ошибка создания заглушки: {e}")

        messagebox.showerror(
            "Поиск завершён",
            "Пояснительная записка не найдена.\n"
            "Проверьте:\n"
            "1) Наличие раздела \"Пояснительная записка\" на странице сайта;\n"
            "2) Наличие ссылки на .html или .docx с \"записка\" в названии;\n"
            "Прикрепите файл вручную через кнопку \"Загрузить файл\"."
        )
        return False

    def _get_import_sort_key(self, dep):
        """Возвращает ключ сортировки по правилам: Выбранные > Системные > Фракция > ФИО"""
        display = f"{dep['full_name']} — {dep['faction']}"
        is_selected = 0 if display in self.selected_deputies_set else 1
        is_system = 0 if dep['faction'] in getattr(__import__('config'), 'SYSTEM_FACTIONS', []) else 1
        return (is_selected, is_system, dep['faction'].lower(), dep['full_name'].lower())

    def _render_deputies_list(self):
        # 🔹 СТРОГАЯ ЗАЩИТА ОТ ПОВТОРНЫХ ВЫЗОВОВ ПРИ БЫСТРОМ ПОИСКЕ
        if getattr(self, '_is_rendering', False): return
        self._is_rendering = True

        if not hasattr(self, 'window') or not self.window.winfo_exists():
            self._is_rendering = False
            return

        self.deputies_listbox.delete(0, tk.END)
        query = self.deputies_search_var.get().lower()

        filtered = [d for d in self.all_deputies_for_import
                    if not query or query in d["full_name"].lower() or query in d["faction"].lower()]

        filtered.sort(key=self._get_import_sort_key)

        for i, dep in enumerate(filtered):
            display_text = f"{dep['full_name']} — {dep['faction']}"
            self.deputies_listbox.insert(tk.END, display_text)
            if display_text in self.selected_deputies_set:
                self.deputies_listbox.selection_set(i)

        self._is_rendering = False

    def on_enter_tooltip(self, text):
        if self.tooltip:
            self.tooltip.destroy()
        x, y, _, _ = self.remove_header_cb.bbox("insert")
        x += self.remove_header_cb.winfo_rootx() + 25
        y += self.remove_header_cb.winfo_rooty() + 25
        self.tooltip = tk.Toplevel(self.window)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1,
                          font=("tahoma", "8", "normal"))
        label.pack(ipadx=1, ipady=1)

    def on_leave_tooltip(self, event=None):
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None

    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="Выберите текстовый файл",
            filetypes=[("Text files", "*.txt"), ("Word documents", "*.docx"), ("All files", "*.*")]
        )
        if not file_path:
            return

        basename = os.path.basename(file_path)
        name_without_ext, ext = os.path.splitext(basename)
        self.source_name_var.set(name_without_ext[:50])

        if ext.lower() == '.docx':
            try:
                doc = Document(file_path)
                full_text = '\n'.join([para.text for para in doc.paragraphs])
                # Используем системную временную директорию вместо cwd
                temp_dir = tempfile.gettempdir()
                temp_txt = os.path.join(temp_dir, f"{name_without_ext}_import_temp.txt")
                with open(temp_txt, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                self.selected_file_path.set(temp_txt)
                self.file_label.config(text=f"[Временный] {os.path.basename(temp_txt)}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось прочитать .docx:\n{e}")
                self.selected_file_path.set("")
        else:
            self.selected_file_path.set(file_path)
            self.file_label.config(text=basename)

    def import_file(self):
        file_path = self.selected_file_path.get().strip()
        source_name = self.source_name_var.get().strip()
        url = self.url_var.get().strip()
        pub_date = self.registration_date_var.get().strip()
        selected_deputies = list(self.selected_deputies_set)
        description = self.desc_text.get("1.0", tk.END).strip()
        remove_header_flag = self.remove_header_var.get()
        current_sigs_status = self.sigs_status

        if not source_name:
            messagebox.showerror("Ошибка", "Название источника не может быть пустым.")
            return
        if len(source_name) > 50:
            messagebox.showerror("Ошибка", "Название источника не должно превышать 50 символов.")
            return
        if not file_path or not os.path.isfile(file_path):
            messagebox.showerror("Ошибка", "Файл не выбран или не существует.")
            return

        is_valid, msg = is_valid_source_name(source_name)
        if not is_valid:
            messagebox.showerror("Ошибка", msg)
            return

        try:
            with open(os.path.join(self.db_path, ".remove_header_state"), "w") as f:
                f.write(str(remove_header_flag))
        except Exception:
            pass

        sources_dir = os.path.join(self.db_path, SOURCES_DIR_NAME)
        os.makedirs(sources_dir, exist_ok=True)
        dest_path = os.path.normpath(os.path.join(sources_dir, source_name + '.txt'))

        if os.path.exists(dest_path):
            if not messagebox.askyesno("Файл существует", f"Файл '{source_name}.txt' уже существует. Перезаписать?"):
                return

        task_data = {
            "file_path": file_path, "source_name": source_name, "url": url,
            "pub_date": pub_date, "selected_deputies": selected_deputies,
            "description": description, "remove_header_flag": remove_header_flag,
            "current_sigs_status": current_sigs_status
        }
        threading.Thread(target=self._heavy_import_task, args=(task_data,), daemon=True).start()

    def _disable_import_btn(self):
        if hasattr(self, 'import_btn'):
            self.import_btn.config(state=tk.DISABLED, text="Обработка...")
        else:
            self.index_btn.config(state=tk.DISABLED)

    def _enable_import_btn(self):
        if hasattr(self, 'import_btn'):
            self.import_btn.config(state=tk.NORMAL, text="Импортировать")
        else:
            self.index_btn.config(state=tk.NORMAL)

    def _heavy_import_task(self, task_data):
        file_path = task_data["file_path"]
        source_name = task_data["source_name"]
        url = task_data["url"]
        pub_date = task_data["pub_date"]
        selected_deputies = task_data["selected_deputies"]
        description = task_data["description"]
        remove_header_flag = task_data["remove_header_flag"]
        current_sigs_status = task_data["current_sigs_status"]

        try:
            # 🔥 2. Быстрое чтение без chardet для малых файлов
            with open(file_path, 'rb') as f:
                raw = f.read()

            # Попытка декодирования по скорости: UTF-8 -> CP1251 -> fallback
            try:
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    content = raw.decode('cp1251')
                except UnicodeDecodeError:
                    # Только если стандартные не сработали, используем авто-определение
                    content = auto_decode_text(file_path)

                    # 🔹 Исправление разрывов слов из-за переносов строк в документах
                    # 1. Остальные переносы строк заменяем на пробел (сохраняем абзацы как пробелы)
                    content = re.sub(r'\n+', ' ', content)
                    # 2. Нормализуем множественные пробелы
                    content = re.sub(r'\s+', ' ', content).strip()

            if not content.strip():
                self.window.after(0, lambda: self._safe_call(
                    lambda: messagebox.showwarning("Предупреждение", "Файл пуст или не содержит читаемого текста.")))
                self.window.after(0, lambda: self._safe_call(self._enable_import_btn))
                return

            header_removed = False
            if remove_header_flag:
                original_len = len(content)
                content = remove_header(content)
                header_removed = len(content) < original_len

            sources_dir = os.path.join(self.db_path, SOURCES_DIR_NAME)
            dest_path = os.path.normpath(os.path.join(sources_dir, source_name + '.txt'))
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(content)

            sources_list_path = os.path.join(self.db_path, SOURCES_LIST_FILE_NAME)
            try:
                lines = []
                if os.path.exists(sources_list_path):
                    with open(sources_list_path, 'r', encoding='utf-8') as f:
                        lines = [l.strip() for l in f if l.strip()]
                entry = f"{source_name}.txt"
                if entry not in lines:
                    lines.append(entry)
                with open(sources_list_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines) + '\n')
            except Exception:
                pass

            # 🔥 3. Кэширование ngram_mapping на уровне сессии (если возможно) или быстрая загрузка
            from core.nlp import get_ngram_mapping
            ngram_mapping = get_ngram_mapping(self.db_path)

            stopwords = get_active_stopwords(self.db_path)

            tokens = process_source_text_to_lemmas(content, ngram_mapping, stopwords)

            tokens_counter = Counter(tokens)

            lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
            os.makedirs(lexemes_dir, exist_ok=True)
            lexemes_file_path = os.path.join(lexemes_dir, f"{source_name}.json")

            extracted_date = pub_date
            if not extracted_date or not re.match(r'^\d{2}\.\d{2}\.\d{4}$', extracted_date):
                parsed_url = urllib.parse.urlparse(url)
                if parsed_url.netloc and 'sozd' in parsed_url.netloc:
                    date_match = re.search(r'\b(\d{2}\.\d{2}\.\d{4})\b', url)
                    extracted_date = date_match.group(1) if date_match else datetime.now().strftime("%d.%m.%Y")
                else:
                    extracted_date = datetime.now().strftime("%d.%m.%Y")

            try:
                day, month, year = extracted_date.split('.')
                extracted_date_iso = f"{year}-{month}-{day}"
            except ValueError:
                extracted_date_iso = datetime.now().strftime("%Y-%m-%d")

            with open(lexemes_file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "tokens": dict(tokens_counter),
                    "date": extracted_date_iso,
                    "unique_tokens": list(tokens_counter.keys()),
                    "deputies": selected_deputies,
                    "url": url,
                    "description": description
                }, f, ensure_ascii=False, indent=2)

            os.utime(self.db_path, None)

            self.window.after(0, self._on_import_complete, source_name, header_removed, current_sigs_status,
                              len(selected_deputies))


        except Exception as e:
            traceback.print_exc()
            self.window.after(0, lambda: self._safe_call(
                lambda: messagebox.showerror("Ошибка импорта", f"Не удалось обработать файл:\n{str(e)}")))
            self.window.after(0, lambda: self._safe_call(self._enable_import_btn))

    def _on_import_complete(self, source_name, header_removed, sigs_status, deputies_count):
        if not hasattr(self, 'window') or not self.window.winfo_exists():
            return

        self.selected_deputies_set.clear()
        self._render_deputies_list()

        try:
            self.window.grab_release()
        except:
            pass

        status_h = "удалён" if header_removed else "сохранён"
        messagebox.showinfo(
            "Успешно",
            f"Файл '{source_name}' успешно импортирован.\nЗаголовок {status_h}. Подписи {sigs_status}.",
            parent=self.window
        )

        try:
            self.window.grab_set()
        except:
            pass

        self.selected_file_path.set("")
        self.file_label.config(text="")
        self.source_name_var.set("")
        self.url_var.set("")
        self.registration_date_var.set("")
        self.desc_text.delete("1.0", tk.END)
        self._enable_import_btn()

    def _safe_call(self, func):
        """Безопасная обёртка для вызова GUI-функций из других потоков"""
        try:
            if hasattr(self, 'window') and self.window.winfo_exists():
                func()
        except tk.TclError:
            pass

    def on_index_sig_hover(self, text):
        if hasattr(self, 'index_sig_tooltip') and self.index_sig_tooltip: self.index_sig_tooltip.destroy()
        x, y, _, _ = self.index_signatures_cb.bbox("insert")
        x += self.index_signatures_cb.winfo_rootx() + 25; y += self.index_signatures_cb.winfo_rooty() + 25
        self.index_sig_tooltip = tk.Toplevel(self.window); self.index_sig_tooltip.wm_overrideredirect(True)
        self.index_sig_tooltip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.index_sig_tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1, font=("tahoma", "8", "normal")).pack(ipadx=1, ipady=1)
    def hide_index_sig_tooltip(self, event=None):
        if hasattr(self, 'index_sig_tooltip') and self.index_sig_tooltip: self.index_sig_tooltip.destroy()

    def on_del_sig_hover(self, text):
        if hasattr(self, 'del_sig_tooltip') and self.del_sig_tooltip: self.del_sig_tooltip.destroy()
        x, y, _, _ = self.delete_signatures_cb.bbox("insert")
        x += self.delete_signatures_cb.winfo_rootx() + 25; y += self.delete_signatures_cb.winfo_rooty() + 25
        self.del_sig_tooltip = tk.Toplevel(self.window); self.del_sig_tooltip.wm_overrideredirect(True)
        self.del_sig_tooltip.wm_geometry(f"+{x}+{y}")
        ttk.Label(self.del_sig_tooltip, text=text, background="#ffffe0", relief="solid", borderwidth=1, font=("tahoma", "8", "normal")).pack(ipadx=1, ipady=1)
    def hide_del_sig_tooltip(self, event=None):
        if hasattr(self, 'del_sig_tooltip') and self.del_sig_tooltip: self.del_sig_tooltip.destroy()

    def _parse_file_signatures(self, content):
        lines = content.split('\n')
        if len(lines) < 3: return content, [], False, 0

        # 1. Проверяем последние 5 строк на метки даты/времени
        end_block = '\n'.join(lines[-5:])
        dt_pattern = re.compile(
            r'(\d{1,2}[:.]\d{2}\s*(?:AM|PM)?)|(\d{1,2}[/\\\.]\d{1,2}[/\\\.]\d{2,4})|'
            r'(\d{2,4}[/\\\.]\d{1,2}[/\\\.]\d{1,2})|(в\s+\d{1,2}[:.]\d{2})', re.IGNORECASE
        )
        if not dt_pattern.search(end_block):
            return content, [], False, 0

        # 2. Ищем маркер с конца
        deputies_idx = colon_idx = -1
        for i in range(len(lines) - 1, -1, -1):
            s = lines[i].strip().lower()
            if s == 'депутаты' or s.startswith('депутаты '): deputies_idx = i
            if ':' in lines[i].strip() and colon_idx == -1: colon_idx = i

        marker_idx = deputies_idx if deputies_idx != -1 else colon_idx
        marker_type = 'deputies' if deputies_idx != -1 else ('colon' if colon_idx != -1 else None)
        if marker_idx == -1: return content, [], False, 0

        # 3. Извлекаем и чистим имена
        sig_text = '\n'.join(lines[marker_idx + 1:])
        name_pat = re.compile(r'([А-ЯЁ]\.?\s*){1,2}[А-ЯЁ][а-яё]+|[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+',
                              re.UNICODE)
        found = []
        for m in name_pat.finditer(sig_text):
            name = m.group(0).strip()
            name = re.sub(r'\s*[—-]\s*[^;]+;?\s*$', '', name).strip()  # Убираем "- должность;"
            found.append(name)

        found = list(dict.fromkeys(found))  # Убираем дубли с сохранением порядка
        if not found: return content, [], False, 0

        return content, found, True, marker_idx

    def __del__(self):
        if hasattr(self, 'selected_file_path'):
            path = self.selected_file_path.get()
            if path and path.endswith('_temp.txt') and os.path.isfile(path):
                try:
                    os.remove(path)
                except:
                    pass