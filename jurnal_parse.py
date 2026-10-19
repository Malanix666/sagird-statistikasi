"""Sürətli qeyd sətrinin Azərbaycan dilində oxunması.

Nümunələr:
    bu gün 5a filankesov filankes qaib
    dünən 7b məmmədova aysel 5
    12.10.2026 5a hamısı qaib
    əliyev, məmmədov qaib
"""

import difflib
import re
import unicodedata
from datetime import date, timedelta

_AZ = str.maketrans(
    {
        "ə": "e", "Ə": "e",
        "ı": "i", "İ": "i", "I": "i",
        "ö": "o", "Ö": "o",
        "ü": "u", "Ü": "u",
        "ç": "c", "Ç": "c",
        "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g",
    }
)

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./\-](\d{1,2})(?:[./\-](\d{2,4}))?(?!\d)")
_CLASS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*([a-p])(?![a-z0-9])")
_QAIB_RE = re.compile(r"\bqaib\b|\byox idi\b|\bgelmadi\b|\byoq\b|\bxeste\b|\bmovcud deyil\b")
_QVAL_RE = re.compile(r"\bqiymet[ie]?[nm]?\s*([1-5])\b|\b([1-5])\s*qiymet[ie]?[nm]?\b")
_GRADE_RE = re.compile(r"\b([1-5])\b")
_HAMISI_RE = re.compile(r"\bhamisi\b|\bhammisi\b|\bbutun\b|\bhepsi\b")
_SPLIT_RE = re.compile(r"\s*\bv[ea]\b\s*")
_REL = (("bu gun", 0), ("bugun", 0), ("dunen", -1), ("onceki gun", -1), ("sabah", 1))


def fold(s) -> str:
    """Kiçik hərf + Azərbaycan hərflərini latinə çevirir (ə→e, ı→i, ş→s ...)."""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.translate(_AZ).lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def _cut(text: str, match) -> str:
    return text[: match.start()] + " " + text[match.end() :]


def parse_command(text, default_sinif=None, today=None) -> dict:
    """Sətri parslayır. Qaytarır:
    {sinif, date, value, queries, whole_class, errors}
    """
    today = today or date.today()
    t = " " + text.strip() + " "
    # vergül / nöqtəli vergül / + adları ayıran kimi işləsin
    t = re.sub(r"[,;+]", " ve ", t)
    errors = []

    d = None
    m = _DATE_RE.search(t)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        ys = m.group(3)
        if not ys:
            year = today.year
        elif len(ys) == 2:
            year = 2000 + int(ys)
        else:
            year = int(ys)
        try:
            d = date(year, mon, day)
        except ValueError:
            errors.append("`%s` düzgün tarix deyil" % m.group(0).strip())
        t = _cut(t, m)

    f = fold(t)

    if d is None:
        for key, delta in _REL:
            pat = r"(?<![a-z])" + re.escape(key) + r"(?![a-z])"
            if re.search(pat, f):
                d = today + timedelta(days=delta)
                f = re.sub(pat, " ", f)
                break

    sinif = default_sinif
    m = _CLASS_RE.search(f)
    if m:
        sinif = m.group(1) + m.group(2)
        f = _cut(f, m)

    value = None
    mq, mqv = _QAIB_RE.search(f), _QVAL_RE.search(f)
    mg = None if mqv else _GRADE_RE.search(f)
    parts = []
    if mq:
        parts.append((mq.start(), "qaib", mq))
    if mqv:
        parts.append((mqv.start(), mqv.group(1) or mqv.group(2), mqv))
    elif mg:
        parts.append((mg.start(), mg.group(1), mg))
    if parts:
        parts.sort(key=lambda p: p[0])
        value, mval = parts[-1][1], parts[-1][2]
        f = _cut(f, mval)

    f = " ".join(f.split())
    whole = bool(_HAMISI_RE.search(f))
    if whole:
        f = " ".join(_HAMISI_RE.sub(" ", f).split())

    queries = [q.strip() for q in _SPLIT_RE.split(f) if q and q.strip()]

    return {
        "sinif": sinif,
        "date": d,
        "value": value,
        "queries": queries,
        "whole_class": whole,
        "errors": errors,
    }


def match_students(query, names) -> list:
    """Sorğuya uyğun şagirdlər (ən yaxşıdan)."""
    q = fold(query)
    if not q:
        return []
    qtok = q.split()
    scored = []
    for n in names:
        toks = fold(n).split()
        if not toks:
            continue
        if not all(any(c.startswith(x) or x.startswith(c) for c in toks) for x in qtok):
            continue
        core = toks[:2] if len(toks) >= 2 else toks
        exact = 2.0 if set(core) == set(qtok) else 0.0
        partial = sum(1.0 for x in qtok if x in core)
        scored.append((exact + partial + len(qtok) / 10.0, n))
    scored.sort(key=lambda p: (-p[0], p[1]))
    out = []
    for _, n in scored:
        if n not in out:
            out.append(n)
    return out


def closest(query, names, k=5) -> list:
    """Tapılmadıqda ən oxşar namizədlər."""
    q = fold(query)
    if not q:
        return []
    keys = {fold(n): n for n in names}
    hits = difflib.get_close_matches(q, list(keys), n=k, cutoff=0.45)
    return [keys[h] for h in hits]
