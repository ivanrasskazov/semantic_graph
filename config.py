import os

MAIN_FILE_NAME = "main"
SOURCES_DIR_NAME = "sources"
GRAMS_FILE_NAME = "grams.txt"
SOURCES_LIST_FILE_NAME = "sources_list.txt"
BLACKLIST_FILE_NAME = "blacklist.txt"
FACTIONS_FILE_NAME = "factions.txt"
DEPUTIES_FILE_NAME = "deputies.txt"
STOPWORDS_FILE_NAME = "stopwords.txt"
ABBREVIATIONS_FILE_NAME = "abbreviations.json"
LEXEMES_DIR_NAME = "lexemes"
GRAPH_DATA_DIR_NAME = "graph_data"
DOWNLOADS_DIR_NAME = "Downloads"
SOURCE_MAP_FILE = "source_map.json"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEXTDATA_DIR = os.path.join(SCRIPT_DIR, "data", "textdata")
DEFAULTS_DIR = os.path.join(TEXTDATA_DIR, "_defaults")
DEFAULTS_SETTINGS_FILE = os.path.join(DEFAULTS_DIR, "defaults.json")
MODELS_DIR = os.path.join(SCRIPT_DIR, "data", "models")
MODULES_DIR = os.path.join(SCRIPT_DIR, "data", "modules")

SYSTEM_FACTIONS = {
        "Сенатор Российской Федерации",
        "Федеральный СПЗИ",
        "Законодательный (представительный) орган",
        "Фракция не определена"
    }

NAVEC_MODEL_PATH = os.path.join(MODELS_DIR, "navec_hudlit_v1_12B_500K_300d_100q.tar")

os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(DEFAULTS_DIR, exist_ok=True)
os.makedirs(MODULES_DIR, exist_ok=True)