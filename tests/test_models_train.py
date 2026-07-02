"""Tests for gif.models and gif.train."""
import numpy as np
import pandas as pd
import pytest

from gif.models import build_models, build_param_grids, available_models, select_models
from gif.train import train_models, rmse, evaluate_model


def _dataset(n=160, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({
        "time_s": rng.uniform(0, 1000, n),
        "temperature": rng.uniform(20, 250, n),
        "Stiring": rng.uniform(0, 5, n),
    })
    # A smooth, learnable target so RMSE/R² are meaningful.
    y = pd.Series(0.01 * X["temperature"] + 0.5 * X["Stiring"] + rng.normal(0, 0.1, n))
    return X, y


def test_registry_contains_new_models():
    names = available_models()
    for expected in ["linreg", "enet", "rf", "extratrees", "gbr", "svr", "mlp"]:
        assert expected in names


def test_grids_align_with_models():
    models = build_models()
    grids = build_param_grids()
    # every model has a grid entry (possibly empty)
    for name in models:
        assert name in grids


def test_select_models_ignores_unknown():
    models, grids = select_models(["rf", "not_a_model", "enet"])
    assert set(models) == {"rf", "enet"}
    assert set(grids) == {"rf", "enet"}


def test_rmse_zero_for_perfect_prediction():
    y = np.array([1.0, 2.0, 3.0])
    assert rmse(y, y) == pytest.approx(0.0)


def test_train_models_picks_best_and_reports(tmp_path):
    X, y = _dataset(180)
    Xtr, Xte, Xva = X.iloc[:120], X.iloc[120:150], X.iloc[150:]
    ytr, yte, yva = y.iloc[:120], y.iloc[120:150], y.iloc[150:]
    result = train_models(
        Xtr, ytr, Xte, yte, Xva, yva,
        enabled=["linreg", "rf"], cv_folds=3, n_jobs=1,
    )
    assert result.best_name in {"linreg", "rf"}
    assert list(result.results["model"])[0] == result.best_name  # sorted best-first
    # results sorted by ascending val RMSE
    rmses = list(result.results["rmse_val"])
    assert rmses == sorted(rmses)
    assert set(result.predictions) == {"test", "val"}
    assert len(result.predictions["val"]) == len(yva)


def test_train_models_empty_selection_raises():
    X, y = _dataset(40)
    with pytest.raises(ValueError):
        train_models(X, y, X, y, X, y, enabled=["unknown_only"], cv_folds=2, n_jobs=1)


def test_evaluate_model_keys():
    X, y = _dataset(60)
    from sklearn.linear_model import LinearRegression
    m = LinearRegression().fit(X, y)
    metrics = evaluate_model(m, X, y, X, y)
    assert set(metrics) == {"rmse_test", "r2_test", "rmse_val", "r2_val"}
