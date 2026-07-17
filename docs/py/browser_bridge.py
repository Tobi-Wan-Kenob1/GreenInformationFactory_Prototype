"""Bridge between docs/run.html (JavaScript) and the real pipeline modules.

Runs inside Pyodide. Every function takes/returns JSON strings so the JS side
stays a thin UI layer; all logic reuses the actual ``gif`` / ``helper`` code
so the browser demo behaves exactly like the CLI.

Phase A: format sniffing + column-role suggestion + data preview.
Phase B: pipeline execution — ``run_prepare`` → ``run_train`` →
``run_scenario_analysis`` → ``make_results_zip``. State is kept in module
globals (one analysis session per page load).
"""
from __future__ import annotations

import base64
import io
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gif.data import prepare_data, resolve_column, validate_prepared
from gif.scenario import detect_scenario_vars, run_scenarios
from gif.train import train_models
from helper.sustainability_metrics import normalize_colname

#: Where result files (CSVs, PNGs) accumulate for the download zip. Uses the
#: platform temp dir so the module works both in Pyodide's in-memory FS and
#: natively in the test suite.
RESULTS_DIR = Path(tempfile.gettempdir()) / "gif_browser_results"

#: Row cap for the in-browser demo (single-core WebAssembly); larger uploads
#: are subsampled with a provenance note.
MAX_ROWS = 20000

#: Compute budgets: model subset + optional grid override + CV folds.
BUDGETS = {
    "fast": {
        "enabled": ["linreg", "rf"],
        "custom_grids": {"rf": {"n_estimators": [100], "max_depth": [None, 10]}},
        "cv_folds": 3,
    },
    "thorough": {
        "enabled": ["linreg", "enet", "rf", "extratrees", "gbr"],
        "custom_grids": None,  # standard grids (SVR/MLP stay excluded: too slow single-core)
        "cv_folds": 3,
    },
}

_STATE: dict = {}

#: Candidate names for each column role — the same lists the pipeline uses
#: (gif.pipeline._resolve_feature_target / helper.sustainability_metrics).
ROLE_CANDIDATES = {
    "time": ["time_s", "time", "t", "Time", "Time (min)", "timestamp"],
    "temperature": ["temperature", "temp", "T", "Temperature"],
    "stirring": ["stirring", "Stirring", "stiring", "Stiring", "rpm", "RPM"],
    "target": ["pressure", "Pressure", "yield", "Yield", "output", "conversion"],
}

_SEPARATORS = [";", ",", "\t", "|"]


def _sniff_separator(text: str) -> str:
    """Pick the separator that yields the most (and consistent) columns."""
    lines = [l for l in text.splitlines()[:20] if l.strip()]
    best, best_score = ";", 0
    for sep in _SEPARATORS:
        counts = [line.count(sep) for line in lines]
        if not counts or min(counts) == 0:
            continue
        # consistent column count across lines scores higher
        score = min(counts) * (2 if len(set(counts)) == 1 else 1)
        if score > best_score:
            best, best_score = sep, score
    return best


def _numeric_ratio(series: pd.Series) -> float:
    """Fraction of values that parse as numbers (comma decimals allowed)."""
    s = series.astype(str).str.strip().str.replace(",", ".", regex=False)
    return float(pd.to_numeric(s, errors="coerce").notna().mean())


def _looks_like_time(series: pd.Series) -> bool:
    s = series.astype(str).str.strip()
    return bool(pd.to_timedelta(s, errors="coerce").notna().mean() > 0.8)


def _decimal_style(df: pd.DataFrame) -> str:
    sample = df.astype(str).head(200).to_string()
    commas = sum(1 for _ in __import__("re").finditer(r"\d,\d", sample))
    dots = sum(1 for _ in __import__("re").finditer(r"\d\.\d", sample))
    return "comma" if commas > dots else "dot"


