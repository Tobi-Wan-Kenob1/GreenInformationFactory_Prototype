"""Plotting helpers that regenerate the pipeline's standard figures.

Kept separate from the compute code so the notebooks (and the CLI) stay thin:
they call one function instead of carrying matplotlib boilerplate. All figures
are written to ``results_dir`` and the saved paths are returned.

matplotlib is imported lazily so importing this module (and therefore
``gif.pipeline``) never hard-fails in a headless/plot-less environment.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd


def _plt():
    import matplotlib
    # Pick a non-interactive backend when there is clearly no display, so
    # `gif train` works over SSH / in batch jobs without a configured GUI.
    import os
    if not os.environ.get("DISPLAY") and matplotlib.get_backend().lower() not in ("agg",):
        try:
            matplotlib.use("Agg")
        except Exception:
            pass
    import matplotlib.pyplot as plt
    return plt


def stamp_caveat(fig, text: str) -> None:
    """Stamp an uncertainty/provenance caveat onto a figure (bottom-right).

    Central hook so every plot produced under default assumptions or reduced
    settings carries its limitation visibly — on screen, in downloads, and in
    any report the figure ends up in.
    """
    fig.text(
        0.99, 0.005, text, ha="right", va="bottom", fontsize=7, style="italic",
        color="#8A5B14",
        bbox=dict(facecolor="#FFF4DE", edgecolor="#FFBE5C",
                  boxstyle="round,pad=0.3", alpha=0.92),
    )


def training_plots(
    results: pd.DataFrame,
    best_models: Dict[str, object],
    X_val,
    y_val,
    results_dir: Path,
    caveat: str | None = None,
) -> List[Path]:
    """Val scatter (top-3), val RMSE bar and val R² bar — mirrors notebook 03.

    ``caveat`` (optional) is stamped onto every figure — used when the run
    deviates from the full offline pipeline (e.g. reduced model search).
    """
    plt = _plt()
    results_dir = Path(results_dir)
    saved: List[Path] = []

    def _save(fig, fname: str):
        if caveat:
            stamp_caveat(fig, caveat)
        p = results_dir / fname
        fig.savefig(p, dpi=200, bbox_inches="tight")
        plt.close(fig)
        saved.append(p)

    top3 = results.head(3)["model"].tolist()
    fig = plt.figure()
    plt.title("Validation: True vs Predicted (Top 3 Models)")
    plt.xlabel("y_true"); plt.ylabel("y_pred")
    plt.plot([y_val.min(), y_val.max()], [y_val.min(), y_val.max()], "k--", label="Ideal")
    for m in top3:
        plt.scatter(y_val, best_models[m].predict(X_val), label=m, alpha=0.5)
    plt.legend()
    _save(fig, "val_scatter_top3.png")

    for col, title, ylabel, fname in [
        ("rmse_val", "Validation RMSE by Model", "RMSE (val)", "val_rmse_bar.png"),
        ("r2_val", "Validation R² by Model", "R² (val)", "val_r2_bar.png"),
    ]:
        fig = plt.figure()
        plt.title(title); plt.xlabel("model"); plt.ylabel(ylabel)
        plt.bar(results["model"], results[col])
        _save(fig, fname)

    return saved


def scenario_plots(
    out: pd.DataFrame,
    best_name: str,
    results_dir: Path,
    scenario_vars: Sequence[str] | None = None,
    caveat: str | None = None,
) -> List[Path]:
    """Per-variable y_pred sensitivity + CO₂/MCI method comparison — notebook 05.

    ``caveat`` (optional) is stamped onto every figure — e.g. when the
    sustainability proxies were computed under generic default assumptions.
    """
    plt = _plt()
    results_dir = Path(results_dir)
    saved: List[Path] = []
    scenario_vars = list(scenario_vars) if scenario_vars is not None else sorted(out["_var"].unique())

    has_assumed = "co2_assumed" in out.columns

    def _safe(name: str) -> str:
        # Keep filenames friendly even for unit-suffixed columns like "Temperature (°C)".
        import re
        return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")

    def _save(fig, fname: str):
        if caveat:
            stamp_caveat(fig, caveat)
        p = results_dir / fname
        fig.savefig(p, dpi=200, bbox_inches="tight")
        plt.close(fig)
        saved.append(p)

    for var in scenario_vars:
        dfv = out[out["_var"] == var].sort_values("_val")

        fig = plt.figure()
        plt.title(f"Scenario Sensitivity: {var} → y_pred ({best_name})")
        plt.xlabel(var); plt.ylabel("y_pred")
        plt.plot(dfv["_val"], dfv["y_pred"])
        _save(fig, f"scenario_y_pred_{_safe(var)}_{best_name}.png")

        for metric, cols, ylabel in [
            ("co2", ["co2_v1", "co2_pca"] + (["co2_assumed"] if has_assumed else []), "CO₂ proxy (lower better)"),
            ("mci", ["mci_v1", "mci_pca"] + (["mci_assumed"] if has_assumed else []), "MCI proxy (higher better)"),
        ]:
            fig = plt.figure()
            plt.title(f"{metric.upper()} proxy sensitivity vs {var}")
            plt.xlabel(var); plt.ylabel(ylabel)
            for yc in cols:
                plt.plot(dfv["_val"], dfv[yc], label=yc)
            plt.legend()
            _save(fig, f"scenario_{metric}_{_safe(var)}_{best_name}.png")

    return saved
