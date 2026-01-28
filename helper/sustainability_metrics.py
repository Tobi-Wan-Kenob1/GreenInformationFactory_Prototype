# helper/sustainability_metrics.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Dict, Tuple
import numpy as np
import pandas as pd
import json
import re


def pick_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """Return first candidate column that exists in df."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def minmax01(x) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return x
    mn = np.nanmin(x)
    mx = np.nanmax(x)
    if not np.isfinite(mn) or not np.isfinite(mx) or abs(mx - mn) < 1e-12:
        return np.zeros_like(x, dtype=float)
    return (x - mn) / (mx - mn)


def sustainability_v1(
    df: pd.DataFrame,
    *,
    y_pred_col: str = "y_pred",
    time_candidates: Iterable[str] = ("time_s", "time", "t", "Time"),
    temp_candidates: Iterable[str] = ("temperature", "temp", "T", "Temperature"),
    stir_candidates: Iterable[str] = ("stiring", "Stiring", "stirring", "Stirring", "rpm", "RPM"),
    weights: Dict[str, float] = None,
) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    """
    Self-contained proxy sustainability metrics.

    Adds:
      - energy_proxy (0..1-ish)
      - co2_proxy    (0..1-ish)
      - mci_proxy    (0..1, higher=better)

    Returns:
      (out_df, drivers_used)
    """
    out = df.copy()
    weights = weights or {"time": 0.40, "temp": 0.40, "stir": 0.20}

    col_temp = pick_col(out, temp_candidates)
    col_time = pick_col(out, time_candidates)
    col_stir = pick_col(out, stir_candidates)

    temp = out[col_temp].to_numpy() if col_temp else np.zeros(len(out))
    time = out[col_time].to_numpy() if col_time else np.zeros(len(out))
    stir = out[col_stir].to_numpy() if col_stir else np.zeros(len(out))

    temp_n = minmax01(temp)
    time_n = minmax01(time)
    stir_n = minmax01(stir)

    ypred = out[y_pred_col].to_numpy(dtype=float)
    ypred_n = minmax01(ypred)

    out["energy_proxy"] = weights["time"] * time_n + weights["temp"] * temp_n + weights["stir"] * stir_n
    out["co2_proxy"] = 0.70 * out["energy_proxy"] + 0.30 * ypred_n
    out["mci_proxy"] = 1.0 - (0.60 * out["energy_proxy"] + 0.40 * ypred_n)
    out["mci_proxy"] = out["mci_proxy"].clip(0.0, 1.0)

    drivers_used = {"temperature": col_temp, "time": col_time, "stirring": col_stir}
    return out, drivers_used

from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

def sustainability_pca_energy_index(
    df: pd.DataFrame,
    *,
    feature_candidates: Iterable[str] = (
        "time_s", "time", "t",
        "temperature", "temp", "T",
        "stiring", "stirring", "rpm"
    ),
    y_pred_col: str = "y_pred",
):
    """
    PCA-based latent energy index proxy.
    - Uses PCA(1) if >=2 candidate numeric columns exist
    - Falls back to minmax(single_column) if only 1 exists
    - Falls back to zeros if none exist

    Adds:
      - energy_pca_proxy
      - co2_pca_proxy
      - mci_pca_proxy

    Returns:
      (out_df, info_dict)
    """
    out = df.copy()
    used_cols = [c for c in feature_candidates if c in out.columns]

    # predictions normalized
    ypred = out[y_pred_col].to_numpy(dtype=float)
    ypred_n = minmax01(ypred)

    info = {"used_columns": used_cols, "mode": None}

    if len(used_cols) >= 2:
        X = out[used_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)

        pca = PCA(n_components=1)
        pc1 = pca.fit_transform(Xs).ravel()

        energy = minmax01(pc1)

        info["mode"] = "pca"
        info["explained_variance_ratio"] = float(pca.explained_variance_ratio_[0])
        info["pca_components"] = pca.components_[0].tolist()

    elif len(used_cols) == 1:
        # Single-column fallback: scale that column to 0..1
        col = used_cols[0]
        x = pd.to_numeric(out[col], errors="coerce").fillna(0.0).to_numpy()
        energy = minmax01(x)

        info["mode"] = "single_column_fallback"
        info["fallback_column"] = col
        info["explained_variance_ratio"] = None
        info["pca_components"] = None

    else:
        # No usable columns: return zeros
        energy = np.zeros(len(out), dtype=float)

        info["mode"] = "no_columns_fallback"
        info["fallback_column"] = None
        info["explained_variance_ratio"] = None
        info["pca_components"] = None

    out["energy_pca_proxy"] = energy
    out["co2_pca_proxy"] = 0.7 * energy + 0.3 * ypred_n
    out["mci_pca_proxy"] = 1.0 - (0.6 * energy + 0.4 * ypred_n)
    out["mci_pca_proxy"] = out["mci_pca_proxy"].clip(0.0, 1.0)

    return out, info

# Assumption-based proxy

_ALLOWED_FUNCS = {
    "min": np.minimum,
    "max": np.maximum,
    "clip": np.clip,
    "abs": np.abs,
    "sqrt": np.sqrt,
    "log1p": np.log1p,
    "exp": np.exp,
}

_ALLOWED_NAMES = {"np"} | set(_ALLOWED_FUNCS.keys())

def _safe_eval_expr(expr: str, local_vars: dict) -> np.ndarray:
    """
    Very small safe expression evaluator:
    - Allows numpy arrays in local_vars (e.g., energy, y_pred, temperature)
    - Allows a few numpy-like functions: min/max/clip/abs/sqrt/log1p/exp
    - Disallows attribute access other than np.<something> by not exposing builtins
    """
    if "__" in expr:
        raise ValueError("Unsafe expression (double underscore) detected.")

    # Disallow imports, semicolons, etc.
    if re.search(r"(import|exec|eval|open|os\.|sys\.|subprocess|;)", expr):
        raise ValueError("Unsafe tokens detected in expression.")

    # Evaluate with no builtins
    return eval(expr, {"__builtins__": {}, "np": np, **_ALLOWED_FUNCS}, local_vars)


def sustainability_from_assumptions(
    df: pd.DataFrame,
    assumptions_path: str | Path,
    *,
    y_pred_col: str = "y_pred",
) -> tuple[pd.DataFrame, dict]:
    """
    Compute sustainability proxy metrics from a JSON assumptions file.

    JSON structure (example):
    {
      "drivers": {
        "time": ["time_s","time"],
        "temperature": ["temperature","temp"],
        "stirring": ["stirring","rpm"]
      },
      "energy": {
        "method": "weighted_sum",
        "weights": {"time": 0.4, "temperature": 0.4, "stirring": 0.2},
        "normalize": "minmax"
      },
      "metrics": {
        "co2": "0.7*energy + 0.3*y_pred_n",
        "mci": "clip(1 - (0.6*energy + 0.4*y_pred_n), 0, 1)"
      }
    }

    Returns:
      (out_df, info)
    """
    assumptions_path = Path(assumptions_path)
    if not assumptions_path.exists():
        raise FileNotFoundError(f"Assumptions JSON not found: {assumptions_path}")

    cfg = json.loads(assumptions_path.read_text(encoding="utf-8"))
    out = df.copy()

    # --- resolve driver columns ---
    drivers_cfg = cfg.get("drivers", {})
    resolved = {}
    for driver_name, candidates in drivers_cfg.items():
        if not isinstance(candidates, list):
            raise ValueError(f"drivers.{driver_name} must be a list of column candidates.")
        resolved[driver_name] = pick_col(out, candidates)

    # --- build driver arrays (missing drivers become zeros) ---
    driver_arrays = {}
    for k, col in resolved.items():
        if col is None:
            driver_arrays[k] = np.zeros(len(out), dtype=float)
        else:
            driver_arrays[k] = pd.to_numeric(out[col], errors="coerce").fillna(0.0).to_numpy(dtype=float)

    # --- energy computation ---
    energy_cfg = cfg.get("energy", {})
    method = energy_cfg.get("method", "weighted_sum")
    norm = energy_cfg.get("normalize", "minmax")

    if method != "weighted_sum":
        raise ValueError(f"Unsupported energy.method: {method}. Only 'weighted_sum' supported for now.")

    weights = energy_cfg.get("weights", {})
    if not weights:
        raise ValueError("energy.weights missing or empty.")

    energy = np.zeros(len(out), dtype=float)
    for k, w in weights.items():
        if k not in driver_arrays:
            raise ValueError(f"energy.weights refers to unknown driver '{k}'. Defined drivers: {list(driver_arrays.keys())}")
        energy += float(w) * driver_arrays[k]

    if norm == "minmax":
        energy = minmax01(energy)
    elif norm == "none":
        pass
    else:
        raise ValueError(f"Unsupported energy.normalize: {norm}")

    # --- normalize predictions for formulas ---
    y_pred = out[y_pred_col].to_numpy(dtype=float)
    y_pred_n = minmax01(y_pred)

    # expose variables to expression evaluation
    local_vars = {
        "energy": energy,
        "y_pred": y_pred,
        "y_pred_n": y_pred_n,
        **driver_arrays,  # e.g., time, temperature, stirring as arrays
    }

    # --- compute metrics from expressions ---
    metrics_cfg = cfg.get("metrics", {})
    if not metrics_cfg:
        raise ValueError("metrics section missing or empty in assumptions JSON.")

    out["energy_assumed"] = energy

    computed = {}
    for metric_name, expr in metrics_cfg.items():
        if not isinstance(expr, str):
            raise ValueError(f"metrics.{metric_name} must be a string expression.")
        out_col = f"{metric_name}_assumed"
        out[out_col] = _safe_eval_expr(expr, local_vars).astype(float)
        computed[metric_name] = {"expr": expr, "column": out_col}

    info = {
        "assumptions_file": str(assumptions_path),
        "resolved_driver_columns": resolved,
        "energy": {"method": method, "normalize": norm, "weights": weights},
        "computed_metrics": computed,
    }
    return out, info