def sniff_and_preview(csv_text: str) -> str:
    """Analyze an uploaded delimited text file.

    Returns JSON with: separator, decimal style, row/column counts, a small
    preview, and a per-column analysis including the suggested role
    (``time`` / ``feature`` / ``target`` / ``ignore``) plus whether that
    suggestion came from name matching (the pipeline's candidate lists) or
    from content heuristics.
    """
    # strip a BOM if present (the pilot CSV has one)
    csv_text = csv_text.lstrip("﻿")
    sep = _sniff_separator(csv_text)
    df = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]

    # role suggestions by name first (same matching as the pipeline: exact,
    # then case/unit-suffix tolerant via normalize_colname)
    assigned: dict[str, str] = {}
    matched_by_name: set = set()
    for role in ("time", "temperature", "stirring", "target"):
        col = resolve_column(df, ROLE_CANDIDATES[role])
        if col is None:
            norm_map = {normalize_colname(c): c for c in df.columns}
            for cand in ROLE_CANDIDATES[role]:
                hit = norm_map.get(normalize_colname(cand))
                if hit is not None:
                    col = hit
                    break
        if col is not None and col not in assigned:
            assigned[col] = "target" if role == "target" else (
                "time" if role == "time" else "feature")
            matched_by_name.add(col)

    columns = []
    numeric_cols = []
    for col in df.columns:
        ratio = _numeric_ratio(df[col])
        is_time = col not in assigned and _looks_like_time(df[col])
        if col in assigned:
            role = assigned[col]
        elif is_time:
            role = "time"
        elif ratio > 0.5:
            # mostly-numeric columns are suggested as features even when some
            # values fail to parse — the warning below flags the bad rows and
            # the user can still switch the role to "ignore".
            role = "feature"
            numeric_cols.append(col)
        else:
            role = "ignore"
        columns.append({
            "name": col,
            "suggested_role": role,
            "matched_by_name": col in matched_by_name,
            "numeric_ratio": round(ratio, 3),
            "sample": df[col].head(3).tolist(),
        })

    # if no target was matched by name, promote the last numeric column —
    # flagged as a guess so the UI can require confirmation
    target_guessed = False
    if not any(c["suggested_role"] == "target" for c in columns):
        if numeric_cols:
            for c in columns:
                if c["name"] == numeric_cols[-1]:
                    c["suggested_role"] = "target"
                    target_guessed = True

    result = {
        "separator": sep,
        "decimal": _decimal_style(df),
        "n_rows": int(len(df)),
        "n_cols": int(len(df.columns)),
        "preview": df.head(5).to_dict(orient="records"),
        "columns": columns,
        "target_guessed": target_guessed,
        "warnings": _warnings(df, columns),
    }
    return json.dumps(result)


def _warnings(df: pd.DataFrame, columns: list) -> list:
    w = []
    if len(df) < 100:
        w.append(f"Only {len(df)} rows — models will be unreliable below a few hundred rows.")
    n_feat = sum(1 for c in columns if c["suggested_role"] == "feature")
    if n_feat == 0:
        w.append("No numeric feature columns detected — check the separator and decimal settings.")
    low = [c["name"] for c in columns
           if c["suggested_role"] in ("feature", "target") and c["numeric_ratio"] < 0.95]
    if low:
        w.append(f"Columns with unparseable values (will become gaps): {', '.join(low)}.")
    return w


def runtime_info() -> str:
    """Versions of the loaded scientific stack, for the page footer."""
    import sys

    import numpy
    import sklearn

    import gif

    return json.dumps({
        "python": sys.version.split()[0],
        "numpy": numpy.__version__,
        "pandas": pd.__version__,
        "sklearn": sklearn.__version__,
        "gif": gif.__version__,
    })


# --------------------------------------------------------------------------- #
# Phase B: pipeline execution
# --------------------------------------------------------------------------- #
def _png_data_urls(paths) -> list:
    out = []
    for p in paths:
        p = Path(p)
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        out.append({"name": p.name, "data_url": "data:image/png;base64," + b64})
    return out


def run_prepare(csv_text: str, mapping_json: str, options_json: str = "{}") -> str:
    """Clean + split the uploaded data using the confirmed column mapping."""
    mapping = json.loads(mapping_json)
    options = json.loads(options_json)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    for old in RESULTS_DIR.glob("*"):
        old.unlink()

    csv_text = csv_text.lstrip("﻿")
    sep = options.get("separator", ";")
    df = pd.read_csv(io.StringIO(csv_text), sep=sep, dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]

    subsampled = False
    if len(df) > MAX_ROWS:
        df = df.sample(n=MAX_ROWS, random_state=42).sort_index().reset_index(drop=True)
        subsampled = True

    try:
        prepared = prepare_data(
            df,
            feature_cols=mapping["features"],
            target_col=mapping["target"],
            time_col=mapping.get("time") or None,
            random_seed=42,
        )
    except Exception as exc:
        # e.g. every row dropped (non-numeric target) → sklearn refuses to
        # split 0 samples. Surface a readable message instead of a traceback.
        return json.dumps({"error": f"Could not prepare this data: {exc}"})
    problems = validate_prepared(prepared)
    if problems:
        return json.dumps({"error": "Prepared data is unusable: " + "; ".join(problems)})

    _STATE.clear()
    _STATE["prepared"] = prepared
    _STATE["provenance"] = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_name": options.get("file_name", "uploaded.csv"),
        "column_mapping": mapping,
        "column_mapping_source": options.get("mapping_source", "auto"),
        "separator": sep,
        "random_seed": 42,
        "subsampled_to": MAX_ROWS if subsampled else None,
        "engine": json.loads(runtime_info()),
        "disclaimer": ("In-browser demo run. Results are indicative; defaults were used "
                       "where no expert input was provided."),
    }

    prepared.df.describe().to_csv(RESULTS_DIR / "data_summary.csv")
    return json.dumps({
        "rows_after_clean": prepared.report["rows_after_clean"],
        "rows_dropped": prepared.report["rows_dropped"],
        "features": prepared.features,
        "target": prepared.target,
        "splits": prepared.report["splits"],
        "subsampled": subsampled,
    })


