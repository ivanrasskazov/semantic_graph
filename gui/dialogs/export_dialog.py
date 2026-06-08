import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import csv
import shutil
import networkx as nx
from collections import defaultdict, Counter

from config import (
    LEXEMES_DIR_NAME, DEPUTIES_FILE_NAME,
    FACTIONS_FILE_NAME, GRAMS_FILE_NAME,
)

class ExportWindow:
    def __init__(self, parent, db_path):
        self.parent = parent
        self.db_path = db_path
        self.window = tk.Toplevel(parent)
        self.window.title("Экспорт данных")
        self.window.geometry("720x680")
        self.window.transient(parent)
        self.window.grab_set()

        folder_frame = ttk.Frame(self.window)
        folder_frame.pack(fill=tk.X, padx=10, pady=5)
        self.folder_label = ttk.Label(folder_frame, text="Папка: не выбрана")
        self.folder_label.pack(side=tk.TOP, anchor=tk.W)

        options_frame = ttk.LabelFrame(self.window, text="Выберите данные для экспорта:")
        options_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Удалили галочки: self.export_stats_var, self.export_edges_var, self.export_clusters_var
        self.export_ngrams_var = tk.BooleanVar()
        self.export_factions_var = tk.BooleanVar()
        self.export_deputies_var = tk.BooleanVar()
        self.export_stopwords_var = tk.BooleanVar()
        self.export_abbrev_var = tk.BooleanVar()

        # Удалили галочки: "Статистика по источникам", "Рёбра графа", "Кластеры"

        ttk.Checkbutton(options_frame, text="Список фракций", variable=self.export_factions_var).pack(anchor=tk.W,
                                                                                                      padx=10, pady=2)
        ttk.Checkbutton(options_frame, text="Список субъектов", variable=self.export_deputies_var).pack(anchor=tk.W,
                                                                                                        padx=10, pady=2)
        ttk.Checkbutton(options_frame, text="Список стоп-слов", variable=self.export_stopwords_var).pack(anchor=tk.W,
                                                                                                         padx=10,
                                                                                                         pady=2)
        ttk.Checkbutton(options_frame, text="Список N-грамм", variable=self.export_ngrams_var).pack(anchor=tk.W,
                                                                                                    padx=10, pady=2)
        ttk.Checkbutton(options_frame, text="Список обозначений", variable=self.export_abbrev_var).pack(anchor=tk.W,
                                                                                                        padx=10, pady=2)

        button_frame = ttk.Frame(self.window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(button_frame, text="Выбрать папку", command=self.select_output_dir).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Экспортировать", command=self.run_export).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

        self.output_dir = None

    def select_output_dir(self):
        self.output_dir = filedialog.askdirectory(title="Выберите папку для экспорта")
        if self.output_dir:
            self.folder_label.config(text=f"Папка: {self.output_dir}")
        else:
            self.folder_label.config(text="Папка: не выбрана")

    def run_export(self):
        if not self.output_dir:
            messagebox.showwarning("Экспорт", "Пожалуйста, выберите папку.")
            return

        errors = []
        # Удалили вызовы: self.export_source_stats()
        if self.export_ngrams_var.get():
            try:
                self.export_ngrams()
            except Exception as e:
                errors.append(f"N-граммы: {e}")
        if self.export_factions_var.get():
            try:
                self.export_factions()
            except Exception as e:
                errors.append(f"Фракции: {e}")
        if self.export_deputies_var.get():
            try:
                self.export_deputies()
            except Exception as e:
                errors.append(f"Субъекты: {e}")
        if self.export_stopwords_var.get():
            try:
                self.export_stopwords()
            except Exception as e:
                errors.append(f"Стоп-слова: {e}")
        if self.export_abbrev_var.get():
            try:
                self.export_abbreviations()
            except Exception as e:
                errors.append(f"Обозначения: {e}")

        if errors:
            messagebox.showerror("Ошибки", "\n".join(errors))
        else:
            messagebox.showinfo("Готово", f"Экспорт завершён в:\n{self.output_dir}")
            self.window.destroy()

    def export_source_stats(self):
        lexemes_dir = os.path.join(self.db_path, LEXEMES_DIR_NAME)
        csv_path = os.path.join(self.output_dir, "exported_source_stats.csv")
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Source_Name', 'Date', 'Token', 'Count'])
            idx = 1
            for fn in os.listdir(lexemes_dir):
                if fn.endswith('.json'):
                    try:
                        with open(os.path.join(lexemes_dir, fn), 'r', encoding='utf-8') as jf:
                            data = json.load(jf)
                        src_name = os.path.splitext(fn)[0]
                        date = data.get("date", "N/A")
                        tokens = data.get("tokens", {})
                        for token, cnt in tokens.items():
                            writer.writerow([idx, src_name, date, token, cnt])
                            idx += 1
                    except Exception as e:
                        continue
        print(f"Экспортировано: {csv_path}")

    def export_ngrams(self):
        ngrams_file_path = os.path.join(self.db_path, GRAMS_FILE_NAME)
        target_path = os.path.join(self.output_dir, "exported_ngrams.txt")
        if os.path.exists(ngrams_file_path):
            shutil.copy2(ngrams_file_path, target_path)
            print(f"Экспортировано: {target_path}")
        else:
            raise FileNotFoundError(f"Файл n-грамм {ngrams_file_path} не найден.")

    def export_factions(self):
        factions_file_path = os.path.join(self.db_path, FACTIONS_FILE_NAME)
        target_path = os.path.join(self.output_dir, "exported_factions.txt")
        if os.path.exists(factions_file_path):
            shutil.copy2(factions_file_path, target_path)
            print(f"Экспортировано: {target_path}")
        else:
            raise FileNotFoundError(f"Файл фракций {factions_file_path} не найден.")

    def export_deputies(self):
        deputies_file_path = os.path.join(self.db_path, DEPUTIES_FILE_NAME)
        target_path = os.path.join(self.output_dir, "exported_deputies.txt")
        if not os.path.exists(deputies_file_path):
            raise FileNotFoundError(f"Файл субъектов {deputies_file_path} не найден.")

        # Подгружаем кэш описаний на случай, если он не в TSV
        desc_cache = {}
        desc_file = os.path.join(self.db_path, "deputies_desc.json")
        if os.path.exists(desc_file):
            try:
                desc_cache = json.load(open(desc_file, 'r', encoding='utf-8'))
            except:
                pass

        with open(deputies_file_path, 'r', encoding='utf-8') as f_in, \
                open(target_path, 'w', encoding='utf-8') as f_out:
            for line in f_in:
                line = line.strip()
                if not line: continue
                parts = line.split('\t')
                if len(parts) < 4: continue

                surname, name, patronymic, raw_faction = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[
                    3].strip()
                full_name = f"{surname} {name} {patronymic}".strip() if name else surname
                faction, desc = (raw_faction.split('@', 1) if '@' in raw_faction else (raw_faction, ""))

                # Фоллбэк на JSON кэш
                if not desc.strip():
                    for key, val in desc_cache.items():
                        if full_name in key:
                            desc = val.strip()
                            break

                out_line = f"{full_name} — {faction}"
                if desc:
                    out_line += f" @{desc}"
                f_out.write(out_line + '\n')
        print(f"✅ Экспортировано: {target_path}")

    def export_stopwords(self):
        src = os.path.join(self.db_path, "stopwords.txt")
        target_path = os.path.join(self.output_dir, "exported_stopwords.txt")

        if not os.path.exists(src):
            raise FileNotFoundError("Файл стоп-слов не найден.")

        with open(src, 'r', encoding='utf-8') as f_in, \
                open(target_path, 'w', encoding='utf-8') as f_out:
            for line in f_in:
                line = line.strip()
                if not line:
                    continue
                # Преобразуем внутренний формат (табуляция) в читаемый вид
                if '\t' in line:
                    parts = line.split('\t', 1)
                    word, category = parts[0].strip(), parts[1].strip()
                    f_out.write(f"{word} — {category}\n")
                else:
                    # Если формат уже читаемый или слово без категории
                    f_out.write(f"{line} — Прочее\n")
        print(f"✅ Экспортировано: {target_path}")

    def export_abbreviations(self):
        src = os.path.join(self.db_path, "abbreviations.json")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(self.output_dir, "exported_abbreviations.json"))
        else:
            raise FileNotFoundError("Файл обозначений не найден.")

