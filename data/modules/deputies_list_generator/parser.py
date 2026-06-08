from bs4 import BeautifulSoup
import re
import requests
from urllib.parse import quote


def parse_deputies_page(soup: BeautifulSoup) -> list[tuple[str, str, str, str]]:
    """Парсит страницу со списком депутатов duma.gov.ru."""
    deputies = []
    person_contents = soup.find_all('div', class_='person__content person__content--s')

    for content in person_contents:
        try:
            name_span = content.find('span', itemprop='name')
            if not name_span:
                continue

            surname_tag = name_span.find('strong')
            surname = surname_tag.get_text(strip=True) if surname_tag else ""

            second_name_span = name_span.find('span', class_='second-name')
            if second_name_span:
                second_name_text = second_name_span.get_text(strip=True)
                name_parts = second_name_text.split(maxsplit=1)
                name = name_parts[0] if len(name_parts) > 0 else ""
                patronymic = name_parts[1] if len(name_parts) > 1 else ""
            else:
                name = ""
                patronymic = ""

            if not surname:
                continue

            post_div = content.find('div', class_='person__post')
            faction = "Фракция не определена"

            if post_div:
                post_text = post_div.get_text(strip=True)
                quote_match = re.search(r'«([^»]+)»', post_text)
                if quote_match:
                    faction = quote_match.group(1).strip()
                elif "политической партией" in post_text:
                    party_idx = post_text.find("политической партией")
                    after_party = post_text[party_idx + len("политической партией"):]
                    faction = re.split(r'[<\n]', after_party)[0].strip(' "\'')

            deputies.append((surname, name, patronymic, faction))
        except Exception:
            continue
    return deputies


def parse_deputy_ruwiki(soup: BeautifulSoup) -> str | None:
    """
    Извлекает последнюю указанную партию со страницы депутата на ru.ruwiki.ru.
    """
    infobox = soup.find('table', class_=re.compile(r'infobox', re.I))
    if not infobox:
        return None

    party_values = []
    for row in infobox.find_all('tr'):
        header = row.find('th')
        if header and 'партия' in header.get_text(strip=True).lower():
            data_cell = row.find('td')
            if data_cell:
                raw_text = data_cell.get_text(separator=' ', strip=True)
                parties = re.split(r'[;\n]', raw_text)
                for p in parties:
                    p = p.strip()
                    if p and p.lower() not in ['неизвестно', 'нет данных', '—', '-']:
                        p = re.sub(r'\s*\[.*?\]', '', p).strip()
                        if p:
                            party_values.append(p)
    return party_values[-1] if party_values else None


def search_deputy_on_ruwiki(full_name: str) -> str | None:
    """
    Ищет статью депутата на ru.ruwiki.ru по ФИО.
    Возвращает URL статьи или None.
    """
    search_url = f"https://ru.ruwiki.ru/w/index.php?search={quote(full_name)}&title=Служебная:Поиск"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/wiki/' in href and not any(x in href for x in ['Служебная:', 'Обсуждение:', 'Файл:']):
                link_text = link.get_text(strip=True)
                surname = full_name.split()[0] if full_name.split() else ""
                if surname and (surname in link_text or surname in href):
                    if href.startswith('/'):
                        return f"https://ru.ruwiki.ru{href}"
                    return href
    except Exception:
        pass
    return None