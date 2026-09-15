"""Domain-specific normalization add-ons, ported from
https://github.com/rustam-zarifov/mto-scsa-reconciliation (`4_normalization_addons.py`).

These are real production edge-case handlers from prior EPC reconciliation
work. NONE of these are currently wired into diff.py/matching.py - the demo
scope is elbow reconciliation only, and elbows don't hit any of these
cases. They're ported as-is (pure functions, no schema dependency) so
they're ready to plug in when gasket/pipe/flange matching gets built out,
instead of being rewritten from scratch later.
"""
from __future__ import annotations

import re
from collections import defaultdict

# ---- Gasket GOST-year normalization ------------------------------------
# SCSA wrote "ГОСТ 15180-1986"; MTO wrote "ГОСТ 15180-86". Without this,
# every gasket group looked like a mismatch.


def norm_gost_year(name: str) -> str:
    """Convert 'NNNNN-YYYY' (4-digit year) to 'NNNNN-YY' (last 2 digits)."""

    def repl(m):
        num, year = m.group(1), m.group(2)
        return f"{num}-{year[-2:]}"

    return re.sub(r"(\d{3,6})-(\d{4})\b", repl, name)


# ---- Material-code recovery from line ID --------------------------------
# Some SCSA rows had the gasket *material name* ("ТМКЩ") in the Материал
# column instead of the line-class code. The real code was still findable
# inside "Идентификатор номера линии", e.g. "LN-10003-25-C1A-NR" -> C1A.

KNOWN_LINE_CODES = ["S1C", "S1A", "C1A", "N1A", "L1A"]


def extract_code_from_lineid(line_id) -> str | None:
    """Search a line-ID string for one of the known material/line codes."""
    if not line_id:
        return None
    line_id = str(line_id).upper()
    for code in KNOWN_LINE_CODES:
        if code in line_id:
            return code
    return None


def resolve_material(material_cell, lineid_cell) -> str:
    """Return a usable material code: the cell itself if already a known
    code, otherwise recovered from the line ID, otherwise the raw text."""
    matu = str(material_cell).strip().upper() if material_cell else ""
    if matu in KNOWN_LINE_CODES:
        return matu
    code = extract_code_from_lineid(lineid_cell)
    return code or matu  # keep original text (e.g. 'ТМКЩ') if unresolved


# ---- OD -> DN lookup with tolerance (pipes & pipe-derived items) -------
# Russian pipe schedules give outer diameter (OD) in the item name; DN is
# the nominal bore. Table below is the standard GOST 8732-style mapping.
# A small tolerance handles source rounding (e.g. '160x5' meant DN150/OD159).

OD_TO_DN = {
    25: 20, 32: 25, 38: 32, 45: 40, 57: 50, 76: 65, 89: 80,
    108: 100, 133: 125, 159: 150, 219: 200, 273: 250, 325: 300,
    377: 350, 426: 400, 530: 500, 1024: 1000, 1228: 1200, 1432: 1400,
}


def get_dn_from_od(name: str, tolerance_mm: int = 15):
    """Return (dn, delta, method) for a pipe/flange name.

    Prefers an explicit 'DN###' token; otherwise reads the OD before the
    first 'x'/'х' and maps it to the nearest DN within `tolerance_mm`.
    """
    m = re.search(r"DN\s*(\d+)", name, re.IGNORECASE)
    if m:
        return int(m.group(1)), 0, "explicit DN"
    m2 = re.search(r"(\d+(?:[.,]\d+)?)\s*[xх]\s*\d", name)
    if not m2:
        return None, None, None
    od = round(float(m2.group(1).replace(",", ".")))
    if od in OD_TO_DN:
        return OD_TO_DN[od], 0, f"OD{od} exact"
    best_od, best_dn = min(OD_TO_DN.items(), key=lambda kv: abs(kv[0] - od))
    delta = abs(best_od - od)
    if delta <= tolerance_mm:
        return best_dn, delta, f"OD{od} approx (Δ{delta}mm)"
    return None, delta, f"OD{od} unresolved (Δ{delta}mm to nearest)"


# ---- Pipe "L = X м" segment vs. plain aggregate-length split -----------
# Large-diameter pipe rows are sometimes recorded per physical cut
# ("Труба DN1400 FRP, L = 2,522 м", unit='шт', qty=count of that cut)
# and sometimes as one aggregate length ("Труба ... DN1400 ...", unit='м').
# These need different comparison logic (segment count vs. summed length).


def strip_length_suffix(name: str) -> str:
    """Remove a ', L = X м' (and an added ', офланцованная с двух сторон'
    descriptor) so segments of the same pipe spec group under one base name."""
    name = re.sub(r",?\s*L\s*=\s*[\d.,]+\s*м\.?", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r",?\s*офланцованная\s+с\s+двух\s+сторон", "", name, flags=re.IGNORECASE
    )
    return name.strip()


def extract_L(name: str):
    """Pull the numeric L value (metres) out of a 'L = X м' fragment."""
    m = re.search(r"L\s*=\s*([\d.,]+)\s*м", name, re.IGNORECASE)
    return round(float(m.group(1).replace(",", ".")), 3) if m else None


def split_pipe_rows(mto_rows):
    """mto_rows: Pipe/Труба rows, each with name/qty/unit/note.

    Returns (segment_counts, plain_lengths):
    segment_counts: {(base_name, material, L): count_of_segments}
    plain_lengths: {(base_name, material): summed_length_m}

    A row only counts as a "segment" row when unit == 'шт' AND an L value
    is present - some legacy rows kept 'L = X м' in the text but were
    already aggregated under unit == 'м', and must be treated as plain.
    """
    segment_counts = defaultdict(int)
    plain_lengths = defaultdict(float)
    for row in mto_rows:
        name, qty, unit, material = row["name"], row["qty"] or 0, row["unit"], row["note"]
        unit_clean = str(unit).strip().lower()
        L = extract_L(name)
        base = strip_length_suffix(name)
        if L is not None and unit_clean == "шт":
            segment_counts[(base, material, L)] += qty
        else:
            plain_lengths[(base, material)] += qty
    return segment_counts, plain_lengths
