"""Pytest bootstrap: make ``gif`` and ``helper`` importable without install.

Adds the repo root (for ``helper``) and ``src`` (for ``gif``) to ``sys.path``
so the suite runs from a bare checkout via ``pytest`` alone.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"

for p in (str(_REPO_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)
