import re
import os
import numpy as np
from collections import Counter, defaultdict
from sklearn.cluster import AgglomerativeClustering
from scipy.spatial.distance import cosine
from navec import Navec
from pymystem3 import Mystem
from config import NAVEC_MODEL_PATH, DEFAULTS_DIR
import threading
MYSTEM_LOCK = threading.Lock()

NAVEC_MODEL = None
MYSTEM_MODEL = None

_NGRAM_CACHE = None
_NGRAM_CACHE_MTIMES = {"grams": 0, "stopwords": 0}


def get_ngram_mapping(db_path):
    """
    Возвращает маппинг N-грамм с кэшированием.
    Пересчитывается только если изменились файлы справочников.
    """
    global _NGRAM_CACHE, _NGRAM_CACHE_MTIMES
    from config import GRAMS_FILE_NAME

    grams_path = os.path.join(db_path, GRAMS_FILE_NAME)
    stopwords_path = os.path.join(db_path, "stopwords.txt")

    # Получаем время модификации файлов (0 если не существует)
    grams_mtime = os.path.getmtime(grams_path) if os.path.exists(grams_path) else 0
    stopwords_mtime = os.path.getmtime(stopwords_path) if os.path.exists(stopwords_path) else 0

    # Проверяем валидность кэша
    if (_NGRAM_CACHE is not None and
            _NGRAM_CACHE_MTIMES.get('grams') == grams_mtime and
            _NGRAM_CACHE_MTIMES.get('stopwords') == stopwords_mtime):
        return _NGRAM_CACHE

    # Если кэш невалиден — пересчитываем
    n_grams = set()
    if os.path.exists(grams_path):
        with open(grams_path, 'r', encoding='utf-8') as f:
            n_grams = {line.strip() for line in f if line.strip()}

    stopwords = get_active_stopwords(db_path)
    _NGRAM_CACHE = preprocess_ngrams_mapping(n_grams, stopwords)

    # Обновляем метаданные кэша
    _NGRAM_CACHE_MTIMES['grams'] = grams_mtime
    _NGRAM_CACHE_MTIMES['stopwords'] = stopwords_mtime

    return _NGRAM_CACHE

def init_nlp_models():
    global NAVEC_MODEL, MYSTEM_MODEL

    try:
        NAVEC_MODEL = Navec.load(NAVEC_MODEL_PATH)
        print("Модель Navec загружена.")
    except Exception as e:
        print(f"Ошибка при загрузке Navec: {e}")
        NAVEC_MODEL = None

    try:
        MYSTEM_MODEL = Mystem()
        print("Mystem инициализирован (может потребовать время на первый запуск).")
    except Exception as e:
        print(f"Ошибка инициализации Mystem: {e}")
        MYSTEM_MODEL = None

def process_source_text_to_lemmas(text, ngram_mapping, stopwords_set=None):
    """Шаги 1-4: очистка -> лемматизация -> стоп-слова -> N-граммы (оптимизировано и безопасно)."""
    if not text or not MYSTEM_MODEL: return []

    # 1. Очистка
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\d', ' ', cleaned).strip()
    words = cleaned.split()
    if not words: return []

    # 🔹 РАЗБИЕНИЕ НА ЧАНКИ (чтобы не вешать процесс Mystem)
    chunk_size = 500
    chunks = [words[i: i + chunk_size] for i in range(0, len(words), chunk_size)]

    all_lemmas = []

    for chunk in chunks:
        chunk_text = ' '.join(chunk)

        # 🔹 БЛОКИРОВКА: только один поток может вызывать Mystem
        with MYSTEM_LOCK:
            try:
                lemmas_raw = MYSTEM_MODEL.lemmatize(chunk_text)
                # Извлекаем леммы (формат: слово\tлемма)
                for item in lemmas_raw:
                    if item.strip():
                        # Берем первую часть (оригинальное слово/лемма в зависимости от конфига)
                        lemma = item.split('\t')[0]
                        if lemma:
                            all_lemmas.append(lemma)
            except Exception as e:
                # Если Mystem упал на чанке, используем исходные слова как фоллбэк
                print(f"Warning: Mystem failed on chunk: {e}")
                all_lemmas.extend(chunk)

    # 3. Стоп-слова
    sw = stopwords_set if stopwords_set is not None else set()
    clean_lemmas = [l.strip().lower() for l in all_lemmas if l.strip().lower() not in sw and l.strip()]
    if not clean_lemmas: return []

    # 4. Оптимизированный поиск N-грамм (индексация по первому слову)
    ngram_starts = defaultdict(list)
    for ng in ngram_mapping.keys():
        ngram_starts[ng.split()[0]].append(ng)

    processed_tokens = []
    i = 0
    while i < len(clean_lemmas):
        found = False
        current_word = clean_lemmas[i]
        if current_word in ngram_starts:
            # Проверяем только кандидаты, начинающиеся с текущего слова
            for nk in sorted(ngram_starts[current_word], key=len, reverse=True):
                parts = nk.split()
                if i + len(parts) <= len(clean_lemmas) and clean_lemmas[i:i + len(parts)] == parts:
                    processed_tokens.append(ngram_mapping[nk][0])
                    i += len(parts)
                    found = True
                    break
        if not found:
            processed_tokens.append(current_word)
            i += 1
    return processed_tokens

