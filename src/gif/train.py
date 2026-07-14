"""Model training, hyperparameter search and evaluation.

Non-interactive port of the training loop in ``03_train_optimize.ipynb``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import make_scorer, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV

from .models import select_models


def rmse(y_true, y_pred) -> float:
    """Root mean squared error as a plain float."""
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


# Scorer used to *optimize* during grid search: sklearn maximizes, so we return
# negative RMSE (higher == better).
_rmse_scorer = make_scorer(
    lambda yt, yp: -np.sqrt(mean_squared_error(yt, yp)), greater_is_better=True
)


@dataclass
class TrainingResult:
    """Outcome of :func:`train_models`."""

    results: pd.DataFrame
    best_models: Dict[str, object]
    best_name: str
    best_model: object
    predictions: Dict[str, pd.DataFrame] = field(default_factory=dict)


def evaluate_model(model, X_test, y_test, X_val, y_val) -> Dict[str, float]:
    """Return RMSE/R² on the test and validation splits."""
    yhat_test = model.predict(X_test)
    yhat_val = model.predict(X_val)
    return {
        "rmse_test": rmse(y_test, yhat_test),
        "r2_test": float(r2_score(y_test, yhat_test)),
        "rmse_val": rmse(y_val, yhat_val),
        "r2_val": float(r2_score(y_val, yhat_val)),
    }


def train_models(
    X_train, y_train, X_test, y_test, X_val, y_val,
    *,
    enabled: Optional[Sequence[str]] = None,
    random_seed: int = 42,
    cv_folds: int = 5,
    n_jobs: int = -1,
    verbose: bool = False,
    custom_grids: Optional[Dict[str, Dict]] = None,
) -> TrainingResult:
    """Train (optionally grid-search) each enabled model and rank by val RMSE.

    ``custom_grids`` replaces the default hyperparameter grids per model name
    (models without an entry are fitted with their defaults) — used e.g. by
    the in-browser runtime to trim the search space to a fast subset.

    Returns a :class:`TrainingResult` whose ``results`` frame is sorted best
    first (lowest ``rmse_val``, tie-broken by highest ``r2_val``).
    """
    models, grids = select_models(enabled, random_seed=random_seed)
    if not models:
        raise ValueError(f"No known models selected from enabled={list(enabled or [])}.")
    if custom_grids is not None:
        grids = {k: custom_grids.get(k, {}) for k in models}

    rows: List[Dict[str, object]] = []
    best_models: Dict[str, object] = {}

    for name, estimator in models.items():
        grid = grids.get(name, {})
        start = time.time()
        if len(grid) == 0:
            estimator.fit(X_train, y_train)
            best, best_params = estimator, {}
        else:
            gs = GridSearchCV(
                estimator=estimator, param_grid=grid, scoring=_rmse_scorer,
                cv=cv_folds, n_jobs=n_jobs, refit=True,
            )
            gs.fit(X_train, y_train)
            best, best_params = gs.best_estimator_, gs.best_params_

        metrics = evaluate_model(best, X_test, y_test, X_val, y_val)
        row = {"model": name, **metrics,
               "fit_seconds": round(time.time() - start, 2),
               "best_params": best_params}
        rows.append(row)
        best_models[name] = best
        if verbose:
            print(f"{name}: rmse_val={metrics['rmse_val']:.4g} r2_val={metrics['r2_val']:.4g}")

    results = (
        pd.DataFrame(rows)
        .sort_values(["rmse_val", "r2_val"], ascending=[True, False])
        .reset_index(drop=True)
    )
    best_name = str(results.iloc[0]["model"])
    best_model = best_models[best_name]

    predictions = {
        "test": pd.DataFrame({"y_true": np.asarray(y_test), "y_pred": best_model.predict(X_test)}),
        "val": pd.DataFrame({"y_true": np.asarray(y_val), "y_pred": best_model.predict(X_val)}),
    }
    return TrainingResult(
        results=results, best_models=best_models,
        best_name=best_name, best_model=best_model, predictions=predictions,
    )
