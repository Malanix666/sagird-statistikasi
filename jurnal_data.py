"""Dərs cədvəli və təqvim — formativ jurnal üçün məlumat."""

from datetime import date, timedelta

# İ gün = Bazar ertəsi ... V gün = Cümə (5 günlük həftə)
DAY_TO_WEEKDAY = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
DOW_AZ = ["B.e", "Ç.a", "Ç", "C.a", "C"]

# Məktəbin həftəlik cədvəli: sinif -> [(gün (I-V), dərs periodu), ...]
CEDEVEL = {
    "5a": [(1, 4), (5, 4)],
    "5b": [(1, 4), (5, 4)],
    "5c": [(5, 1), (1, 3)],
    "5d": [(5, 1), (2, 3)],
    "6a": [(5, 3), (2, 5)],
    "6b": [(5, 2), (2, 5)],
    "6c": [(5, 2), (2, 4)],
    "6d": [(2, 4), (4, 5)],
    "7a": [(1, 2), (5, 3)],
    "7b": [(1, 2), (5, 5)],
    "7c": [(3, 3), (1, 5)],
    "7d": [(4, 3), (1, 5)],
    "8a": [(5, 5), (4, 6)],
    "8b": [(1, 1), (3, 1)],
    "8c": [(1, 1), (3, 5)],
    "8d": [(2, 1), (4, 5)],
    "9a": [(2, 2), (4, 6)],
    "9b": [(2, 1), (3, 1)],
    "9c": [(2, 2), (4, 3)],
    "9d": [(4, 2), (3, 4)],
    "9e": [(3, 3), (4, 7)],
    "10a": [(4, 2), (2, 3)],
    "10b": [(4, 4), (3, 6)],
    "10p": [(3, 2), (1, 6)],
    "11a": [(4, 1), (5, 6)],
    "11b": [(1, 6), (3, 6)],
    "11c": [(3, 2), (5, 6)],
    "11p": [(3, 4), (2, 7)],
}

# Bayram / tətil günləri (təqvimdən) — bu tarixlərdə dərs işi yoxdur
TATIL = {
    date(2026, 11, 8),   # Zəfər Günü
    date(2026, 11, 9),   # Dövlət Bayrağı Günü
    date(2026, 11, 16),  # Payız tətili
    date(2026, 11, 17),
    date(2026, 11, 18),
    date(2026, 11, 19),
    date(2026, 11, 20),
    date(2026, 12, 31),  # Dünya Azərbaycanlılarının Həmrəyliyi Günü
}

SCHOOL_START = date(2026, 9, 15)
SCHOOL_END = date(2026, 12, 31)


def lesson_days(sinif):
    """Sinifin həftəlik dərsləri: [(gün, period), ...]."""
    return CEDEVEL.get(sinif, [])


def lesson_columns(sinif, start, end):
    """[start, end] aralığındakı hər dərs hadisəsi ayrıca sütun olaraq.

    Qaytarır: [(tarix, period), ...] — tarix artan, hətta eyni tarixdə
    iki dərs varsa period üzrə sıralı.
    """
    out = []
    for day, period in lesson_days(sinif):
        wd = DAY_TO_WEEKDAY[day]
        d = start
        while d <= end and d.weekday() != wd:
            d += timedelta(days=1)
        while d <= end:
            if d not in TATIL:
                out.append((d, period))
            d += timedelta(days=7)
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def class_sort_key(sinif):
    num = "".join(ch for ch in sinif if ch.isdigit())
    letter = "".join(ch for ch in sinif if not ch.isdigit())
    return (int(num or 0), letter)