def perform_clustering_and_restore(tokens_list, threshold=0.5, ngram_mapping=None):
    """Кластеризация + восстановление оригинальных форм + разрешение коллизий N-грамм."""
    if threshold <= 1e-5:
        return [ngram_mapping.get(t, [t])[0] for t in tokens_list] if ngram_mapping else tokens_list

    if not NAVEC_MODEL or len(tokens_list) < 2:
        return [ngram_mapping.get(t, [t])[0] for t in tokens_list] if ngram_mapping else tokens_list

    vectors, valid_tokens = [], []
    for t in tokens_list:
        if t in NAVEC_MODEL:
            vectors.append(NAVEC_MODEL[t])
            valid_tokens.append(t)

    if len(vectors) < 2:
        return [ngram_mapping.get(t, [t])[0] for t in tokens_list]

    X = np.array(vectors)
    dist_mat = np.zeros((len(X), len(X)))
    for i in range(len(X)):
        for j in range(i+1, len(X)):
            d = cosine(X[i], X[j])
            dist_mat[i, j] = d
            dist_mat[j, i] = d

    clustering = AgglomerativeClustering(n_clusters=None, linkage='average', metric='cosine', distance_threshold=threshold)
    labels = clustering.fit_predict(X)

    # Группировка и выбор "представителя" кластера (самое частотное)
    token_counts = Counter(tokens_list)
    rep_map = {}
    clusters = defaultdict(list)
    for t, lab in zip(valid_tokens, labels):
        clusters[lab].append(t)

    for members in clusters.values():
        best = max(members, key=lambda x: token_counts.get(x, 0))
        original = ngram_mapping.get(best, [best])[0]
        for m in members:
            rep_map[m] = original

    return [rep_map.get(t, ngram_mapping.get(t, [t])[0]) for t in tokens_list]

def preprocess_ngrams_mapping(ngrams_list, stopwords_set=None):
    """Преобразует список N-грамм до обработки БД: лемматизация + удаление стоп-слов.
    Возвращает dict: {processed_lemma_key: [original_ngram1, original_ngram2]}"""
    mapping = {}
    # Используем переданный набор, если он есть, иначе fallback на глобальный
    sw = stopwords_set if stopwords_set is not None else set()

    for ng in ngrams_list:
        cleaned = re.sub(r'[^\w\s]', '', ng.lower())
        cleaned = re.sub(r'\d+', '', cleaned).strip()
        if not cleaned: continue
        try:
            lemmas = MYSTEM_MODEL.lemmatize(cleaned) if MYSTEM_MODEL else [cleaned]
            lemmas = [l.split('\t')[0] for l in lemmas if l.strip()]
            filtered = [l.strip().lower() for l in lemmas if l.strip().lower() not in sw]
            processed_key = ' '.join(filtered)
        except:
            processed_key = cleaned.lower()
        if not processed_key: continue
        mapping.setdefault(processed_key, []).append(ng)
    return mapping

def remove_header(text):
    """
    Удаляет заголовок из текста.
    Заголовок определяется как текст от начала файла до ВТОРОГО вхождения кавычки.
    Поддерживаются обычные (") и "ёлочки" («»), "лапки" („“).
    Если таких кавычек меньше двух, возвращается исходный текст.
    """
    # Объединяем все виды кавычек в один список
    opening_quotes = {'"', '«', '„', '`'}  # Добавьте сюда другие открывающие, если нужно
    closing_quotes = {'"', '»', '"', "'"}  # Добавьте сюда другие закрывающие, если нужно

    all_quotes = opening_quotes.union(closing_quotes)

    quote_indices = []
    for i, char in enumerate(text):
        if char in all_quotes:
            quote_indices.append(i)
            # Нам нужно минимум 2 кавычки любого типа
            if len(quote_indices) == 2:
                # Возвращаем текст *после* второй кавычки
                # +1, чтобы не включать саму кавычку
                return text[quote_indices[1] + 1:]

    # Если не нашли 2 кавычки, возвращаем исходный текст
    return text

def get_active_stopwords(db_path):
    """Загружает стоп-слова из файла БД. Если файла нет, берет из настроек по умолчанию."""
    sw_file = os.path.join(db_path, "stopwords.txt")
    if os.path.exists(sw_file):
        try:
            with open(sw_file, 'r', encoding='utf-8') as f:
                return {line.split('\t')[0].strip().lower() for line in f if line.strip()}
        except:
            pass

    # Фоллбэк на дефолтные стоп-слова
    default_sw_file = os.path.join(DEFAULTS_DIR, "stopwords.txt")
    if os.path.exists(default_sw_file):
        try:
            with open(default_sw_file, 'r', encoding='utf-8') as f:
                return {line.split('\t')[0].strip().lower() for line in f if line.strip()}
        except:
            pass

    return set()