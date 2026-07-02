"""GreenInformationFactory (``gif``) — importable pipeline package.

This package extracts the logic that previously lived inline in the
``notebooks/`` cells into small, testable, non-interactive modules so the
whole workflow can be driven from a script, a CI job, or a notebook with a
single import surface.

Layering
--------
- ``helper/``      : low-level primitives (config/IO/hashing, sustainability
                     proxy formulas, release-payload collection). Unchanged.
- ``src/gif/``     : pipeline orchestration built on top of ``helper``.

Typical use::

    from gif import prepare_data, train_models, run_scenarios

or via the CLI::

    python -m gif.cli all
"""
from __future__ import annotations

__version__ = "0.2.0"

from .config import load_config, resolve_paths, PipelinePaths
from .data import (
    load_raw,
    prepare_data,
    save_splits,
    load_split,
    validate_raw,
    validate_prepared,
)
from .models import build_models, build_param_grids, available_models
from .train import train_models, evaluate_model, rmse
from .scenario import one_way_scenarios, run_scenarios

__all__ = [
    "__version__",
    # config
    "load_config",
    "resolve_paths",
    "PipelinePaths",
    # data
    "load_raw",
    "prepare_data",
    "save_splits",
    "load_split",
    "validate_raw",
    "validate_prepared",
    # models
    "build_models",
    "build_param_grids",
    "available_models",
    # training
    "train_models",
    "evaluate_model",
    "rmse",
    # scenario
    "one_way_scenarios",
    "run_scenarios",
]
