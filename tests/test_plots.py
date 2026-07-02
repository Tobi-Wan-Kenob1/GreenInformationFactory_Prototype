"""Tests for gif.plots (figures are written headless via the Agg backend)."""
import matplotlib
matplotlib.use("Agg")  # no display needed in CI

import numpy as np
import pandas as pd
import pytest

from gif.plots import training_plots, scenario_plots
from gif.train import train_models


def _dataset(n=120, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({
        "time_s": rng.uniform(0, 1000, n),
        "Temperature (°C)": rng.uniform(20, 250, n),  # unit-suffixed on purpose
        "Stiring": rng.uniform(0, 5, n),
    })
    y = pd.Series(0.01 * X["Temperature (°C)"] + 0.5 * X["Stiring"] + rng.normal(0, 0.1, n))
    return X, y


def test_training_plots_written(tmp_path):
    X, y = _dataset()
    result = train_models(X[:80], y[:80], X[80:100], y[80:100], X[100:], y[100:],
                          enabled=["linreg", "rf"], cv_folds=3, n_jobs=1)
    saved = training_plots(result.results, result.best_models, X[100:], y[100:], tmp_path)
    assert {p.name for p in saved} == {"val_scatter_top3.png", "val_rmse_bar.png", "val_r2_bar.png"}
    assert all(p.exists() and p.stat().st_size > 0 for p in saved)


def test_scenario_plots_sanitize_unit_suffixed_names(tmp_path):
    out = pd.DataFrame({
        "_var": ["Temperature (°C)"] * 3 + ["Stiring"] * 3,
        "_val": [1, 2, 3, 1, 2, 3],
        "y_pred": [1.0, 2.0, 3.0, 1.0, 1.5, 2.0],
        "co2_v1": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3],
        "mci_v1": [0.9, 0.8, 0.7, 0.9, 0.8, 0.7],
        "co2_pca": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3],
        "mci_pca": [0.9, 0.8, 0.7, 0.9, 0.8, 0.7],
    })
    saved = scenario_plots(out, "rf", tmp_path)
    names = {p.name for p in saved}
    # unit suffix must be sanitized out of the filename, no spaces/parens
    assert "scenario_y_pred_Temperature_C_rf.png" in names
    assert all(" " not in n and "(" not in n for n in names)
    assert all(p.exists() for p in saved)
