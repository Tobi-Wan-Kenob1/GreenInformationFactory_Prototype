from __future__ import annotations

import json
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def find_repo_root(start: Optional[Path] = None) -> Path:
    """
    Find repository root by walking upwards until a .git folder is found.
    Works from notebooks/ and other subfolders.
    """
    p = start or Path.cwd()
    for parent in [p, *p.resolve().parents]:
        if (parent / ".git").exists():
            return parent
    # best-effort fallback
    return Path.cwd()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def git_info(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Best-effort git metadata for provenance.
    Safe on systems without git or outside a repo.
    """
    repo_root = repo_root or find_repo_root()
    info: Dict[str, Any] = {"repo_root": str(repo_root)}

    def _run(args):
        return subprocess.check_output(args, cwd=repo_root, stderr=subprocess.DEVNULL).decode().strip()

    try:
        info["commit"] = _run(["git", "rev-parse", "HEAD"])
        info["branch"] = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        # dirty flag
        dirty = subprocess.call(["git", "diff", "--quiet"], cwd=repo_root) != 0
        info["dirty"] = bool(dirty)
    except Exception:
        info["commit"] = None
        info["branch"] = None
        info["dirty"] = None

    return info


def env_info() -> Dict[str, Any]:
    """
    Minimal environment provenance without heavy dependencies.
    """
    return {
        "python": os.sys.version.split()[0],
        "platform": os.sys.platform,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_pipeline_config(repo_root: Optional[Path] = None, rel_path: str = "metadata/pipeline_config.json") -> Dict[str, Any]:
    repo_root = repo_root or find_repo_root()
    cfg_path = repo_root / rel_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"Pipeline config not found: {cfg_path}")
    return load_json(cfg_path)


def save_run_log(
    stage: str,
    payload: Dict[str, Any],
    repo_root: Optional[Path] = None,
    run_logs_rel_dir: str = "metadata/runs",
    filename_prefix: Optional[str] = None,
) -> Path:
    """
    Store a compact run log for traceability.

    Example stage values:
      - download_store
      - prepare_data
      - train_optimize
      - sustainability_eval
      - scenario_analysis
    """
    repo_root = repo_root or find_repo_root()
    run_dir = ensure_dir(repo_root / run_logs_rel_dir)

    prefix = filename_prefix or stage
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = run_dir / f"{prefix}_{ts}.json"

    log = {
        "stage": stage,
        "timestamp_utc": utc_now_iso(),
        "git": git_info(repo_root),
        "env": env_info(),
        "payload": payload,
    }
    save_json(out, log)
    return out
