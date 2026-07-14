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
