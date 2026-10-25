"""Разбор ввода пользователя: дни недели и время."""
import re
from datetime import time

# (короткое имя, префикс полного названия) для дней: 0 = понедельник
_DAYS = [
    ("пн", "пон"),
    ("вт", "вто"),
    ("ср", "сре"),
    ("чт", "чет"),
    ("пт", "пят"),
    ("сб", "суб"),
    ("вс", "вос"),
]
DAY_NAMES = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def parse_days(text: str) -> list[int] | None:
    """'пн ср пт', 'вторник, четверг', 'будни', 'каждый день' -> [0, 2, 4].

    Возвращает None, если ничего не распознано.
    """
    text = text.lower()
    if any(w in text for w in ("каждый день", "ежедневно", "все дни")):
        return list(range(7))
    if "будни" in text:
        return [0, 1, 2, 3, 4]
    if "выходные" in text:
        return [5, 6]

    found = set()
    for token in re.findall(r"[а-яё]+", text):
        for index, (short, prefix) in enumerate(_DAYS):
            if token == short or token.startswith(prefix):
                found.add(index)
    return sorted(found) or None


def parse_time(text: str) -> time | None:
    """'18:30', '7.05', '9:00' -> datetime.time. Неверный ввод -> None."""
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def format_days(days: list[int]) -> str:
    if len(days) == 7:
        return "каждый день"
    return " ".join(DAY_NAMES[d] for d in sorted(days))
