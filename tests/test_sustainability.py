"""Tests for helper.sustainability_metrics, incl. the new eco-efficiency proxy."""
import json

import numpy as np
import pandas as pd
import pytest

from helper.sustainability_metrics import (
    minmax01, pick_col,
    sustainability_v1, sustainability_pca_energy_index,
    sustainability_from_assumptions, sustainability_eco_efficiency,
    _safe_eval_expr,
)


# NOTE: uses the canonical lowercase driver names that the proxy candidate
# lists in helper.sustainability_metrics actually recognize. The real processed
# data uses unit-suffixed names ("Temperature (°C)") that these lists do NOT
# match — see the mismatch flagged separately in the review notes.
def _df(n=50, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "time_s": rng.uniform(0, 1000, n),
        "temperature": rng.uniform(20, 250, n),
        "stiring": rng.uniform(0, 5, n),
        "y_pred": rng.uniform(0, 40, n),
    })


def test_minmax01_range_and_degenerate():
    x = minmax01([1, 2, 3, 4])
    assert x.min() == 0.0 and x.max() == 1.0
    # constant input -> all zeros, no div-by-zero
    assert np.all(minmax01([5, 5, 5]) == 0.0)


def test_pick_col():
    df = pd.DataFrame(columns=["Stiring", "y_pred"])
    assert pick_col(df, ["stirring", "Stiring"]) == "Stiring"
    assert pick_col(df, ["absent"]) is None


def test_v1_outputs_bounded_mci():
    out, drivers = sustainability_v1(_df())
    assert {"energy_proxy", "co2_proxy", "mci_proxy"} <= set(out.columns)
    assert out["mci_proxy"].between(0, 1).all()
    assert drivers["temperature"] == "temperature"


def test_pca_uses_pca_mode_with_multiple_columns():
    out, info = sustainability_pca_energy_index(_df())
    assert info["mode"] == "pca"
    assert len(info["used_columns"]) >= 2
    assert out["mci_pca_proxy"].between(0, 1).all()


def test_pca_single_column_fallback():
    df = pd.DataFrame({"time_s": np.linspace(0, 1, 10), "y_pred": np.linspace(0, 5, 10)})
    out, info = sustainability_pca_energy_index(df)
    assert info["mode"] == "single_column_fallback"


def test_eco_efficiency_higher_for_more_output_per_burden():
    df = pd.DataFrame({
        "y_pred": [10.0, 10.0, 1.0],
        "co2_proxy": [0.1, 0.9, 0.9],  # row 0: high output, low burden -> best
    })
    out, info = sustainability_eco_efficiency(df, burden_col="co2_proxy")
    assert info["burden_col"] == "co2_proxy"
    assert out["eco_eff_proxy"].between(0, 1).all()
    assert out["eco_eff_proxy"].idxmax() == 0  # best eco-efficiency


def test_eco_efficiency_missing_burden_raises():
    with pytest.raises(KeyError):
        sustainability_eco_efficiency(_df(), burden_col="nope")


def test_assumptions_end_to_end(tmp_path):
    cfg = {
        "drivers": {
            "time": ["time_s"],
            "temperature": ["Temperature (°C)"],
            "stirring": ["Stiring"],
        },
        "energy": {"method": "weighted_sum",
                   "weights": {"time": 0.4, "temperature": 0.4, "stirring": 0.2},
                   "normalize": "minmax"},
        "metrics": {"co2": "0.7*energy + 0.3*y_pred_n",
                    "mci": "clip(1 - (0.6*energy + 0.4*y_pred_n), 0, 1)"},
    }
    path = tmp_path / "assumptions.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    out, info = sustainability_from_assumptions(_df(), path)
    assert {"energy_assumed", "co2_assumed", "mci_assumed"} <= set(out.columns)
    assert out["mci_assumed"].between(0, 1).all()


def test_safe_eval_blocks_dangerous_expressions():
    for bad in ["__import__('os')", "open('x')", "import os", "eval('1')"]:
        with pytest.raises(ValueError):
            _safe_eval_expr(bad, {})


# --- unit-suffix tolerant column matching (the temperature-dropped fix) ----- #
def _df_real_names(n=40, seed=1):
    """Mimics the real processed data: unit-suffixed, mixed-case column names."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "time_s": rng.uniform(0, 1000, n),
        "Temperature (°C)": rng.uniform(20, 250, n),
        "Stiring": rng.uniform(0, 5, n),
        "y_pred": rng.uniform(0, 40, n),
    })


def test_normalize_colname_strips_units_and_case():
    from helper.sustainability_metrics import normalize_colname
    assert normalize_colname("Temperature (°C)") == "temperature"
    assert normalize_colname("Pressure (bar)") == "pressure"
    assert normalize_colname("time_s") == "time_s"


def test_v1_detects_unit_suffixed_temperature():
    out, drivers = sustainability_v1(_df_real_names())
    # temperature must now be resolved to the real unit-suffixed column
    assert drivers["temperature"] == "Temperature (°C)"
    assert drivers["stirring"] == "Stiring"
    # and it must actually contribute to energy (non-constant energy_proxy)
    assert out["energy_proxy"].nunique() > 1


def test_pca_uses_unit_suffixed_columns():
    out, info = sustainability_pca_energy_index(_df_real_names())
    assert info["mode"] == "pca"
    assert "Temperature (°C)" in info["used_columns"]


def test_pick_col_exact_still_wins():
    # When both an exact and a fuzzy candidate exist, exact wins.
    df = pd.DataFrame(columns=["temperature", "Temperature (°C)"])
    assert pick_col(df, ["temperature"]) == "temperature"
