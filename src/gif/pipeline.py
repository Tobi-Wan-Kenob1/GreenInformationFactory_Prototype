"""High-level orchestration tying the pipeline stages together.

Each ``run_*`` function is a non-interactive equivalent of one notebook and
writes the same on-disk artifacts (splits, schema, hashes, model bundle, run
logs) so the notebook and scripted flows stay interchangeable.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from helper.utils import sha256_file, save_run_log
from .config import load_config, resolve_paths, PipelinePaths
from .data import (
    load_raw, prepare_data, save_splits, load_split,
    validate_raw, validate_prepared, resolve_column, PreparedData,
)
from .train import train_models, TrainingResult
from .scenario import run_scenarios, detect_scenario_vars


def _resolve_feature_target(df, cfg) -> tuple[list[str], str, Optional[str]]:
    """Resolve feature/target/time columns from config against actual columns.

    The config's ``ml.features``/``ml.target`` may use canonical short names
    (e.g. ``temperature``, ``pressure``); we map them to whatever the raw file
    actually contains via small candidate lists, falling back to the literal
    config value when present verbatim.
    """
    candidate_map = {
        "time": ["time_s", "time", "t", "Time", "Time (min)"],
        "temperature": ["temperature", "temp", "T", "Temperature", "Temperature (°C)"],
        "stiring": ["stiring", "Stiring", "stirring", "Stirring", "rpm", "RPM"],
        "stirring": ["stirring", "Stirring", "stiring", "Stiring", "rpm", "RPM"],
        "pressure": ["pressure", "Pressure", "Pressure (bar)"],
    }

    def _resolve_one(name: str) -> Optional[str]:
        if name in df.columns:
            return name
        return resolve_column(df, candidate_map.get(name.lower(), [name]))

    ml = cfg["ml"]
    time_col = None
    features: list[str] = []
    for f in ml["features"]:
        col = _resolve_one(f)
        if col is None:
            raise ValueError(f"Feature {f!r} could not be resolved to a column in {list(df.columns)}")
        if f.lower() in ("time", "time_s"):
            time_col = col if col != "time_s" else None  # already-seconds needs no parse
            if col == "time_s":
                features.append("time_s")
        else:
            features.append(col)
    target = _resolve_one(ml["target"])
    if target is None:
        raise ValueError(f"Target {ml['target']!r} could not be resolved in {list(df.columns)}")
    return features, target, time_col


def run_prepare(
    cfg: Optional[Dict[str, Any]] = None,
    paths: Optional[PipelinePaths] = None,
    *,
    strict: bool = True,
) -> PreparedData:
    """Load raw data, validate, clean, split, save splits + schema + hashes."""
    cfg = cfg or load_config()
    paths = paths or resolve_paths(cfg).ensure()

    raw_path = paths.raw_dir / cfg["dataset"]["raw_filename"]
    sep = cfg["dataset"].get("separator", ";")
    enc = cfg["dataset"].get("encoding", "utf-8")
    df = load_raw(raw_path, sep=sep, encoding=enc)

    problems = validate_raw(df, min_rows=1)
    if problems and strict:
        raise ValueError("Raw data validation failed:\n- " + "\n- ".join(problems))

    features, target, time_col = _resolve_feature_target(df, cfg)
    splits = cfg["ml"]["splits"]
    prepared = prepare_data(
        df, feature_cols=[f for f in features if f != "time_s"],
        target_col=target,
        time_col=time_col if time_col else None,
        holdout_fraction=splits["holdout_fraction"],
        train_fraction_within_train=splits["train_fraction_within_train"],
        random_seed=cfg["ml"]["random_seed"],
    )

    prob2 = validate_prepared(prepared)
    if prob2 and strict:
        raise ValueError("Prepared data validation failed:\n- " + "\n- ".join(prob2))

    written = save_splits(prepared, paths.processed_dir)

    schema = {
        "features": prepared.features,
        "target": prepared.target,
        "rows_total": len(prepared.df),
        "splits": prepared.report["splits"],
        "source_file": str(raw_path.relative_to(paths.repo_root)),
        "files": {k: str(v.relative_to(paths.repo_root)) for k, v in written.items()},
    }
    (paths.repo_root / "metadata" / "prepared_schema.json").write_text(
        json.dumps(schema, indent=2), encoding="utf-8"
    )
    hashes = {k: sha256_file(paths.repo_root / v) for k, v in schema["files"].items()}
    (paths.repo_root / "metadata" / "prepared_hashes.json").write_text(
        json.dumps(hashes, indent=2), encoding="utf-8"
    )

    save_run_log("prepare_data", {**prepared.report, "validation": problems + prob2},
                 repo_root=paths.repo_root, run_logs_rel_dir=cfg["paths"]["run_logs_dir"])
    return prepared


def run_train(
    cfg: Optional[Dict[str, Any]] = None,
    paths: Optional[PipelinePaths] = None,
    *,
    make_plots: bool = True,
) -> TrainingResult:
    """Load splits, train/grid-search models, save comparison + model bundle."""
    cfg = cfg or load_config()
    paths = paths or resolve_paths(cfg).ensure()

    X_train, y_train, *_ = load_split(paths.processed_dir, "Train")
    X_test, y_test, *_ = load_split(paths.processed_dir, "Test")
    X_val, y_val, *_ = load_split(paths.processed_dir, "Validation")

    gs = cfg["ml"]["gridsearch"]
    result = train_models(
        X_train, y_train, X_test, y_test, X_val, y_val,
        enabled=cfg["ml"].get("models_default"),
        random_seed=cfg["ml"]["random_seed"],
        cv_folds=gs["cv_folds"], n_jobs=gs["n_jobs"],
    )

    result.results.to_csv(paths.results_dir / "model_comparison.csv", index=False)
    if make_plots:
        try:
            from .plots import training_plots
            training_plots(result.results, result.best_models, X_val, y_val, paths.results_dir)
        except Exception as exc:  # plotting is best-effort, never fatal
            print(f"⚠️ Skipped training plots: {exc}")
    result.predictions["test"].to_csv(
        paths.results_dir / f"predictions_test_{result.best_name}.csv", index=False)
    result.predictions["val"].to_csv(
        paths.results_dir / f"predictions_val_{result.best_name}.csv", index=False)

    bundle = {
        "best_model_name": result.best_name,
        "best_model": result.best_model,
        "all_models": result.best_models,
        "comparison": result.results,
        "config": cfg,
    }
    bundle_path = paths.models_dir / "all_models.pkl"
    with open(bundle_path, "wb") as f:
        pickle.dump(bundle, f)

    save_run_log("train_optimize",
                 {"best_model": result.best_name,
                  "models": list(result.best_models.keys()),
                  "bundle": str(bundle_path.relative_to(paths.repo_root))},
                 repo_root=paths.repo_root, run_logs_rel_dir=cfg["paths"]["run_logs_dir"])
    return result


def run_scenario(
    cfg: Optional[Dict[str, Any]] = None,
    paths: Optional[PipelinePaths] = None,
    *,
    grid_points: int = 25,
    baseline_idx: int = 0,
    make_plots: bool = True,
) -> pd.DataFrame:
    """Load the model bundle + validation split and run the one-way sweep."""
    cfg = cfg or load_config()
    paths = paths or resolve_paths(cfg).ensure()

    with open(paths.models_dir / "all_models.pkl", "rb") as f:
        bundle = pickle.load(f)
    best_model, best_name = bundle["best_model"], bundle["best_model_name"]

    X_base, _, _, _ = load_split(paths.processed_dir, "Validation")
    assumptions_path = paths.repo_root / "metadata" / "sustainability_assumptions_v1.json"
    scenario_vars = detect_scenario_vars(X_base.columns)

    out = run_scenarios(
        best_model, X_base,
        scenario_vars=scenario_vars,
        baseline_idx=baseline_idx, grid_points=grid_points,
        feature_order=list(X_base.columns),
        assumptions_path=assumptions_path if assumptions_path.exists() else None,
    )
    out_path = paths.results_dir / f"scenario_results_oneway_{best_name}.csv"
    out.to_csv(out_path, index=False)
    if make_plots:
        try:
            from .plots import scenario_plots
            scenario_plots(out, best_name, paths.results_dir, scenario_vars)
        except Exception as exc:  # plotting is best-effort, never fatal
            print(f"⚠️ Skipped scenario plots: {exc}")

    save_run_log("scenario_analysis",
                 {"model": best_name, "grid_points": grid_points,
                  "scenario_vars": detect_scenario_vars(X_base.columns),
                  "output": str(out_path.relative_to(paths.repo_root))},
                 repo_root=paths.repo_root, run_logs_rel_dir=cfg["paths"]["run_logs_dir"])
    return out


def run_all(cfg: Optional[Dict[str, Any]] = None, *, grid_points: int = 25) -> Dict[str, Any]:
    """Run prepare → train → scenario end to end."""
    cfg = cfg or load_config()
    paths = resolve_paths(cfg).ensure()
    prepared = run_prepare(cfg, paths)
    trained = run_train(cfg, paths)
    scenarios = run_scenario(cfg, paths, grid_points=grid_points)
    return {"prepared": prepared, "trained": trained, "scenarios": scenarios}