class StatsExportWindow:
    def __init__(self, parent, db_path):
        self.parent = parent; self.db_path = db_path
        self.window = tk.Toplevel(parent); self.window.title("Экспорт статистики"); self.window.geometry("500x450")
        self.window.transient(parent); self.window.grab_set();

        folder_frame = ttk.Frame(self.window); folder_frame.pack(fill=tk.X, padx=10, pady=10)
        self.folder_label = ttk.Label(folder_frame, text="Папка: не выбрана"); self.folder_label.pack(side=tk.TOP, anchor=tk.W)
        ttk.Button(folder_frame, text="Выбрать папку", command=self.select_output_dir).pack(side=tk.LEFT, padx=5)

        opts = ttk.LabelFrame(self.window, text="Что экспортировать?"); opts.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.v_tok = tk.BooleanVar(value=True); ttk.Checkbutton(opts, text="Экспортировать токены", variable=self.v_tok).pack(anchor=tk.W, padx=10, pady=2)
        self.v_clu = tk.BooleanVar(value=True); ttk.Checkbutton(opts, text="Экспортировать кластеры", variable=self.v_clu).pack(anchor=tk.W, padx=10, pady=2)
        self.v_act = tk.BooleanVar(value=True); ttk.Checkbutton(opts, text="Экспортировать активность субъектов", variable=self.v_act).pack(anchor=tk.W, padx=10, pady=2)
        self.v_met = tk.BooleanVar(value=True); ttk.Checkbutton(opts, text="Экспортировать метрики сети", variable=self.v_met).pack(anchor=tk.W, padx=10, pady=2)

        btn_frame = ttk.Frame(self.window); btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Экспортировать", command=self.run_export).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.window.destroy).pack(side=tk.RIGHT, padx=5)
        self.output_dir = None

    def select_output_dir(self):
        d = filedialog.askdirectory(title="Выберите папку для экспорта")
        if d: self.output_dir = d; self.folder_label.config(text=f"Папка: {d}")
        else: self.folder_label.config(text="Папка: не выбрана")

    def run_export(self):
        if not self.output_dir: messagebox.showwarning("Экспорт", "Выберите папку."); return
        errors = []
        if self.v_tok.get():
            try: self._export_tokens()
            except Exception as e: errors.append(f"Токены: {e}")
        if self.v_clu.get():
            try: self._export_clusters()
            except Exception as e: errors.append(f"Кластеры: {e}")
        if self.v_act.get():
            try: self._export_activity()
            except Exception as e: errors.append(f"Активность: {e}")
        if self.v_met.get():
            try: self._export_metrics()
            except Exception as e: errors.append(f"Метрики: {e}")
        if errors: messagebox.showerror("Ошибки", "\n".join(errors))
        else: messagebox.showinfo("Готово", f"Экспорт завершён в:\n{self.output_dir}")

    def _export_tokens(self):
        lex = os.path.join(self.db_path, "lexemes"); rows = []
        for fn in os.listdir(lex):
            if fn.endswith('.json'):
                with open(os.path.join(lex, fn), 'r', encoding='utf-8') as f: d = json.load(f)
                for tok, cnt in d.get("tokens", {}).items(): rows.append([os.path.splitext(fn)[0], tok, cnt])
        with open(os.path.join(self.output_dir, "tokens.csv"), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f); w.writerow(["Source", "Token", "Count"]); w.writerows(rows)

    def _export_clusters(self):
        g_path = os.path.join(self.db_path, "graph_data.json")
        if not os.path.exists(g_path): raise FileNotFoundError("Граф не построен.")
        with open(g_path, 'r', encoding='utf-8') as f: data = json.load(f)
        with open(os.path.join(self.output_dir, "clusters.csv"), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f); w.writerow(["Token", "Weight", "Type"]);
            w.writerows([[n["id"], n["weight"], n["type"]] for n in data["nodes"]])

    def _export_activity(self):
        lex = os.path.join(self.db_path, "lexemes"); deps = defaultdict(lambda: {"srcs": set(), "tokens": Counter()})
        for fn in os.listdir(lex):
            if fn.endswith('.json'):
                with open(os.path.join(lex, fn), 'r', encoding='utf-8') as f: d = json.load(f)
                for dep in d.get("deputies", []):
                    if " — " in dep:
                        name, fac = dep.split(" — ", 1); deps[name.strip()]["srcs"].add(fn); deps[name.strip()]["fac"] = fac.strip()
                        deps[name.strip()]["tokens"].update(d.get("tokens", {}))
        with open(os.path.join(self.output_dir, "deputy_activity.csv"), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f); w.writerow(["Name", "Faction", "Source_Count", "Total_Token_Weight"])
            for n, v in sorted(deps.items()): w.writerow([n, v.get("fac",""), len(v["srcs"]), sum(v["tokens"].values())])

    def _export_metrics(self):
        g_path = os.path.join(self.db_path, "graph_data.json")
        if not os.path.exists(g_path): raise FileNotFoundError("Граф не построен.")
        with open(g_path, 'r', encoding='utf-8') as f: data = json.load(f)
        G = nx.Graph()
        for n in data["nodes"]: G.add_node(n["id"], type=n["type"], weight=n["weight"])
        for e in data["edges"]: G.add_edge(e["source"], e["target"], weight=e["weight"])
        deg = nx.degree_centrality(G); bet = nx.betweenness_centrality(G, weight='weight')
        with open(os.path.join(self.output_dir, "network_metrics.csv"), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f); w.writerow(["Node", "Type", "Degree_Centrality", "Betweenness_Centrality", "Weight"])
            for n in G.nodes(): w.writerow([n, G.nodes[n].get("type",""), deg.get(n,0), bet.get(n,0), G.nodes[n].get("weight",0)])