def run_train(options_json: str = "{}") -> str:
    """Train and compare models on the prepared splits (fast mode default)."""
    options = json.loads(options_json)
    budget_name = options.get("budget", "fast")
    budget = BUDGETS.get(budget_name, BUDGETS["fast"])
    p = _STATE["prepared"]

    result = train_models(
        p.X_train, p.y_train, p.X_test, p.y_test, p.X_val, p.y_val,
        enabled=budget["enabled"],
        custom_grids=budget["custom_grids"],
        cv_folds=budget["cv_folds"],
        n_jobs=1, random_seed=42,
    )
    _STATE["trained"] = result
    _STATE["provenance"]["compute_budget"] = budget_name
    _STATE["provenance"]["models_evaluated"] = list(result.best_models.keys())

    comp = result.results.copy()
    comp["best_params"] = comp["best_params"].astype(str)
    comp.to_csv(RESULTS_DIR / "model_comparison.csv", index=False)
    result.predictions["val"].to_csv(RESULTS_DIR / "predictions_val.csv", index=False)

    caveat = ("fast mode: reduced model search — indicative ranking"
              if budget_name == "fast"
              else "browser mode: SVR/MLP excluded from the comparison")
    from gif.plots import training_plots
    figs = training_plots(result.results, result.best_models, p.X_val, p.y_val,
                          RESULTS_DIR, caveat=caveat)

    return json.dumps({
        "best": result.best_name,
        "comparison": comp[["model", "rmse_val", "r2_val", "rmse_test", "r2_test",
                            "fit_seconds"]].round(4).to_dict(orient="records"),
        "figures": _png_data_urls(figs),
    })


#: Default driver weights of the assumption-based proxy (project defaults).
DEFAULT_WEIGHTS = {"time": 0.4, "temperature": 0.4, "stirring": 0.2}


def _resolve_assumptions(options: dict) -> tuple:
    """Return ``(assumptions_path, source, weights)`` for the scenario run.

    When the user supplied custom driver weights, a copy of the default
    assumptions JSON with those weights (normalized to sum 1) is written and
    used; otherwise the project defaults apply.
    """
    default_path = Path(__file__).parent / "metadata" / "sustainability_assumptions_v1.json"
    raw = options.get("weights")
    if not raw:
        return (default_path if default_path.exists() else None,
                "default", dict(DEFAULT_WEIGHTS))

    total = sum(float(v) for v in raw.values()) or 1.0
    weights = {k: round(float(v) / total, 4) for k, v in raw.items()}
    cfg = json.loads(default_path.read_text(encoding="utf-8"))
    cfg["energy"]["weights"] = weights
    custom = RESULTS_DIR / "custom_assumptions.json"
    custom.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return custom, "user", weights


