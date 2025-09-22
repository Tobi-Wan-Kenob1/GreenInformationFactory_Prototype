# helper/upload_collector.py
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Iterable, Union, Dict, List

PathLike = Union[str, Path]

__all__ = ["prepare_release_payload"]

def _find_repo_root(start: Path | None = None) -> Path:
    """
    Walk upwards from 'start' (or CWD) until a .git directory is found.
    Returns CWD if not found (best effort).
    """
    p = start or Path.cwd()
    for parent in [p, *p.resolve().parents]:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()

def _coerce_path(x: PathLike) -> Path:
    return x if isinstance(x, Path) else Path(x)

def _resolve_group(
    items: Iterable[PathLike],
    repo_root: Path,
    required_prefix: Path,
) -> List[Path]:
    """
    Map each item to a path under repo_root with smart prefixing:
    - If absolute -> use as-is.
    - If already starts with required_prefix (e.g. "data/processed") -> join repo_root/item.
    - Else -> join repo_root/required_prefix/item.
    """
    resolved: List[Path] = []
    req_str = str(required_prefix).rstrip("/\\")
    for item in items:
        p = _coerce_path(item)
        if p.is_absolute():
            resolved.append(p)
        else:
            # normalize string compare on POSIX style
            p_str = str(p).lstrip("./")
            if p_str.startswith(req_str + "/") or p_str == req_str:
                resolved.append(repo_root / p)
            else:
                resolved.append(repo_root / required_prefix / p)
    return resolved

def prepare_release_payload(
    files: Iterable[PathLike],
    results: Iterable[PathLike],
    models: Iterable[PathLike],
    payload_subdir: str = "notebooks/release_payload",
    require_all: bool = False,
) -> Dict[str, object]:
    """
    Collect project artifacts into a single payload directory for release/Zenodo upload.

    Parameters
    ----------
    files : list[str|Path]
        Items that live under 'data/processed/'. You may pass:
          - "Train/foo.csv"                (subpath)
          - "data/processed/Train/foo.csv" (prefixed)
          - absolute paths
    results : list[str|Path]
        Items that live under 'data/results/'. Same flexibility as 'files'.
    models : list[str|Path]
        Items that live under 'models/'. Same flexibility as 'files'.
    payload_subdir : str
        Destination under the repo root where files are copied. Default "notebooks/release_payload".
    require_all : bool
        If True, raise FileNotFoundError when any source is missing.

    Returns
    -------
    dict with:
        - 'payload_dir' : Path
        - 'copied'      : list[Path] (dest paths)
        - 'missing'     : list[Path] (source paths that did not exist)
    """
    repo_root = _find_repo_root()
    payload = repo_root / payload_subdir
    # Clean out any existing payload contents to ensure only one upload at a time
    if payload.exists():
        for f in payload.iterdir():
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                import shutil
                shutil.rmtree(f)
    payload.mkdir(parents=True, exist_ok=True)

    sources_files   = _resolve_group(files,   repo_root, Path("data/processed"))
    sources_results = _resolve_group(results, repo_root, Path("data/results"))
    sources_models  = _resolve_group(models,  repo_root, Path("notebooks/models"))

    # Deduplicate while preserving order
    seen = set()
    all_sources: List[Path] = []
    for p in (sources_files + sources_results + sources_models):
        key = p.resolve() if p.exists() else p
        if key not in seen:
            seen.add(key)
            all_sources.append(p)

    missing: List[Path] = []
    copied: List[Path] = []
    for src in all_sources:
        if src.exists():
            dst = payload / src.name  # flat copy (only basenames)
            shutil.copy2(src, dst)
            copied.append(dst)
        else:
            missing.append(src)

    # Pretty summary
    print(f"📦 Payload directory: {payload}")
    if copied:
        print("✅ Copied:")
        for p in copied:
            print(f"  - {p.name}")
    else:
        print("⚠️ Nothing copied.")

    if missing:
        print("\n⚠️ Missing (not found on disk):")
        for m in missing:
            print(f"  - {m}")
        print("\nTip: Check typos (e.g., 'Test/' vs 'Text/') and correct directories:")
        print("     • files   → data/processed/…")
        print("     • results → data/results/…")
        print("     • models  → models/…")
        if require_all:
            raise FileNotFoundError("Some source files were missing. See list above.")

    return {"payload_dir": payload, "copied": copied, "missing": missing}
