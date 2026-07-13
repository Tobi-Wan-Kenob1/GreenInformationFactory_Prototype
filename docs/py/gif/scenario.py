"""One-way scenario / sensitivity analysis.

Non-interactive port of ``05_scenario_analysis.ipynb``: vary one feature at a
time across a grid around a baseline row, predict with the best model, and
attach the three sustainability proxies for each point.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from helper.sustainability_metrics import (
    sustainability_v1,
    sustainability_pca_energy_index,
    sustainability_from_assumptions,
    pick_col,
)

_TIME = ["time_s", "time", "t", "Time"]
_TEMP = ["temperature", "temp", "T", "Temperature"]
_STIR = ["stirring", "Stirring", "stiring", "Stiring", "rpm", "RPM"]


def detect_scenario_vars(columns: Sequence[str]) -> List[str]:
    """Auto-detect time/temperature/stirring columns present in ``columns``.

    Uses the same tolerant matching as the sustainability proxies, so
    unit-suffixed columns (e.g. ``"Temperature (°C)"``) are detected.
    """
    df_like = pd.DataFrame(columns=list(columns))
    found: List[str] = []
    for cands in (_TIME, _TEMP, _STIR):
        col = pick_col(df_like, cands)
        if col is not None and col not in found:
            found.append(col)
    return found


def scenario_range(series: pd.Series, q_low: float = 0.10, q_high: float = 0.90) -> Tuple[float, float]:
    """Robust [low, high] range from quantiles, with min/max and [0,1] fallbacks."""
    s = pd.to_numeric(series, errors="coerce")
    lo, hi = float(s.quantile(q_low)), float(s.quantile(q_high))
    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-12:
        lo, hi = float(s.min()), float(s.max())
    if not np.isfinite(lo) or not np.isfinite(hi) or abs(hi - lo) < 1e-12:
        lo, hi = 0.0, 1.0
    return lo, hi


def build_grids(X_base: pd.DataFrame, scenario_vars: Sequence[str], grid_points: int = 25) -> Dict[str, np.ndarray]:
    """Build a 1-D linspace grid for each scenario variable."""
    return {v: np.linspace(*scenario_range(X_base[v]), grid_points) for v in scenario_vars}


def one_way_scenarios(baseline_row: pd.DataFrame, grid_1d: Dict[str, np.ndarray]) -> pd.DataFrame:
    """Expand a single baseline row into one-way perturbations along each var."""
    rows = []
    for var, values in grid_1d.items():
        for val in values:
            r = baseline_row.copy()
            r[var] = val
            r["_var"] = var
            r["_val"] = float(val)
            rows.append(r)
    return pd.concat(rows, ignore_index=True)


def run_scenarios(
    model,
    X_base: pd.DataFrame,
    *,
    scenario_vars: Optional[Sequence[str]] = None,
    baseline_idx: int = 0,
    grid_points: int = 25,
    feature_order: Optional[Sequence[str]] = None,
    assumptions_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Run the full one-way sweep and return a tidy results frame.

    Columns: ``_var, _val, y_pred, co2_v1, mci_v1, co2_pca, mci_pca`` and, if
    ``assumptions_path`` is given, ``co2_assumed, mci_assumed``.
    """
    if scenario_vars is None:
        scenario_vars = detect_scenario_vars(X_base.columns)
    if not scenario_vars:
        raise ValueError("No scenario variables found or provided.")

    cols = list(feature_order) if feature_order is not None else list(X_base.columns)
    baseline = X_base.iloc[[baseline_idx]].copy()
    grids = build_grids(X_base, scenario_vars, grid_points)
    scenarios = one_way_scenarios(baseline, grids)

    sc = scenarios.copy()
    sc["y_pred"] = model.predict(scenarios[cols])

    sc_v1, _ = sustainability_v1(sc, y_pred_col="y_pred")
    sc_pca, _ = sustainability_pca_energy_index(sc, y_pred_col="y_pred")

    out = sc[["_var", "_val", "y_pred"]].copy()
    out["co2_v1"] = sc_v1["co2_proxy"].to_numpy()
    out["mci_v1"] = sc_v1["mci_proxy"].to_numpy()
    out["co2_pca"] = sc_pca["co2_pca_proxy"].to_numpy()
    out["mci_pca"] = sc_pca["mci_pca_proxy"].to_numpy()

    if assumptions_path is not None:
        sc_assumed, _ = sustainability_from_assumptions(sc, assumptions_path, y_pred_col="y_pred")
        out["co2_assumed"] = sc_assumed["co2_assumed"].to_numpy()
        out["mci_assumed"] = sc_assumed["mci_assumed"].to_numpy()

    return out.reset_index(drop=True)
