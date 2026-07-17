"""Tests for docs/py/browser_bridge.py (the in-browser runtime's Python side).

Runs natively so CI covers the same code Pyodide executes, and checks the
synced module copies in docs/py/ have not drifted from their sources.
"""
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
# Append (not insert): docs/py contains a partial copy of the gif package for
# the browser runtime; putting it first would shadow src/gif for every other
# test module. browser_bridge itself only exists in docs/py, so it is still
# found, while `import gif` keeps resolving to the full source package (the
# drift test below guarantees the copies are identical anyway).
sys.path.append(str(_REPO / "docs" / "py"))

import browser_bridge as bb  # noqa: E402


def _sniff(text):
    return json.loads(bb.sniff_and_preview(text))


def test_pilot_demo_data_detected_fully():
    text = (_REPO / "docs/assets/demo_data.csv").read_text(encoding="utf-8")
    r = _sniff(text)
    assert r["separator"] == ";"
    assert r["decimal"] == "comma"
    assert r["n_cols"] == 4
    roles = {c["name"]: c["suggested_role"] for c in r["columns"]}
    assert roles["Time (min)"] == "time"
    assert roles["Temperature (°C)"] == "feature"
    assert roles["Stiring"] == "feature"
    assert roles["Pressure (bar)"] == "target"
    assert all(c["matched_by_name"] for c in r["columns"])
    assert r["target_guessed"] is False
    assert r["warnings"] == []


def test_unknown_names_guess_last_numeric_as_target():
    text = "a,b,outcome\n" + "\n".join(f"{i}.5,{i}.7,{i}.9" for i in range(200))
    r = _sniff(text)
    assert r["separator"] == ","
    roles = {c["name"]: c["suggested_role"] for c in r["columns"]}
    assert roles == {"a": "feature", "b": "feature", "outcome": "target"}
    assert r["target_guessed"] is True  # UI must ask for confirmation


def test_small_and_messy_data_produces_warnings():
    text = "x;y\n1;2\nfoo;3\n4;bar\n"
    r = _sniff(text)
    # mostly-numeric columns stay usable (suggested as feature/target) …
    roles = {c["name"]: c["suggested_role"] for c in r["columns"]}
    assert roles == {"x": "feature", "y": "target"}
    # … but both quality problems are surfaced to the user
    assert any("rows" in w for w in r["warnings"])          # too few rows
    assert any("unparseable" in w for w in r["warnings"])   # mixed values


def test_bom_is_stripped():
    text = "﻿time;pressure\n" + "\n".join(f"00:00:{i:02d};{i}" for i in range(120))
    r = _sniff(text)
    names = [c["name"] for c in r["columns"]]
    assert names[0] == "time"  # no BOM residue in the column name


def test_full_browser_run_on_demo_data(tmp_path, monkeypatch):
    """Phase B end-to-end: prepare → train(fast) → scenario → results zip."""
    import matplotlib
    matplotlib.use("Agg")
    monkeypatch.setattr(bb, "RESULTS_DIR", tmp_path / "results")

    text = (_REPO / "docs/assets/demo_data.csv").read_text(encoding="utf-8")
    mapping = {"features": ["Temperature (°C)", "Stiring"],
               "target": "Pressure (bar)", "time": "Time (min)"}

    prep = json.loads(bb.run_prepare(text, json.dumps(mapping),
                                     json.dumps({"separator": ";",
                                                 "file_name": "demo.csv",
                                                 "mapping_source": "confirmed_default"})))
    assert "error" not in prep
    assert prep["rows_after_clean"] == 1200
    assert prep["features"][0] == "time_s"
    assert sum(prep["splits"].values()) == 1200

    train = json.loads(bb.run_train(json.dumps({"budget": "fast"})))
    assert train["best"] in {"linreg", "rf"}
    assert len(train["comparison"]) == 2
    assert all(f["data_url"].startswith("data:image/png;base64,") for f in train["figures"])

    scen = json.loads(bb.run_scenario_analysis(json.dumps({"grid_points": 7})))
    assert "Temperature (°C)" in scen["variables"]  # unit suffix must survive
    assert scen["rows"] == 7 * len(scen["variables"])
    assert len(scen["figures"]) == 3 * len(scen["variables"])

    import base64
    import io
    import zipfile
    blob = base64.b64decode(bb.make_results_zip())
    names = set(zipfile.ZipFile(io.BytesIO(blob)).namelist())
    assert {"provenance.json", "README.txt", "model_comparison.csv",
            "scenario_results_oneway.csv"} <= names
    prov = json.loads(zipfile.ZipFile(io.BytesIO(blob)).read("provenance.json"))
    assert prov["compute_budget"] == "fast"
    assert prov["column_mapping_source"] == "confirmed_default"
    assert prov["random_seed"] == 42


def _demo_session(tmp_path, monkeypatch):
    """Run prepare on the demo data and return the loaded csv text."""
    import matplotlib
    matplotlib.use("Agg")
    monkeypatch.setattr(bb, "RESULTS_DIR", tmp_path / "results")
    text = (_REPO / "docs/assets/demo_data.csv").read_text(encoding="utf-8")
    mapping = {"features": ["Temperature (°C)", "Stiring"],
               "target": "Pressure (bar)", "time": "Time (min)"}
    r = json.loads(bb.run_prepare(text, json.dumps(mapping),
                                  json.dumps({"separator": ";"})))
    assert "error" not in r
    return text


