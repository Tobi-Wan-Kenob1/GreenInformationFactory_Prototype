"""Model zoo and hyperparameter grids.

Extracted from ``03_train_optimize.ipynb`` and extended with additional
regressors. Every scale-sensitive estimator is wrapped in a ``StandardScaler``
pipeline so grids can address the final step via the ``model__`` prefix.

New in this version (vs. the original 5-model notebook):
- ``enet``       : ElasticNet (L1/L2 linear baseline, often beats plain OLS)
- ``extratrees`` : Extremely Randomized Trees (fast, low-variance ensemble)
- ``xgb``        : XGBoost, only registered if the ``xgboost`` package is
                   installed — the pipeline degrades gracefully without it.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression, ElasticNet
from sklearn.ensemble import (
    RandomForestRegressor,
    GradientBoostingRegressor,
    ExtraTreesRegressor,
)
from sklearn.svm import SVR
from sklearn.neural_network import MLPRegressor

try:  # optional dependency
    from xgboost import XGBRegressor  # type: ignore
    _HAS_XGB = True
except Exception:  # pragma: no cover - depends on environment
    _HAS_XGB = False


def _scaled(estimator) -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("model", estimator)])


def build_models(random_seed: int = 42) -> Dict[str, object]:
    """Return the full estimator registry keyed by short name."""
    models: Dict[str, object] = {
        "linreg": _scaled(LinearRegression()),
        "enet": _scaled(ElasticNet(random_state=random_seed, max_iter=10000)),
        "rf": RandomForestRegressor(random_state=random_seed),
        "extratrees": ExtraTreesRegressor(random_state=random_seed),
        "gbr": GradientBoostingRegressor(random_state=random_seed),
        "svr": _scaled(SVR()),
        "mlp": _scaled(MLPRegressor(random_state=random_seed, max_iter=2000)),
    }
    if _HAS_XGB:
        models["xgb"] = XGBRegressor(
            random_state=random_seed, n_estimators=400, objective="reg:squarederror"
        )
    return models


def build_param_grids() -> Dict[str, Dict[str, Sequence]]:
    """Return the hyperparameter grids keyed by short name."""
    grids: Dict[str, Dict[str, Sequence]] = {
        "linreg": {},
        "enet": {
            "model__alpha": [0.01, 0.1, 1.0],
            "model__l1_ratio": [0.1, 0.5, 0.9],
        },
        "rf": {
            "n_estimators": [200, 500],
            "max_depth": [None, 5, 10],
            "min_samples_split": [2, 5],
        },
        "extratrees": {
            "n_estimators": [200, 500],
            "max_depth": [None, 10, 20],
            "min_samples_split": [2, 5],
        },
        "gbr": {
            "n_estimators": [200, 500],
            "learning_rate": [0.05, 0.1],
            "max_depth": [2, 3, 4],
        },
        "svr": {
            "model__C": [0.1, 1, 10],
            "model__epsilon": [0.01, 0.1, 0.2],
            "model__kernel": ["rbf"],
            "model__gamma": ["scale", "auto"],
        },
        "mlp": {
            "model__hidden_layer_sizes": [(50,), (100,), (100, 50)],
            "model__alpha": [1e-4, 1e-3],
            "model__learning_rate_init": [1e-3, 5e-4],
        },
    }
    if _HAS_XGB:
        grids["xgb"] = {
            "max_depth": [3, 5, 7],
            "learning_rate": [0.05, 0.1],
            "subsample": [0.8, 1.0],
        }
    return grids


def available_models() -> List[str]:
    """Names of all registered models in this environment."""
    return list(build_models().keys())


def select_models(
    enabled: Optional[Sequence[str]],
    random_seed: int = 42,
) -> tuple[Dict[str, object], Dict[str, Dict[str, Sequence]]]:
    """Return ``(models, grids)`` filtered to ``enabled`` (or all if None).

    Unknown names in ``enabled`` are ignored so a config that requests an
    unavailable optional model (e.g. ``xgb`` with xgboost not installed) does
    not break the run.
    """
    models = build_models(random_seed)
    grids = build_param_grids()
    if enabled is None:
        return models, grids
    keep = [k for k in enabled if k in models]
    models = {k: models[k] for k in keep}
    grids = {k: grids.get(k, {}) for k in keep}
    return models, grids