def run_scenario_analysis(options_json: str = "{}") -> str:
    """One-way scenario sweep + sustainability proxies with the best model.

    Expert inputs (all optional, defaults tracked in provenance):
      - ``weights``: driver weights for the assumption-based proxy
      - ``baseline_idx``: which validation row anchors the sweep
      - ``energy_kwh`` + ``grid_kgco2_kwh``: emission factors that convert the
        normalized CO₂ proxy range into an indicative kg-CO₂e range
    """
    options = json.loads(options_json)
    grid_points = int(options.get("grid_points", 15))
    baseline_idx = int(options.get("baseline_idx", 0) or 0)
    baseline_source = "user" if options.get("baseline_source") == "user" else "default"
    p, trained = _STATE["prepared"], _STATE["trained"]
    baseline_idx = max(0, min(baseline_idx, len(p.X_val) - 1))

    scenario_vars = detect_scenario_vars(p.X_val.columns)
    if not scenario_vars:
        scenario_vars = list(p.X_val.columns)[:2]  # fall back: first features

    assumptions_path, assumptions_source, weights = _resolve_assumptions(options)
    out = run_scenarios(
        trained.best_model, p.X_val,
        scenario_vars=scenario_vars,
        baseline_idx=baseline_idx,
        grid_points=grid_points,
        feature_order=list(p.X_val.columns),
        assumptions_path=assumptions_path,
    )
    out.to_csv(RESULTS_DIR / "scenario_results_oneway.csv", index=False)

    # optional emission factors → indicative absolute CO2 range
    co2_estimate = None
    energy_kwh = options.get("energy_kwh")
    grid_int = options.get("grid_kgco2_kwh")
    if energy_kwh and grid_int and "co2_assumed" in out.columns:
        factor = float(energy_kwh) * float(grid_int)
        co2_estimate = {
            "min_kg": round(float(out["co2_assumed"].min()) * factor, 2),
            "max_kg": round(float(out["co2_assumed"].max()) * factor, 2),
            "energy_kwh_per_batch": float(energy_kwh),
            "grid_kgco2_per_kwh": float(grid_int),
        }

    _STATE["provenance"]["scenario"] = {
        "variables": scenario_vars, "grid_points": grid_points,
        "baseline_idx": baseline_idx, "baseline_source": baseline_source,
        "assumptions_source": assumptions_source,
        "assumption_weights": weights,
        "emission_factors": co2_estimate,
    }

    caveat = ("⚠ generic default assumptions — indicative only, high uncertainty"
              if assumptions_source == "default"
              else "user-provided assumptions — proxy values, not measured emissions")
    from gif.plots import scenario_plots
    figs = scenario_plots(out, trained.best_name, RESULTS_DIR, scenario_vars,
                          caveat=caveat)

    return json.dumps({
        "variables": scenario_vars,
        "rows": int(len(out)),
        "figures": _png_data_urls(figs),
        "co2_estimate": co2_estimate,
        "assumptions_source": assumptions_source,
    })


def confidence_summary() -> str:
    """Per-checkpoint provenance for the confidence card (JSON).

    Lists every user-influenceable input with its value and whether it came
    from the user or a default, plus a headline count.
    """
    prov = _STATE.get("provenance", {})
    scen = prov.get("scenario", {})
    ef = scen.get("emission_factors")
    w = scen.get("assumption_weights", DEFAULT_WEIGHTS)

    rows = [
        {"input": "Column mapping",
         "value": ", ".join(prov.get("column_mapping", {}).get("features", [])) +
                  " → " + str(prov.get("column_mapping", {}).get("target", "?")),
         "source": prov.get("column_mapping_source", "auto"),
         "defaulted": prov.get("column_mapping_source", "auto") != "user_edited"},
        {"input": "Compute budget",
         "value": prov.get("compute_budget", "fast"),
         "source": "user" if prov.get("compute_budget") == "thorough" else "default",
         "defaulted": prov.get("compute_budget", "fast") == "fast"},
        {"input": "Sustainability weights",
         "value": " / ".join(f"{k} {v:g}" for k, v in w.items()),
         "source": scen.get("assumptions_source", "default"),
         "defaulted": scen.get("assumptions_source", "default") == "default"},
        {"input": "Emission factors",
         "value": (f"{ef['energy_kwh_per_batch']:g} kWh × {ef['grid_kgco2_per_kwh']:g} kg CO₂/kWh"
                   if ef else "not provided — proxies stay in relative units (0–1)"),
         "source": "user" if ef else "default",
         "defaulted": ef is None},
        {"input": "Scenario baseline",
         "value": f"validation row {scen.get('baseline_idx', 0)}",
         "source": scen.get("baseline_source", "default"),
         "defaulted": scen.get("baseline_source", "default") == "default"},
    ]
    n_def = sum(1 for r in rows if r["defaulted"])
    headline = (f"{n_def} of {len(rows)} inputs used defaults — treat results as "
                "indicative." if n_def
                else "All inputs were provided or confirmed by you.")
    prov["confidence"] = {"rows": rows, "headline": headline}
    return json.dumps({"rows": rows, "headline": headline,
                       "co2_estimate": ef})


def make_results_zip() -> str:
    """Bundle every result file + provenance into a zip, returned as base64."""
    prov = _STATE.get("provenance", {})
    (RESULTS_DIR / "provenance.json").write_text(
        json.dumps(prov, indent=2), encoding="utf-8")
    (RESULTS_DIR / "README.txt").write_text(
        "GreenInformationFactory — in-browser analysis results\n"
        "======================================================\n\n"
        "Generated locally in your browser; no data was transmitted.\n"
        "See provenance.json for the exact inputs, defaults and engine versions.\n"
        "Pipeline: https://github.com/Tobi-Wan-Kenob1/GreenInformationFactory_Prototype\n",
        encoding="utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(RESULTS_DIR.glob("*")):
            z.write(f, arcname=f.name)
    return base64.b64encode(buf.getvalue()).decode("ascii")
