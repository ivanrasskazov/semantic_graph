# web/deputy_search_api.py
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import re

app = FastAPI(title="Deputy Search API", version="1.0")

# Разрешаем CORS для веб-интерфейса
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Deputy(BaseModel):
    surname: str
    name: str
    patronymic: Optional[str]
    faction: str
    convocation: Optional[int] = None

    @property
    def full_name(self) -> str:
        parts = [self.surname, self.name]
        if self.patronymic:
            parts.append(self.patronymic)
        return " ".join(parts)


class SearchResponse(BaseModel):
    total: int
    results: List[Deputy]
    query: str


# Глобальный кэш загруженных депутатов
_deputies_cache: List[Deputy] = []


def _load_deputies_from_file(db_path: str, convocation: Optional[int] = None) -> List[Deputy]:
    """Загружает депутатов из файла deputies.txt"""
    deputies = []
    filename = f"Депутаты Государственной Думы Российской Федерации {convocation} созыва.txt" if convocation else "deputies.txt"
    filepath = os.path.join(db_path, filename)

    if not os.path.exists(filepath):
        # Пробуем альтернативные имена файлов
        for alt_name in ["deputies.txt", "deputies_list.txt"]:
            alt_path = os.path.join(db_path, alt_name)
            if os.path.exists(alt_path):
                filepath = alt_path
                break
        else:
            return []

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or ' — ' not in line:
                continue
            # Формат: "Фамилия Имя Отчество — Фракция"
            name_part, faction = line.rsplit(' — ', 1)
            parts = name_part.strip().split()
            if len(parts) >= 2:
                deputy = Deputy(
                    surname=parts[0],
                    name=parts[1] if len(parts) > 1 else "",
                    patronymic=parts[2] if len(parts) > 2 else None,
                    faction=faction.strip(),
                    convocation=convocation
                )
                deputies.append(deputy)
    return deputies


def _normalize_text(text: str) -> str:
    """Нормализует текст для поиска: нижний регистр, удаление лишних пробелов"""
    return re.sub(r'\s+', ' ', text.lower().strip())


@app.on_event("startup")
async def startup_event():
    """Предзагрузка депутатов при старте (опционально)"""
    # Можно добавить логику загрузки из конфигурации
    pass


@app.get("/api/deputies", response_model=SearchResponse)
async def search_deputies(
        q: str = Query(default="", description="Поисковый запрос (ФИО или фракция)"),
        faction: Optional[str] = Query(default=None, description="Фильтр по фракции"),
        convocation: Optional[int] = Query(default=None, ge=1, le=8, description="Номер созыва (1-8)"),
        limit: int = Query(default=50, ge=1, le=200, description="Максимум результатов"),
        db_path: Optional[str] = Query(default=None, description="Путь к базе данных")
):
    """
    Поиск депутатов по ФИО и/или фракции.
    """
    global _deputies_cache

    # Загружаем депутатов, если кэш пуст или изменён путь к БД
    if not _deputies_cache or (db_path and not any(d.convocation == convocation for d in _deputies_cache)):
        if db_path:
            _deputies_cache = _load_deputies_from_file(db_path, convocation)
        else:
            # По умолчанию ищем в текущей директории
            _deputies_cache = _load_deputies_from_file(".", convocation)

    # Фильтрация
    results = _deputies_cache

    if q:
        query_norm = _normalize_text(q)
        results = [
            d for d in results
            if query_norm in _normalize_text(d.full_name) or query_norm in _normalize_text(d.faction)
        ]

    if faction:
        faction_norm = _normalize_text(faction)
        results = [d for d in results if faction_norm in _normalize_text(d.faction)]

    # Сортировка: сначала точные совпадения, потом по фамилии
    if q:
        query_norm = _normalize_text(q)

        def sort_key(d):
            name_match = _normalize_text(d.full_name) == query_norm
            faction_match = _normalize_text(d.faction) == query_norm
            return (not (name_match or faction_match), d.surname.lower())

        results = sorted(results, key=sort_key)
    else:
        results = sorted(results, key=lambda d: d.surname.lower())

    return SearchResponse(
        total=len(results),
        results=results[:limit],
        query=q
    )


@app.get("/api/deputies/{deputy_id}")
async def get_deputy(deputy_id: str, db_path: Optional[str] = None):
    """Получение депутата по уникальному ID (surname+name+convocation)"""
    # deputy_id формат: "surname_name_convocation" или хеш
    global _deputies_cache
    if not _deputies_cache and db_path:
        _deputies_cache = _load_deputies_from_file(db_path)

    for deputy in _deputies_cache:
        dep_id = f"{deputy.surname}_{deputy.name}_{deputy.convocation or 'unknown'}".lower()
        if dep_id == deputy_id.lower():
            return deputy
    raise HTTPException(status_code=404, detail="Депутат не найден")


@app.get("/api/factions")
async def get_factions(db_path: Optional[str] = None):
    """Получение списка уникальных фракций"""
    global _deputies_cache
    if not _deputies_cache and db_path:
        _deputies_cache = _load_deputies_from_file(db_path)

    factions = sorted(set(d.faction for d in _deputies_cache if d.faction))
    return {"factions": factions, "total": len(factions)}