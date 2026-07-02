"""Data loading, cleaning, splitting and validation.

This module is the non-interactive counterpart of ``02_prepare_data.ipynb``.
The notebook relied on ``input()`` prompts to pick columns, which makes the
pipeline impossible to run in CI or reproduce unattended. Here the same logic
is exposed as pure functions that take explicit column selections (typically
sourced from the config or CLI flags).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

# Filenames written / read for each split.
SPLIT_FILES: Dict[str, Tuple[str, str]] = {
    "Train": ("X_train.csv", "y_train.csv"),
    "Test": ("X_test.csv", "y_test.csv"),
    "Validation": ("X_val.csv", "y_val.csv"),
}

# Fallback candidates used when reading a split that may have been produced by
# the older BioFairNet naming scheme.
_X_CANDIDATES = [
    "X_train.csv", "X_test.csv", "X_val.csv", "X_validation.csv",
    "BioFairNet_Pilot1_Testrun_Train_in.csv",
    "BioFairNet_Pilot1_Testrun_Test_in.csv",
]
_Y_CANDIDATES = [
    "y_train.csv", "y_test.csv", "y_val.csv", "y_validation.csv",
    "BioFairNet_Pilot1_Testrun_Train_out.csv",
    "BioFairNet_Pilot1_Testrun_Test_out.csv",
]


@dataclass
class PreparedData:
    """Result of :func:`prepare_data`."""

    df: pd.DataFrame
    features: List[str]
    target: str
    X_train: pd.DataFrame
    X_test: pd.DataFrame
    X_val: pd.DataFrame
    y_train: pd.Series
    y_test: pd.Series
    y_val: pd.Series
    report: Dict[str, object] = field(default_factory=dict)


def load_raw(path: Path, sep: str = ";", encoding: str = "utf-8") -> pd.DataFrame:
    """Read the raw CSV and strip whitespace from column names."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {path}")
    df = pd.read_csv(path, sep=sep, encoding=encoding)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def resolve_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[str]:
    """Return the first candidate present in ``df`` (exact match)."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    """Coerce a column to float, accepting comma decimal separators."""
    return pd.to_numeric(
        series.astype(str).str.strip().str.replace(",", ".", regex=False),
        errors="coerce",
    )


def time_to_seconds(series: pd.Series, default_dt: float = 15.0) -> pd.Series:
    """Convert an ``hh:mm:ss`` / ``mm:ss`` time column to elapsed seconds.

    Rebuilds a monotonically increasing series starting at 0, using the median
    positive step to fill gaps/resets — a faithful port of the notebook logic.
    """
    s = series.astype(str).str.strip()
    t = pd.to_timedelta(s, errors="coerce")
    na_ratio = float(t.isna().mean())
    if na_ratio > 0.95:
        bad = s[t.isna()].head(10).tolist()
        raise ValueError(
            f"Time parsing failed for >95% of rows. Examples: {bad}"
        )
    t_sec = t.dt.total_seconds()
    dt = t_sec.diff()
    dt = dt.where(dt > 0)  # drop wraps/resets
    med = dt.dropna().median()
    if pd.isna(med) or med <= 0:
        med = default_dt
    dt = dt.fillna(med)
    if len(dt) > 0:
        dt.iloc[0] = 0.0
    else:
        dt = pd.Series([0.0])
    return dt.cumsum().astype(float)


def prepare_data(
    df: pd.DataFrame,
    *,
    feature_cols: Sequence[str],
    target_col: str,
    time_col: Optional[str] = None,
    holdout_fraction: float = 0.2,
    train_fraction_within_train: float = 0.8,
    random_seed: int = 42,
) -> PreparedData:
    """Clean and split a raw dataframe.

    - If ``time_col`` is given it is converted to a ``time_s`` feature and the
      original string column is dropped.
    - Feature/target columns are coerced to numeric (comma decimals allowed).
    - Rows with a NaN target, or with *all* features NaN, are dropped.
    - Splits: holdout (val) first, then an inner train/test split.
    """
    missing = [c for c in [*feature_cols, target_col, *( [time_col] if time_col else [] )] if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in data: {missing}. Available: {list(df.columns)}")

    features = list(feature_cols)
    work = df[([time_col] if time_col else []) + features + [target_col]].copy()

    if time_col:
        work["time_s"] = time_to_seconds(work[time_col])
        work = work.drop(columns=[time_col])
        features = ["time_s"] + [c for c in features if c != time_col]

    for col in features + [target_col]:
        work[col] = _to_numeric(work[col])

    n_before = len(work)
    work = work.dropna(subset=[target_col])
    work = work.dropna(subset=features, how="all")
    work = work.reset_index(drop=True)

    X = work[features]
    y = work[target_col]

    X_train_full, X_val, y_train_full, y_val = train_test_split(
        X, y, test_size=holdout_fraction, random_state=random_seed
    )
    X_train, X_test, y_train, y_test = train_test_split(
        X_train_full, y_train_full,
        test_size=1 - train_fraction_within_train, random_state=random_seed,
    )

    report = {
        "rows_before_clean": int(n_before),
        "rows_after_clean": int(len(work)),
        "rows_dropped": int(n_before - len(work)),
        "features": features,
        "target": target_col,
        "splits": {"train": len(X_train), "test": len(X_test), "validation": len(X_val)},
    }
    return PreparedData(
        df=work, features=features, target=target_col,
        X_train=X_train, X_test=X_test, X_val=X_val,
        y_train=y_train, y_test=y_test, y_val=y_val, report=report,
    )


def save_splits(prepared: PreparedData, processed_dir: Path) -> Dict[str, Path]:
    """Write the six split CSVs under ``processed_dir/<Split>/``."""
    processed_dir = Path(processed_dir)
    written: Dict[str, Path] = {}
    parts = {
        "Train": (prepared.X_train, prepared.y_train),
        "Test": (prepared.X_test, prepared.y_test),
        "Validation": (prepared.X_val, prepared.y_val),
    }
    for split, (X, y) in parts.items():
        xname, yname = SPLIT_FILES[split]
        sdir = processed_dir / split
        sdir.mkdir(parents=True, exist_ok=True)
        X.to_csv(sdir / xname, index=False)
        y.to_csv(sdir / yname, index=False)
        written[f"X_{split.lower()}"] = sdir / xname
        written[f"y_{split.lower()}"] = sdir / yname
    return written


def load_split(
    processed_dir: Path,
    split_name: str,
    x_candidates: Optional[Sequence[str]] = None,
    y_candidates: Optional[Sequence[str]] = None,
) -> Tuple[pd.DataFrame, pd.Series, str, str]:
    """Load an X/y split, tolerating alternative filenames.

    ``split_name`` may be ``"Validation"`` or the legacy ``"Val"``.
    """
    processed_dir = Path(processed_dir)
    split_dir = processed_dir / split_name
    if not split_dir.exists() and split_name == "Validation":
        split_dir = processed_dir / "Val"
    if not split_dir.exists():
        raise FileNotFoundError(f"Split folder not found: {split_dir}")

    xc = list(x_candidates) if x_candidates else _X_CANDIDATES
    yc = list(y_candidates) if y_candidates else _Y_CANDIDATES
    x_path = next((split_dir / f for f in xc if (split_dir / f).exists()), None)
    y_path = next((split_dir / f for f in yc if (split_dir / f).exists()), None)
    if x_path is None or y_path is None:
        found = [p.name for p in split_dir.glob("*.csv")]
        raise FileNotFoundError(
            f"Could not find X/y files in {split_dir}. Found: {found}"
        )
    X = pd.read_csv(x_path)
    y = pd.read_csv(y_path).squeeze("columns")
    return X, y, x_path.name, y_path.name


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate_raw(
    df: pd.DataFrame,
    *,
    required_columns: Sequence[str] = (),
    min_rows: int = 1,
) -> List[str]:
    """Return a list of human-readable problems with a raw dataframe.

    Empty list == valid. Never raises; callers decide how strict to be.
    """
    problems: List[str] = []
    if len(df) < min_rows:
        problems.append(f"Too few rows: {len(df)} < {min_rows}.")
    for col in required_columns:
        if col not in df.columns:
            problems.append(f"Missing required column: {col!r}.")
    if df.columns.duplicated().any():
        dups = df.columns[df.columns.duplicated()].tolist()
        problems.append(f"Duplicate column names: {dups}.")
    if df.dropna(how="all").empty:
        problems.append("All rows are entirely empty.")
    return problems


def validate_prepared(prepared: PreparedData) -> List[str]:
    """Return a list of problems with a prepared/split dataset."""
    problems: List[str] = []
    if prepared.df.empty:
        problems.append("Prepared frame is empty after cleaning.")
    for name, X in (("train", prepared.X_train), ("test", prepared.X_test), ("val", prepared.X_val)):
        if len(X) == 0:
            problems.append(f"Empty {name} split.")
    if prepared.y_train.isna().any() or prepared.y_test.isna().any() or prepared.y_val.isna().any():
        problems.append("Target contains NaN after cleaning.")
    if not prepared.features:
        problems.append("No feature columns selected.")
    return problems
