from datetime import datetime
import json
import os
import shutil
from config import DEFAULTS_DIR, DEFAULTS_SETTINGS_FILE
from config import (
    GRAMS_FILE_NAME,
    FACTIONS_FILE_NAME,
    DEPUTIES_FILE_NAME,
    STOPWORDS_FILE_NAME,
    ABBREVIATIONS_FILE_NAME
)

def load_filter_state_from_disk(db_path: str) -> dict:
    """Читает состояние фильтров напрямую с диска."""
    filter_state = {}
    tabs = ['keywords', 'ngrams', 'deputies', 'factions']
    for tab in tabs:
        mode = False
        mode_file = os.path.join(db_path, f"{tab}_mode.state")
        if os.path.exists(mode_file):
            try:
                with open(mode_file, 'r', encoding='utf-8') as f:
                    mode = f.read().strip().lower() == 'true'
            except Exception: pass

        selected = set()
        bl_file = os.path.join(db_path, f"{tab}_blacklist.txt")
        if os.path.exists(bl_file):
            try:
                with open(bl_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            item = line.split('\t')[0]
                            # 🔹 НОРМАЛИЗАЦИЯ: для субъектов оставляем только ФИО, чтобы совпало с узлами графа
                            if tab == 'deputies' and ' — ' in item:
                                item = item.split(' — ')[0].strip()
                            selected.add(item)
            except Exception: pass

        filter_state[tab] = {"mode": mode, "selected": selected}
    return filter_state

def _ensure_defaults_dir():
    """Создаёт папку и файлы по умолчанию, если их нет."""
    if not os.path.exists(DEFAULTS_DIR):
        os.makedirs(DEFAULTS_DIR)
    # Создаём пустые файлы списков, если отсутствуют
    for fname in [GRAMS_FILE_NAME, FACTIONS_FILE_NAME, DEPUTIES_FILE_NAME, STOPWORDS_FILE_NAME, ABBREVIATIONS_FILE_NAME]:
        fpath = os.path.join(DEFAULTS_DIR, fname)
        if not os.path.exists(fpath):
            if fname == FACTIONS_FILE_NAME:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write("Фракция не определена\n")
            elif fname == ABBREVIATIONS_FILE_NAME:
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write("{}")
            else:
                open(fpath, 'w').close()

    # Файл общих настроек
    if not os.path.exists(DEFAULTS_SETTINGS_FILE):
        defaults = {
            "reg_date": datetime.now().strftime("%d.%m.%Y"),
            "use_device_time_reg_date": True,
            "default_faction": "Фракция не определена",
            "threshold": 0.5,
            "date_from": "21.02.1994",
            "date_to": datetime.now().strftime("%d.%m.%Y"),
            "use_device_time_date_to": True,
            "invert_period": False,
            "kw_conn": True,
            "viz_center_type": "Общий вид",
            "viz_center_node": ""
        }
        with open(DEFAULTS_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(defaults, f, ensure_ascii=False, indent=2)

def load_defaults_settings():
    _ensure_defaults_dir()
    try:
        with open(DEFAULTS_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def save_defaults_settings(data):
    _ensure_defaults_dir()
    with open(DEFAULTS_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def apply_defaults_to_new_db(db_path):
    """Копирует параметры по умолчанию в только что созданную БД."""
    _ensure_defaults_dir()

    # Копируем файлы списков
    for fname in ["grams.txt", "factions.txt", "deputies.txt", "stopwords.txt", "abbreviations.json"]:
        src = os.path.join(DEFAULTS_DIR, fname)
        dst = os.path.join(db_path, fname)
        if os.path.exists(src):
            shutil.copy2(src, dst)
        elif not os.path.exists(dst):
            open(dst, 'w').close()

    # 🔹 КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Загружаем настройки ДО условных блоков
    defaults = load_defaults_settings()

    # Применение параметров визуализации
    default_viz_path = os.path.join(DEFAULTS_DIR, ".viz_params.json")
    target_viz_path = os.path.join(db_path, ".viz_params.json")

    if os.path.exists(default_viz_path):
        shutil.copy2(default_viz_path, target_viz_path)
    else:
        viz_params = {
            "kw_conn": defaults.get("kw_conn", True),
            "center_type": defaults.get("viz_center_type", "Общий вид"),
            "center_node": defaults.get("viz_center_node", " "),
            "layout_type": "Сило-ориентированный",
            "node_colors": {"keyword": "#add8e6", "subject": "#90ee90", "faction": "#f08080"},
            "edge_colors": {"kw-kw": "#888888", "sub-fac": "#aa6666", "sub-kw": "#6688aa", "sub-sub": "#88aa88"},
            "font": {"size": 8, "color": "#000000", "weight": "normal"},
            "offsets": {"x": 0.05, "y": 0.05},
            "styles": {},
            "smart_labels": False,
            "label_base_radius": 0.035,
            "label_radius_multiplier": 0.003,
            "spacing_mode": "fixed",
            "spacing_fixed": 0.6,
            "spacing_dynamic_base": 0.4,
            "spacing_dynamic_factor": 0.015
        }
        with open(target_viz_path, 'w', encoding='utf-8') as f:
            json.dump(viz_params, f, ensure_ascii=False, indent=2)

    # Сохраняем порог и даты в состояние окна графа
    graph_state = {
        "threshold": defaults.get("threshold", 0.5),
        "date_from": defaults.get("date_from", "21.02.1994"),
        "date_to": datetime.now().strftime("%d.%m.%Y"),
        "invert_filter": defaults.get("invert_period", False),
        "show_kw_conn": defaults.get("kw_conn", True)
    }
    with open(os.path.join(db_path, ".graph_window_state.json"), 'w', encoding='utf-8') as f:
        json.dump(graph_state, f, ensure_ascii=False, indent=2)