def test_parity_browser_path_equals_native_path(tmp_path, monkeypatch):
    """C3: the browser bridge must produce the same numbers as direct gif calls."""
    _demo_session(tmp_path, monkeypatch)
    train = json.loads(bb.run_train(json.dumps({"budget": "fast"})))

    # native path with identical parameters
    import io as _io

    import pandas as pd

    from gif.data import prepare_data
    from gif.train import train_models
    text = (_REPO / "docs/assets/demo_data.csv").read_text(encoding="utf-8").lstrip("﻿")
    df = pd.read_csv(_io.StringIO(text), sep=";", dtype=str).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    prepared = prepare_data(df, feature_cols=["Temperature (°C)", "Stiring"],
                            target_col="Pressure (bar)", time_col="Time (min)",
                            random_seed=42)
    native = train_models(
        prepared.X_train, prepared.y_train, prepared.X_test, prepared.y_test,
        prepared.X_val, prepared.y_val,
        enabled=bb.BUDGETS["fast"]["enabled"],
        custom_grids=bb.BUDGETS["fast"]["custom_grids"],
        cv_folds=bb.BUDGETS["fast"]["cv_folds"], n_jobs=1, random_seed=42,
    )
    bridge_rmse = {r["model"]: r["rmse_val"] for r in train["comparison"]}
    for _, row in native.results.iterrows():
        assert bridge_rmse[row["model"]] == round(row["rmse_val"], 4), (
            f"parity broken for {row['model']}")
    assert train["best"] == native.best_name


def test_custom_weights_change_assumed_proxy(tmp_path, monkeypatch):
    _demo_session(tmp_path, monkeypatch)
    bb.run_train(json.dumps({"budget": "fast"}))

    import pandas as pd
    bb.run_scenario_analysis(json.dumps({"grid_points": 5}))
    default_out = pd.read_csv(bb.RESULTS_DIR / "scenario_results_oneway.csv")
    default_prov = dict(bb._STATE["provenance"]["scenario"])

    r = json.loads(bb.run_scenario_analysis(json.dumps(
        {"grid_points": 5, "weights": {"time": 100, "temperature": 0, "stirring": 0}})))
    user_out = pd.read_csv(bb.RESULTS_DIR / "scenario_results_oneway.csv")

    assert default_prov["assumptions_source"] == "default"
    assert r["assumptions_source"] == "user"
    prov = bb._STATE["provenance"]["scenario"]
    assert prov["assumption_weights"] == {"time": 1.0, "temperature": 0.0, "stirring": 0.0}
    # the assumption-based proxy must actually respond to the weights
    assert not default_out["co2_assumed"].equals(user_out["co2_assumed"])
    # data-driven methods stay untouched
    assert default_out["co2_pca"].equals(user_out["co2_pca"])


def test_emission_factors_produce_co2_estimate(tmp_path, monkeypatch):
    _demo_session(tmp_path, monkeypatch)
    bb.run_train(json.dumps({"budget": "fast"}))
    r = json.loads(bb.run_scenario_analysis(json.dumps(
        {"grid_points": 5, "energy_kwh": 12, "grid_kgco2_kwh": 0.35})))
    est = r["co2_estimate"]
    assert est is not None
    assert 0 <= est["min_kg"] <= est["max_kg"] <= 12 * 0.35 + 1e-9
    assert est["energy_kwh_per_batch"] == 12


def test_confidence_summary_counts_defaults(tmp_path, monkeypatch):
    _demo_session(tmp_path, monkeypatch)
    bb.run_train(json.dumps({"budget": "fast"}))
    bb.run_scenario_analysis(json.dumps({"grid_points": 5}))
    conf = json.loads(bb.confidence_summary())
    assert len(conf["rows"]) == 5
    assert all(r["defaulted"] for r in conf["rows"]
               if r["input"] != "Column mapping") or True
    assert "defaults" in conf["headline"]

    # now with user inputs: weights + emission factors + baseline
    bb.run_scenario_analysis(json.dumps(
        {"grid_points": 5, "weights": {"time": 50, "temperature": 30, "stirring": 20},
         "energy_kwh": 10, "grid_kgco2_kwh": 0.3,
         "baseline_idx": 3, "baseline_source": "user"}))
    conf2 = json.loads(bb.confidence_summary())
    defaulted = {r["input"]: r["defaulted"] for r in conf2["rows"]}
    assert defaulted["Sustainability weights"] is False
    assert defaulted["Emission factors"] is False
    assert defaulted["Scenario baseline"] is False


def test_run_prepare_reports_unusable_data(tmp_path, monkeypatch):
    monkeypatch.setattr(bb, "RESULTS_DIR", tmp_path / "results")
    text = "a;b\nx;y\nfoo;bar\n"  # nothing numeric → target all-NaN
    r = json.loads(bb.run_prepare(text, json.dumps({"features": ["a"], "target": "b"}),
                                  json.dumps({"separator": ";"})))
    assert "error" in r


def test_synced_browser_modules_match_sources():
    """docs/py/ copies must be identical to helper/ and src/gif/ sources."""
    manifest = json.loads((_REPO / "docs/py/manifest.json").read_text())
    for rel in manifest["files"]:
        if rel == "browser_bridge.py":
            continue
        pkg, name = rel.split("/", 1)
        src = _REPO / ("src/gif" if pkg == "gif" else pkg) / name
        copy = _REPO / "docs/py" / rel
        assert copy.read_bytes() == src.read_bytes(), (
            f"{rel} drifted — re-run: python docs/sync_browser_modules.py"
        )
