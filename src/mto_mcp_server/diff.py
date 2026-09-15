"""diff_mto_scsa: the read-only comparison. No file writes happen here.

Returns a plain dict (JSON-serializable) so it works equally well as an
MCP tool result or a unit-test fixture.
"""
from __future__ import annotations

import math

from .io_excel import aggregate_mto, aggregate_scsa, load_mto, load_scsa

QTY_EPSILON = 1e-6  # float qty tolerance (pipe lengths are floats, in m)


def _clean_line(line):
    """pandas coerces None to NaN in float-typed columns; undo that for JSON."""
    if line is None or (isinstance(line, float) and math.isnan(line)):
        return None
    return line


def diff_mto_scsa(mto_path: str, scsa_path: str, category: str | None = None) -> dict:
    mto = aggregate_mto(load_mto(mto_path))
    scsa = aggregate_scsa(load_scsa(scsa_path))

    if category is not None:
        mto = mto[mto["category"] == category]
        scsa = scsa[scsa["category"] == category]

    mto_by_key = {row.match_key: row for row in mto.itertuples()}
    scsa_by_key = {row.match_key: row for row in scsa.itertuples()}

    all_keys = set(mto_by_key) | set(scsa_by_key)

    qty_mismatch, removed, new_items = [], [], []
    matched_count = 0

    for key in all_keys:
        in_mto = key in mto_by_key
        in_scsa = key in scsa_by_key

        if in_mto and in_scsa:
            m, s = mto_by_key[key], scsa_by_key[key]
            if abs(m.qty - s.qty) > QTY_EPSILON:
                qty_mismatch.append(
                    {
                        "key": _key_str(key),
                        "name": m.name,
                        "category": m.category,
                        "line": _clean_line(m.line),
                        "mto_qty": m.qty,
                        "scsa_qty": s.qty,
                        "mto_row_indices": m.row_indices,
                    }
                )
            else:
                matched_count += 1
        elif in_mto and not in_scsa:
            m = mto_by_key[key]
            removed.append(
                {
                    "key": _key_str(key),
                    "name": m.name,
                    "category": m.category,
                    "line": _clean_line(m.line),
                    "mto_qty": m.qty,
                    "mto_row_indices": m.row_indices,
                }
            )
        else:  # in_scsa and not in_mto
            s = scsa_by_key[key]
            new_items.append(
                {
                    "key": _key_str(key),
                    "name": s.name,
                    "category": s.category,
                    "line": _clean_line(s.line),
                    "scsa_qty": s.qty,
                }
            )

    qty_mismatch.sort(key=lambda r: (r["category"], r["name"]))
    removed.sort(key=lambda r: (r["category"], r["name"]))
    new_items.sort(key=lambda r: (r["category"], r["name"]))

    return {
        "category_filter": category,
        "summary": {
            "matched": matched_count,
            "qty_mismatch": len(qty_mismatch),
            "removed": len(removed),
            "new": len(new_items),
        },
        "qty_mismatch": qty_mismatch,
        "removed": removed,
        "new": new_items,
    }


def _key_str(key: tuple) -> str:
    """Human-readable rendering of an internal match key, for the report."""
    return " / ".join(str(part) for part in key)
