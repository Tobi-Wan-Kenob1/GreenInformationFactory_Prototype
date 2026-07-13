"""Configuration and path resolution for the ``gif`` pipeline.

Thin, dependency-light wrappers around ``helper.utils`` that give the rest of
the package a single, typed way to find the repo root, load
``metadata/pipeline_config.json`` and resolve the standard data directories.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from helper.utils import find_repo_root, load_pipeline_config


@dataclass(frozen=True)
class PipelinePaths:
    """Resolved absolute paths for the standard pipeline directories."""

    repo_root: Path
    raw_dir: Path
    processed_dir: Path
    results_dir: Path
    models_dir: Path
    run_logs_dir: Path

    def ensure(self) -> "PipelinePaths":
        """Create the output directories (idempotent). Returns self."""
        for p in (self.processed_dir, self.results_dir, self.models_dir, self.run_logs_dir):
            p.mkdir(parents=True, exist_ok=True)
        return self


def load_config(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load ``metadata/pipeline_config.json`` as a dict."""
    repo_root = repo_root or find_repo_root()
    return load_pipeline_config(repo_root)


def resolve_paths(cfg: Dict[str, Any], repo_root: Optional[Path] = None) -> PipelinePaths:
    """Resolve the ``paths`` section of the config to absolute paths."""
    repo_root = repo_root or find_repo_root()
    paths = cfg["paths"]
    return PipelinePaths(
        repo_root=repo_root,
        raw_dir=repo_root / paths["raw_dir"],
        processed_dir=repo_root / paths["processed_dir"],
        results_dir=repo_root / paths["results_dir"],
        models_dir=repo_root / paths["models_dir"],
        run_logs_dir=repo_root / paths["run_logs_dir"],
    )
