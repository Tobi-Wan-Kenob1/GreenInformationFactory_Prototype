"""Derive a compact WP1/D1.2 codebook vocabulary for the Policy & Grant Finder.

The BioFairNet literature review (WP1/D1.2) coded 366 agri/mining papers into
barriers, drivers, stakeholders, circular-economy and bioeconomy codes. The
finder can match those same codes lexically against EU policies and Horizon
call topics, which answers a question the literature alone cannot: **which
barriers and drivers found in the literature are actually addressed by current
EU policy and funding, and which are blind spots?**

This is a deliberate, transparent lexical match — no classifier, no inference.
Every hit is a literal term occurrence the user can verify in the source
document. It is therefore a complement to ``gif.lit_ml``'s predictions, not a
replacement: the ML coder was trained on academic abstracts and its labels on
legal texts are unvalidated, whereas a term match is checkable by eye.

Output: ``docs/finder/data/wp1_codebook.json``, read directly by the browser.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from helper.utils import find_repo_root

#: Codebook dimensions in the order the UI should present them.
DIMENSIONS = ("barriers", "drivers", "stakeholders", "ce", "bio")

#: Human labels for the dimensions (``ce``/``bio`` are terse in the source).
DIMENSION_LABELS = {
    "barriers": "Barriers",
    "drivers": "Drivers",
    "stakeholders": "Stakeholders",
    "ce": "Circular economy",
    "bio": "Bioeconomy",
}

#: Codes this generic would match almost any document and carry no signal.
TOO_GENERIC = {"data", "fundamental", "regions", "region", "high", "low", "new"}


def canonical(code: str) -> str:
    """Collapse spelling variants onto one key.

    ``policy makers``/``policymakers`` and ``landscape``/``landscapes`` are the
    same code in substance; the source keeps them apart because it records the
    surface form that was found.
    """
    text = re.sub(r"[^a-z\s-]", "", str(code or "").lower()).strip()
    text = re.sub(r"[\s-]+", " ", text)
    words = []
    for word in text.split():
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.append(word)
    return "".join(words)


def build_codebook(lit_dir: Optional[Path] = None,
                   min_papers: int = 2,
                   top_per_dimension: int = 40) -> Dict[str, Any]:
    """Group the coded terms into a finder-ready vocabulary.

    ``min_papers`` drops one-off codes (the long tail is mostly incidental
    wording); ``top_per_dimension`` keeps the file small enough to ship.
    """
    root = find_repo_root()
    lit_dir = lit_dir or (root / "data" / "processed" / "literature")
    codes = pd.read_csv(Path(lit_dir) / "codes_long.csv")

    dimensions: Dict[str, List[Dict[str, Any]]] = {}
    for dimension in DIMENSIONS:
        subset = codes[codes["dimension"] == dimension]
        if subset.empty:
            continue
        # one vote per paper per code, so a repeatedly-coded paper cannot
        # inflate a term's weight
        per_paper = subset.drop_duplicates(["paper_id", "code"])

        papers: Dict[str, set] = defaultdict(set)
        surface: Dict[str, Counter] = defaultdict(Counter)
        for paper_id, code in zip(per_paper["paper_id"], per_paper["code"]):
            key = canonical(code)
            if not key or key in TOO_GENERIC:
                continue
            papers[key].add(paper_id)
            surface[key][str(code).strip().lower()] += 1

        entries = []
        for key, paper_ids in papers.items():
            if len(paper_ids) < min_papers:
                continue
            terms = sorted(surface[key], key=lambda t: (-surface[key][t], t))
            entries.append({
                "code": terms[0],              # most frequent surface form
                "terms": terms,                # every spelling to match on
                "papers": len(paper_ids),
            })
        entries.sort(key=lambda e: (-e["papers"], e["code"]))
        dimensions[dimension] = entries[:top_per_dimension]

    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": ("BioFairNet WP1/D1.2 literature codebook "
                   "(doi:10.5281/zenodo.20744025), via data/processed/literature/"
                   "codes_long.csv"),
        "scope": "366 coded papers on agriculture and mining sectors",
        "method": ("Lexical match only: a document is tagged with a code when one of "
                   "the code's recorded spellings occurs in its title or summary. "
                   "No model, no inference — every hit is verifiable in the source "
                   "text. Codes found in fewer than the configured minimum number of "
                   "papers, and codes too generic to carry signal, are excluded."),
        "dimension_labels": DIMENSION_LABELS,
        "dimensions": dimensions,
    }


def write_codebook(out_dir: Optional[Path] = None, **kwargs: Any) -> Path:
    """Write the codebook vocabulary next to the finder's other data files."""
    root = find_repo_root()
    out_dir = out_dir or (root / "docs" / "finder" / "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "wp1_codebook.json"
    payload = build_codebook(**kwargs)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path
