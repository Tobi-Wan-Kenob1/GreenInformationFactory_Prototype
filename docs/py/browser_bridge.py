"""Bridge between docs/run.html (JavaScript) and the real pipeline modules.

Runs inside Pyodide. Every function takes/returns JSON strings so the JS side
stays a thin UI layer; all detection logic reuses the actual ``gif`` /
``helper`` code so the browser demo behaves exactly like the CLI.

Phase A scope: format sniffing + column-role suggestion + data preview.
The pipeline execution entry points arrive in Phase B.
"""
from __future__ import annotations

import io
import json

import pandas as pd

from gif.data import resolve_column
from helper.sustainability_metrics import normalize_colname

#: Candidate names for each column role — the same lists the pipeline uses
#: (gif.pipeline._resolve_feature_target / helper.sustainability_metrics).
ROLE_CANDIDATES = {
    "time": ["time_s", "time", "t", "Time", "Time (min)", "timestamp"],
    "temperature": ["temperature", "temp", "T", "Temperature"],
    "stirring": ["stirring", "Stirring", "stiring", "Stiring", "rpm", "RPM"],
    "target": ["pressure", "Pressure", "yield", "Yield", "output", "conversion"],
}

_SEPARATORS = [";", ",", "\t", "|"]


def _sniff_separator(text: str) -> str:
    """Pick the separator that yields the most (and consistent) columns."""
    lines = [l for l in text.splitlines()[:20] if l.strip()]
    best, best_score = ";", 0
    for sep in _SEPARATORS:
        counts = [line.count(sep) for line in lines]
        if not counts or min(counts) == 0:
            continue
        # consistent column count across lines scores higher
        score = min(counts) * (2 if len(set(counts)) == 1 else 1)
        if score > best_score:
            best, best_score = sep, score
    return best


def _numeric_ratio(series: pd.Series) -> float:
    """Fraction of values that parse as numbers (comma decimals allowed)."""
    s = series.astype(str).str.strip().str.replace(",", ".", regex=False)
    return float(pd.to_numeric(s, errors="coerce").notna().mean())


def _looks_like_time(series: pd.Series) -> bool:
    s = series.astype(str).str.strip()
    return bool(pd.to_timedelta(s, errors="coerce").notna().mean() > 0.8)


def _decimal_style(df: pd.DataFrame) -> str:
    sample = df.astype(str).head(200).to_string()
    commas = sum(1 for _ in __import__("re").finditer(r"\d,\d", sample))
    dots = sum(1 for _ in __import__("re").finditer(r"\d\.\d", sample))
    return "comma" if commas > dots else "dot"


def sniff_and_preview(csv_text: str) -> str:
    """Analyze an uploaded delimited text file.

    Returns JSON with: separator, decimal style, row/column counts, a small
    preview, and a per-column analysis including the suggested role
    (``time`` / ``feature`` / ``target`` / ``ignore``) plus whether that
    suggestion came from name matching (the pipeline's candidate lists) or
    from content heuristics.
    """
    # strip a BOM if present (the pilot CSV has one)
    csv_text = csv_text.lstrip("﻿")
    sep = _sniff_separator(csv_text)
    df = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]

    # role suggestions by name first (same matching as the pipeline: exact,
    # then case/unit-suffix tolerant via normalize_colname)
    assigned: dict[str, str] = {}
    matched_by_name: set = set()
    for role in ("time", "temperature", "stirring", "target"):
        col = resolve_column(df, ROLE_CANDIDATES[role])
        if col is None:
            norm_map = {normalize_colname(c): c for c in df.columns}
            for cand in ROLE_CANDIDATES[role]:
                hit = norm_map.get(normalize_colname(cand))
                if hit is not None:
                    col = hit
                    break
        if col is not None and col not in assigned:
            assigned[col] = "target" if role == "target" else (
                "time" if role == "time" else "feature")
            matched_by_name.add(col)

    columns = []
    numeric_cols = []
    for col in df.columns:
        ratio = _numeric_ratio(df[col])
        is_time = col not in assigned and _looks_like_time(df[col])
        if col in assigned:
            role = assigned[col]
        elif is_time:
            role = "time"
        elif ratio > 0.5:
            # mostly-numeric columns are suggested as features even when some
            # values fail to parse — the warning below flags the bad rows and
            # the user can still switch the role to "ignore".
            role = "feature"
            numeric_cols.append(col)
        else:
            role = "ignore"
        columns.append({
            "name": col,
            "suggested_role": role,
            "matched_by_name": col in matched_by_name,
            "numeric_ratio": round(ratio, 3),
            "sample": df[col].head(3).tolist(),
        })

    # if no target was matched by name, promote the last numeric column —
    # flagged as a guess so the UI can require confirmation
    target_guessed = False
    if not any(c["suggested_role"] == "target" for c in columns):
        if numeric_cols:
            for c in columns:
                if c["name"] == numeric_cols[-1]:
                    c["suggested_role"] = "target"
                    target_guessed = True

    result = {
        "separator": sep,
        "decimal": _decimal_style(df),
        "n_rows": int(len(df)),
        "n_cols": int(len(df.columns)),
        "preview": df.head(5).to_dict(orient="records"),
        "columns": columns,
        "target_guessed": target_guessed,
        "warnings": _warnings(df, columns),
    }
    return json.dumps(result)


def _warnings(df: pd.DataFrame, columns: list) -> list:
    w = []
    if len(df) < 100:
        w.append(f"Only {len(df)} rows — models will be unreliable below a few hundred rows.")
    n_feat = sum(1 for c in columns if c["suggested_role"] == "feature")
    if n_feat == 0:
        w.append("No numeric feature columns detected — check the separator and decimal settings.")
    low = [c["name"] for c in columns
           if c["suggested_role"] in ("feature", "target") and c["numeric_ratio"] < 0.95]
    if low:
        w.append(f"Columns with unparseable values (will become gaps): {', '.join(low)}.")
    return w


def runtime_info() -> str:
    """Versions of the loaded scientific stack, for the page footer."""
    import sys

    import numpy
    import sklearn

    import gif

    return json.dumps({
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "pandas": pd.__version__,
        "sklearn": sklearn.__version__,
        "gif": gif.__version__,
    })
