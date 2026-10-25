import sys
from datetime import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsing import format_days, parse_days, parse_time


def test_short_days():
    assert parse_days("пн ср пт") == [0, 2, 4]


def test_full_names_and_commas():
    assert parse_days("Вторник, четверг, воскресенье") == [1, 3, 6]


def test_groups():
    assert parse_days("будни") == [0, 1, 2, 3, 4]
    assert parse_days("выходные") == [5, 6]
    assert parse_days("каждый день") == list(range(7))


def test_days_garbage():
    assert parse_days("когда-нибудь") is None


def test_time_ok():
    assert parse_time("18:30") == time(18, 30)
    assert parse_time("7.05") == time(7, 5)


def test_time_bad():
    assert parse_time("25:00") is None
    assert parse_time("18:70") is None
    assert parse_time("вечером") is None


def test_format_days():
    assert format_days([4, 0, 2]) == "пн ср пт"
    assert format_days(list(range(7))) == "каждый день"
