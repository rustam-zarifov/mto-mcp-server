"""Reading MTO and SCSA workbooks into tidy DataFrames.

Both files are read by COLUMN POSITION, not header name, because the real
SCSA export has no header row at all (row 1 is blank) and 50+ columns we
don't use. The maps below are verified against tests/fixtures/*.xlsx -
adjust the indices if your real exports differ.
"""
from __future__ import annotations

import pandas as pd

from .matching import get_match_key
from .normalize import classify_category, normalize_name

# 0-indexed column positions.
MTO_COLUMNS = {
    "poz": 0,
    "name": 1,
    "qty": 2,
    "unit": 3,
    "line": 4,
}

SCSA_COLUMNS = {
    "name": 0,
    "standard": 1,   # GOST / ASME - deliberately NOT part of the match key
    "line_code": 3,  # populated for some standards, empty for others
}


def load_mto(path: str, sheet_name=0) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    df = df.rename(columns={v: k for k, v in MTO_COLUMNS.items()})
    df = df[list(MTO_COLUMNS.keys())]
    df = df.dropna(subset=["name"]).copy()
    df["line"] = df["line"].where(df["line"].notna(), None)
    df["row_index"] = df.index  # 0-based openpyxl-agnostic row pointer
    df["category"] = df["name"].apply(classify_category)
    df["match_key"] = df.apply(
        lambda r: get_match_key(r["name"], r["category"], r["line"]), axis=1
    )
    return df


def load_scsa(path: str, sheet_name=0) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    name_col = SCSA_COLUMNS["name"]
    line_col = SCSA_COLUMNS["line_code"]
    out = pd.DataFrame(
        {
            "name": df[name_col],
            "line": df[line_col] if line_col in df.columns else None,
        }
    )
    out = out.dropna(subset=["name"]).copy()
    out["line"] = out["line"].where(out["line"].notna(), None)
    out["category"] = out["name"].apply(classify_category)
    out["match_key"] = out.apply(
        lambda r: get_match_key(r["name"], r["category"], r["line"]), axis=1
    )
    return out


def aggregate_mto(df: pd.DataFrame) -> pd.DataFrame:
    """Sum quantity per match_key (an item can appear on multiple MTO rows)."""
    grouped = (
        df.groupby("match_key")
        .agg(
            name=("name", "first"),
            line=("line", "first"),
            category=("category", "first"),
            qty=("qty", "sum"),
            row_indices=("row_index", list),
        )
        .reset_index()
    )
    return grouped


def aggregate_scsa(df: pd.DataFrame) -> pd.DataFrame:
    """Count physical instances per match_key (SCSA has no qty column)."""
    grouped = (
        df.groupby("match_key")
        .agg(
            name=("name", "first"),
            line=("line", "first"),
            category=("category", "first"),
            qty=("match_key", "count"),
        )
        .reset_index()
    )
    return grouped
