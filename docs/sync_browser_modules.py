#!/usr/bin/env python3
"""Sync the pipeline modules into docs/py/ for the in-browser runtime.

The "Try it live" page (docs/run.html) runs the pipeline inside the visitor's
browser via Pyodide. To keep that demo honest it executes the *real* modules,
not a re-implementation — this script copies them to where GitHub Pages can
serve them and writes a manifest the page uses to fetch them:

    python docs/sync_browser_modules.py

Re-run (and commit the result) whenever helper/ or src/gif/ change. The CI
parity check (Phase C) will fail if the copies drift from the sources.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEST = HERE / "py"

#: Modules the browser runtime needs. gif.zenodo / gif.literature are omitted:
#: they need network/requests and are not part of the in-browser flow.
SOURCES = {
    "helper": ["__init__.py", "utils.py", "sustainability_metrics.py", "upload_collector.py"],
    "gif": ["__init__.py", "config.py", "data.py", "models.py", "train.py",
            "scenario.py", "pipeline.py", "plots.py"],
    # default sustainability assumptions for the assumption-based proxy
    "metadata": ["sustainability_assumptions_v1.json"],
}


def main() -> None:
    files: list[str] = []
    for pkg, names in SOURCES.items():
        src_dir = REPO / ("src/gif" if pkg == "gif" else pkg)
        out_dir = DEST / pkg
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            src = src_dir / name
            shutil.copy2(src, out_dir / name)
            files.append(f"{pkg}/{name}")

    # browser_bridge.py lives in docs/py/ directly (it is browser-specific).
    if (DEST / "browser_bridge.py").exists():
        files.append("browser_bridge.py")

    manifest = {"files": sorted(files)}
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"✅ synced {len(files)} file(s) into {DEST}")


if __name__ == "__main__":
    main()
