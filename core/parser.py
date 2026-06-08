import re

def _extract_title_from_html_fixed(soup):
    """Извлекает полное название законопроекта из data-title атрибута #share_block."""
    # soup.find может не сработать из-за повреждённой структуры DOM
    # Ищем тег span с id="share_block" и атрибутом data-title вручную
    spans = soup.find_all('span', id="share_block")
    for span in spans:
        title_attr = span.get('data-title')
        if title_attr:
            return title_attr.strip()
    return "Название не найдено"

def parse_initiators_string(initiators_string):
    """
    Разбирает строку вида "Депутаты Государственной Думы И.О.Фамилия1, И.О.Фамилия2; Сенатор Российской Федерации И.О.Фамилия3"
    на список инициаторов: ['И.О.Фамилия1', 'И.О.Фамилия2', 'И.О.Фамилия3'].
    """
    if not initiators_string:
        return []

    # Шаг 1: Разделить по точке с запятой
    parts = [part.strip() for part in initiators_string.split(';')]

    all_initiators = []
    for part in parts:
        # Шаг 2: Удалить префиксы
        # Паттерн для поиска и удаления префикса
        # Он ищет: (Депутат(ы)? Государственной Думы) или (Сенатор(ы)? Российской Федерации) + пробел
        # и удаляет его, оставляя только имена
        # Регулярное выражение для поиска префикса
        prefix_pattern = r'^(?:Депутат(?:ы)?\s+Государственной\s+Думы|Сенатор(?:ы)?\s+Российской\s+Федерации)\s+'
        # Удаляем префикс из начала строки
        names_part = re.sub(prefix_pattern, '', part, flags=re.IGNORECASE).strip()

        # Шаг 3: Разделить по запятым
        if names_part:
            # Разделяем по запятым и убираем лишние пробелы
            initiators_in_part = [name.strip() for name in names_part.split(',')]
            # Добавляем к общему списку
            all_initiators.extend(initiators_in_part)

    # Шаг 4: Очистка от пустых строк (на всякий случай)
    all_initiators = [initiator for initiator in all_initiators if initiator]

    return all_initiators

def _extract_initiators_from_html_fixed(soup):
    """Извлекает список инициаторов из div.opch_r, чистит от префиксов и разбивает по запятым/точками с запятой."""
    opch_r = soup.find('div', class_='opch_r')
    if not opch_r:
        return []

    text = opch_r.get_text(strip=True)
    if not text:
        return []

    # Вызываем наш новый парсер
    return parse_initiators_string(text)

def _extract_registration_date_from_html_fixed(soup):
    """Ищет ПЕРВУЮ дату в формате ДД.ММ.ГГГГ внутри тега <span class="mob_not">."""
    # Находим первый тег <span class="mob_not">
    mob_not_span = soup.find('span', class_='mob_not')
    if mob_not_span:
        # Получаем его текстовое содержимое
        date_text = mob_not_span.get_text(strip=True)
        # Проверяем, соответствует ли оно формату ДД.ММ.ГГГГ
        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_text):
            return date_text  # Возвращаем найденную дату
    # Если не нашли, возвращаем None
    return None

def find_explanatory_note_link(soup):
    """
    Ищет ссылку на пояснительную записку.
    Ищет все вхождения "Пояснительная записка", затем проверяет формат файла.
    """
    explanatory_texts = soup.find_all(string=re.compile(r'Пояснительная записка'))

    for text_element in explanatory_texts:
        parent_a = text_element.find_parent('a', id=True, class_='a_event_files')
        if parent_a:
            # Найден тег <a> с текстом "Пояснительная записка"
            # Теперь ищем в обратном направлении по дереву до span.icon-file
            # Начинаем с тега, содержащего текст
            current = text_element.parent
            while current and current != parent_a:
                # Ищем span с классом, содержащим 'format-' и 'icon-file'
                possible_spans = current.find_all('span', class_=re.compile(r'format-.*icon-file'))
                for span in possible_spans:
                    class_str = span.get('class', [])
                    full_class = ' '.join(class_str)
                    if 'msword' in full_class:
                        href = parent_a.get('href')
                        if href:
                            return href
                current = current.parent

    # Если не нашли подходящих, возвращаем None
    return None