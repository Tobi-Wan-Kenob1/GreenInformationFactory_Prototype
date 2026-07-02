"""Tests for gif.scenario."""
import numpy as np
import pandas as pd
import pytest

from gif.scenario import (
    detect_scenario_vars, scenario_range, build_grids,
    one_way_scenarios, run_scenarios,
)


class _LinearModel:
    """Tiny deterministic stand-in for a fitted estimator."""

    def __init__(self, cols):
        self.cols = cols

    def predict(self, X):
        X = X[self.cols]
        return (0.01 * X["temperature"] + 0.5 * X["Stiring"]).to_numpy()


def _X_base(n=100, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "time_s": rng.uniform(0, 1000, n),
        "temperature": rng.uniform(20, 250, n),
        "Stiring": rng.uniform(0, 5, n),
    })


def test_detect_scenario_vars():
    assert detect_scenario_vars(["time_s", "temperature", "Stiring"]) == [
        "time_s", "temperature", "Stiring"]
    assert detect_scenario_vars(["unrelated"]) == []


def test_scenario_range_fallbacks():
    lo, hi = scenario_range(pd.Series([5, 5, 5]))  # degenerate -> min/max -> [0,1]
    assert (lo, hi) == (0.0, 1.0)
    lo, hi = scenario_range(pd.Series([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
    assert lo < hi


def test_build_grids_shapes():
    X = _X_base()
    grids = build_grids(X, ["temperature", "Stiring"], grid_points=17)
    assert set(grids) == {"temperature", "Stiring"}
    assert all(len(v) == 17 for v in grids.values())


def test_one_way_scenarios_row_count():
    X = _X_base()
    grids = build_grids(X, ["temperature", "Stiring"], grid_points=10)
    baseline = X.iloc[[0]]
    sc = one_way_scenarios(baseline, grids)
    assert len(sc) == 2 * 10
    assert set(sc["_var"].unique()) == {"temperature", "Stiring"}


def test_run_scenarios_end_to_end():
    X = _X_base()
    model = _LinearModel(list(X.columns))
    out = run_scenarios(
        model, X, scenario_vars=["temperature", "Stiring"],
        grid_points=12, feature_order=list(X.columns),
    )
    assert len(out) == 2 * 12
    assert {"_var", "_val", "y_pred", "co2_v1", "mci_v1", "co2_pca", "mci_pca"} <= set(out.columns)
    # y_pred should increase monotonically with temperature at fixed baseline
    temp = out[out["_var"] == "temperature"].sort_values("_val")
    assert temp["y_pred"].is_monotonic_increasing


def test_run_scenarios_requires_vars():
    X = pd.DataFrame({"unrelated": [1, 2, 3]})
    with pytest.raises(ValueError):
        run_scenarios(_LinearModel(["unrelated"]), X)
