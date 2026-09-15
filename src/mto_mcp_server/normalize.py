"""Name normalization and category classification for piping items.

Normalization and the category keyword rules below are ported from
https://github.com/rustam-zarifov/mto-scsa-reconciliation (`3_compare_engine.py`'s
norm() and `1_extract_mto.py`'s categorize()) - real production logic from
actual EPC piping reconciliation work, not written fresh for this project.
Ported as name-only classification (the original categorize() also takes a
`section` argument, used only to catch an "Оборудование" (equipment) bucket
that doesn't apply to piping items - dropped here since it's irrelevant to
this tool and our raw MTO export has no section headers to track anyway).
"""
from __future__ import annotations

import re

# Category keyword rules, ported from categorize() in 1_extract_mto.py.
# Checked in this order - more specific / less ambiguous checks come first,
# matching the original's ordering rationale.
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("gasket", ["прокладк"]),
    ("blind_flange", ["заглушк"]),
    ("stud_bolt", ["шпильк"]),
    ("bolt", ["болт"]),
    ("nut", ["гайк"]),
    ("washer", ["шайб"]),
    ("gate_valve", ["задвижк"]),
    ("safety_valve", ["предохранительный клапан"]),
    ("valve", ["клапан", "затвор", "арматур"]),
    ("ball_valve", ["кран", "шаровый"]),
    ("steam_trap", ["конденсатоотводчик"]),
    ("flange", ["фланец", "фланц"]),
    ("reducer", ["переход"]),
    ("tee", ["тройник"]),
    ("elbow", ["отвод", "поворотная"]),
    ("pipe_support", ["u-образный", "y-образный", "опор"]),
    (
        "insulation",
        [
            "грунтовка",
            "эмаль",
            "теплоизоляция",
            "мат ",
            "лента",
            "стеклотекстилит",
            "фторопласт",
        ],
    ),
    ("structural_steel", ["двутавр", "лист", "пластина", "вкладыш"]),
    ("pipe", ["труба", "труб"]),
]

# Check-type valves are named inconsistently between "клапан" and "затвор"
# across exports/standards. When both items are check-type ("обратный"),
# treat the two words as synonyms. Do NOT do this generally - a plain
# "Клапан" and a plain "Затвор" are NOT the same thing.
_CHECK_VALVE_MARKER = "обратный"
_CHECK_VALVE_SYNONYMS = {"клапан": "клапан_затвор", "затвор": "клапан_затвор"}


def normalize_name(name) -> str:
    """Strip formatting noise that shouldn't affect matching.

    - drops the degree symbol (45° vs 45)
    - drops a trailing "?" (uncertain-tag marker some exports carry)
    - unifies Cyrillic "х" (U+0445) and Latin "x" - ported from norm() in
      3_compare_engine.py; a real bug source when dimension strings like
      "160x5" get typed with either character depending on export/locale
    - collapses repeated whitespace
    - trims
    """
    if name is None:
        return ""
    s = str(name)
    s = s.replace("\xb0", "").replace("°", "")
    s = s.replace("х", "x")  # Cyrillic х (U+0445) -> Latin x
    s = s.strip()
    if s.endswith("?"):
        s = s[:-1].strip()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def classify_category(name) -> str:
    """Best-effort category from the item name. Returns 'other' if unknown."""
    n = normalize_name(name).lower()
    if not n:
        return "blank"
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(kw in n for kw in keywords):
            return category
    return "other"


def canonicalize_valve_words(normalized_lower_name: str) -> str:
    """Map клапан/затвор to a shared token, but only for check-type items.

    Expects an already-normalized, already-lowercased name.
    """
    if _CHECK_VALVE_MARKER not in normalized_lower_name:
        return normalized_lower_name
    out = normalized_lower_name
    for word, canonical in _CHECK_VALVE_SYNONYMS.items():
        out = re.sub(rf"\b{word}\b", canonical, out)
    return out
