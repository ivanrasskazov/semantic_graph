import re

def is_valid_db_name(name):
    if not name or not name.strip():
        return False, "Имя не может быть пустым."
    if re.search(r'[<>:"/\\|?*]', name):
        return False, "Имя содержит недопустимые символы: <, >, :, \", /, \\, |, ? или *."
    if len(name) > 50:
        return False, "Имя слишком длинное (максимум 50 символов)."
    return True, ""


def is_valid_source_name(name):
    if not name or not name.strip():
        return False, "Имя не может быть пустым."
    if re.search(r'[<>:"/\\|?*]', name):
        return False, "Имя содержит недопустимые символы."
    return True, ""

def sanitize_filename(name):
    # Удаляем все недопустимые символы для Windows и Unix
    # : * ? " < > | \ / — это запрещённые символы в Windows
    # Также удаляем конечные точки и пробелы
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', name)  # Удаляем основные запрещённые
    name = re.sub(r':', '', name)  # Явно удаляем двоеточие (частая причина)
    name = re.sub(r'\s+', '_', name)  # Заменяем последовательные пробелы на один _
    name = name.strip('._-')  # Убираем точки, подчёркивания, дефисы с начала и конца
    if not name:
        name = "unnamed"

    return name