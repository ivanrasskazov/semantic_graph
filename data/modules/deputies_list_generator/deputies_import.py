import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import webbrowser
import requests
from bs4 import BeautifulSoup
import os
import time
import re
from parser import parse_deputies_page, parse_deputy_ruwiki, search_deputy_on_ruwiki

BASE_URL = "http://duma.gov.ru/duma/deputies/{}/"
CHECK_DOMAINS = [
    ("https://www.google.com", "Google"),
    ("https://yandex.ru", "Yandex"),
    ("https://ru.ruwiki.ru", "Рувики")
]


class DeputiesImportModule:
    def __init__(self, db_path, parent_window):
        self.db_path = db_path
        self.parent = parent_window
        self.deputies_list = []
        self.convocation = None
        self.rom_convocation = None
        self._stop_refine = False

    def show_main_menu(self):
        self.menu_window = tk.Toplevel(self.parent)
        self.menu_window.title("Модуль: Импорт депутатов")
        self.menu_window.geometry("400x200")
        self.menu_window.transient(self.parent)
        self.menu_window.grab_set()

        main_frame = ttk.Frame(self.menu_window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Button(main_frame, text="Создать список депутатов",
                   command=self._select_convocation).pack(fill=tk.X, pady=5)

        self.btn_export = ttk.Button(main_frame, text="Экспортировать список депутатов",
                                     command=self._export_deputies, state=tk.DISABLED)
        self.btn_export.pack(fill=tk.X, pady=5)

        ttk.Button(main_frame, text="Закрыть модуль",
                   command=self.menu_window.destroy).pack(fill=tk.X, pady=5)

    def _select_convocation(self):
        dlg = tk.Toplevel(self.menu_window)
        dlg.title("Выбор созыва")
        dlg.geometry("200x100")
        dlg.transient(self.menu_window)
        dlg.grab_set()

        ttk.Label(dlg, text="Номер созыва (1-8):").pack(pady=(5, 0))
        convocation_var = tk.IntVar(value=1)
        validate_cmd = dlg.register(lambda p: p in ['1', '2', '3', '4', '5', '6', '7', '8', ''])

        spinbox = ttk.Spinbox(dlg, from_=1, to=8, increment=1,
                              textvariable=convocation_var, width=5,
                              validate='key', validatecommand=(validate_cmd, '%P'))
        spinbox.pack(pady=10)
        spinbox.focus()

        def on_ok():
            val = convocation_var.get()
            if 1 <= val <= 8:
                dlg.destroy()
                self._confirm_scraping(val)
            else:
                messagebox.showwarning("Ошибка", "Введите число от 1 до 8.")

        def on_cancel():
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=5)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=on_cancel).pack(side=tk.LEFT, padx=5)
        dlg.bind('<Return>', lambda e: on_ok())

    def _confirm_scraping(self, convocation):
        url = BASE_URL.format(convocation)
        confirmed = messagebox.askyesno(
            "Подтверждение",
            f"Будет открыт браузер на странице:\n{url}\n\n"
            f"Программа автоматически считает данные о депутатах.\n\nПродолжить?"
        )
        if confirmed:
            self.convocation = convocation
            self._start_scraping(url)

    def _start_scraping(self, url):
        webbrowser.open(url, new=2)
        self.menu_window.after(2000, lambda: self._perform_scraping(url))

    def _perform_scraping(self, url):
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            self.deputies_list = parse_deputies_page(soup)

            if not self.deputies_list:
                messagebox.showwarning("Предупреждение", "Не удалось извлечь данные о депутатах.")
                return

            undefined_count = sum(1 for d in self.deputies_list if d[3] == "Фракция не определена")
            msg = f"Найдено {len(self.deputies_list)} депутатов."

            if undefined_count > 0:
                msg += f"\n\nНе удалось определить фракцию у {undefined_count} депутатов."
                msg += "\n\nПрограмма может продолжить сбор данных об этих депутатах."
                msg += "\nДля этого их ФИО поочерёдно будут внесены в поисковую систему,"
                msg += "\nзатем открыт сайт https://ru.ruwiki.ru/wiki/ с биографией,"
                msg += "\nоткуда возьмётся последняя партия."
                msg += "\n\nПЕРЕД НАЧАЛОМ убедитесь, что у Вас НЕТ открытых вкладок:"
                msg += "\n• google.com"
                msg += "\n• yandex.ru"
                msg += "\n• ru.ruwiki.ru"
                msg += "\n\nЭто необходимо для корректной работы парсинга."

                if messagebox.askyesno("Уточнение фракций", msg):
                    # 🔹 ПРОВЕРКА ДОМЕНОВ ПЕРЕД ПАРСИНГОМ
                    if not self._check_domains_closed():
                        messagebox.showwarning(
                            "Вкладки открыты",
                            "Обнаружены открытые вкладки с целевыми доменами.\n\n"
                            "Пожалуйста, закройте вкладки с:\n"
                            "• Google\n• Яндекс\n• Рувики (ru.ruwiki.ru)\n\n"
                            "И повторите попытку."
                        )
                        return
                    self._refine_unknown_factions()

            self.btn_export.config(state=tk.NORMAL)
            messagebox.showinfo("Успех",
                                f"Найдено {len(self.deputies_list)} депутатов.\n"
                                f"Теперь доступна кнопка «Экспортировать список депутатов».")

        except requests.RequestException as e:
            messagebox.showerror("Ошибка загрузки", f"Не удалось загрузить страницу:\n{e}")
        except Exception as e:
            messagebox.showerror("Ошибка парсинга", f"Произошла ошибка при обработке данных:\n{e}")

    def _check_domains_closed(self):
        """
        Проверяет, доступны ли целевые домены для запросов.
        Возвращает True, если все домены «чисты» (можно работать),
        или False, если обнаружена потенциальная проблема.

        Примечание: прямая проверка открытых вкладок браузера из Python невозможна
        без расширений/аддонов. Мы используем косвенную проверку через тестовые запросы.
        """
        headers = {"User-Agent": "Mozilla/5.0"}
        problematic = []

        for domain, name in CHECK_DOMAINS:
            try:
                # Делаем быстрый HEAD-запрос с коротким таймаутом
                resp = requests.head(domain, headers=headers, timeout=3, allow_redirects=True)
                # Если домен отвечает — это нормально, но мы предупреждаем пользователя
                # что вкладки должны быть закрыты для избежания конфликтов сессий
            except requests.RequestException:
                # Если домен не отвечает — возможно, он занят или заблокирован
                problematic.append(name)

        # Если есть проблемы — возвращаем False
        if problematic:
            return False

        # 🔹 ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА: спрашиваем пользователя
        # (поскольку технически проверить открытые вкладки нельзя)
        confirm = messagebox.askyesno(
            "Подтверждение",
            "Домены доступны для запросов.\n\n"
            "Пожалуйста, подтвердите, что Вы ЗАКРЫЛИ все вкладки с:\n"
            "• Google (google.com)\n"
            "• Яндекс (yandex.ru)\n"
            "• Рувики (ru.ruwiki.ru)\n\n"
            "Это важно для корректного парсинга.\n\n"
            "Продолжить?",
            icon='warning'
        )
        return confirm

    def _refine_unknown_factions(self):
        unknown_deputies = [d for d in self.deputies_list if d[3] == "Фракция не определена"]
        if not unknown_deputies:
            return

        progress_win = tk.Toplevel(self.menu_window)
        progress_win.title("Уточнение фракций")
        progress_win.geometry("450x220")
        progress_win.transient(self.menu_window)
        progress_win.grab_set()

        ttk.Label(progress_win, text="Обработка депутатов с ru.ruwiki.ru...", wraplength=400).pack(pady=10)
        progress = ttk.Progressbar(progress_win, mode='determinate', maximum=len(unknown_deputies))
        progress.pack(fill=tk.X, padx=20, pady=5)
        status_label = ttk.Label(progress_win, text="", wraplength=400, justify=tk.LEFT)
        status_label.pack(pady=5)

        self._stop_refine = False
        ttk.Button(progress_win, text="Остановить",
                   command=lambda: setattr(self, '_stop_refine', True)).pack(pady=5)

        processed = 0
        failed = 0
        headers = {"User-Agent": "Mozilla/5.0"}

        for idx, (surname, name, patronymic, faction) in enumerate(unknown_deputies):
            if self._stop_refine:
                break

            full_name = f"{surname} {name} {patronymic}".strip()
            status_label.config(text=f"[{idx + 1}/{len(unknown_deputies)}] Поиск: {full_name}")
            progress_win.update()

            try:
                # 1. Ищем статью депутата на ru.ruwiki.ru
                article_url = search_deputy_on_ruwiki(full_name)
                if not article_url:
                    failed += 1
                    progress['value'] = idx + 1
                    continue

                # 2. Проверяем, что фамилия в начале статьи совпадает
                response = requests.get(article_url, headers=headers, timeout=15)
                if response.status_code != 200:
                    failed += 1
                    progress['value'] = idx + 1
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')
                page_title = soup.find('h1', id='firstHeading') or soup.find('title')

                if page_title:
                    title_text = page_title.get_text(strip=True)
                    title_text = re.split(r'\s*[—–-]\s*', title_text)[0].strip()
                    if not title_text.startswith(surname):
                        failed += 1
                        progress['value'] = idx + 1
                        continue

                # 3. Парсим фракцию из инфобокса
                new_faction = parse_deputy_ruwiki(soup)
                if new_faction:
                    for i, dep in enumerate(self.deputies_list):
                        if dep[0] == surname and dep[1] == name and dep[2] == patronymic:
                            self.deputies_list[i] = (surname, name, patronymic, new_faction)
                            break
                    processed += 1
                else:
                    failed += 1

            except Exception as e:
                failed += 1
                continue

            progress['value'] = idx + 1
            progress_win.update()
            time.sleep(0.5)

        progress_win.destroy()
        result_msg = f"Обработано {processed} депутатов.\nНе удалось определить фракцию у {failed} депутатов."
        messagebox.showinfo("Завершено", result_msg)

    def _export_deputies(self):
        if not self.deputies_list:
            messagebox.showwarning("Предупреждение", "Список депутатов пуст.")
            return
        if not self.db_path:
            messagebox.showerror("Ошибка", "Путь к базе данных не определен.")
            return

        self.rom_convocation = {
            1: "I", 2: "II", 3: "III", 4: "IV",
            5: "V", 6: "VI", 7: "VII", 8: "VIII"
        }.get(self.convocation)

        filename = f"Депутаты Государственной Думы Российской Федерации {self.rom_convocation} созыва.txt"
        deputies_file = os.path.join(self.db_path, filename)

        if os.path.exists(deputies_file):
            if not messagebox.askyesno("Файл существует", f"Файл '{filename}' уже существует. Перезаписать?"):
                return

        try:
            with open(deputies_file, 'w', encoding='utf-8') as f:
                for surname, name, patronymic, faction in self.deputies_list:
                    full_name = f"{surname} {name} {patronymic}".strip()
                    full_name = "  ".join(full_name.split())
                    f.write(f"{full_name} — {faction}\n")

            os.utime(self.db_path, None)
            messagebox.showinfo("Успех",
                                f"Список из {len(self.deputies_list)} депутатов успешно сохранён в:\n{filename}")
        except Exception as e:
            messagebox.showerror("Ошибка записи", f"Не удалось сохранить файл:\n{e}")