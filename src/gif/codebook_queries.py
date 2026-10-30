"""Pick query terms from the WP1 codebook by how specific they are in a corpus.

The codebook (``docs/finder/data/wp1_codebook.json``) ranks codes by how many
reviewed papers mention them. Ranking by that count alone does not give usable
queries, and this was established by trying it: the top barrier codes are bare
generic words — ``land`` (99 papers), ``water`` (90), ``demand`` (43),
``efficiency`` (24) — and *water* matches EU acts on drinking water, bathing
water, maritime policy and much else. Nor can such a term be narrowed by adding
a sector word, because the finder's multi-keyword search is a **union**: extra
keywords widen the result set rather than focus it.

So specificity is measured against the corpus instead of assumed. A code that
matches most of the corpus is not a topic — it is background — and is dropped.
What remains is ranked by the codebook's own paper count, which is independent
of this tool: the codes come from a literature review that predates it.

Only the corpus's own documents are read, never anything about what happened
afterwards, so the selection cannot be informed by the outcome it is later used
to test.

Run via ``gif codebook-queries``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from helper.utils import find_repo_root

#: Codes matching more than this share of the corpus are background, not topics.
DEFAULT_MAX_DF = 0.20

#: How many queries to return.
DEFAULT_TOP = 10

#: Dimensions to draw candidates from. Barriers and drivers are the ones that
#: name things an instrument can act on; stakeholders are actors, and the
#: circular-economy and bioeconomy dimensions are framings rather than topics.
DEFAULT_DIMENSIONS = ("barriers", "drivers")


def load_codebook(path: Optional[Path] = None,
                  repo_root: Optional[Path] = None) -> Dict[str, Any]:
    root = repo_root or find_repo_root()
    cb_path = path or (root / "docs" / "finder" / "data" / "wp1_codebook.json")
    return json.loads(cb_path.read_text(encoding="utf-8"))


#: Which corpus each snapshot file belongs to. Funded projects sit on the
#: funding side with call topics, because that is how the tool treats them:
#: both answer "what is being financed here".
CORPUS_SIDES = {
    "policies.json": "policy",
    "grants.json": "grant",
    "projects.json": "grant",
}


def corpus_sides(corpus_dir: Path) -> Dict[str, List[Dict[str, Any]]]:
    """A frozen corpus split into its policy and funding sides."""
    sides: Dict[str, List[Dict[str, Any]]] = {"policy": [], "grant": []}
    for name, side in CORPUS_SIDES.items():
        path = corpus_dir / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        sides[side].extend(payload.get("items") or [])
    return sides


def corpus_documents(corpus_dir: Path) -> List[Dict[str, Any]]:
    """Every document in a frozen corpus, whatever sources it holds."""
    sides = corpus_sides(corpus_dir)
    return sides["policy"] + sides["grant"]


def document_frequency(docs: Iterable[Dict[str, Any]],
                       terms: Iterable[str]) -> int:
    """How many documents any of ``terms`` matches.

    Matching mirrors the web app — a leading word boundary, case-insensitive —
    so a frequency computed here means the same thing as a hit in the tool. The
    keyword thesaurus is deliberately **not** applied: it was written as part of
    this tool, and expanding the study's query terms with it would make the test
    partly self-referential.
    """
    from .cordis import term_pattern

    pattern = term_pattern(terms)
    if pattern is None:
        return 0
    return sum(1 for doc in docs
               if pattern.search(str(doc.get("title") or "") + " "
                                 + str(doc.get("summary") or "")))


def select_queries(corpus_dir: Path,
                   codebook: Optional[Dict[str, Any]] = None,
                   dimensions: Iterable[str] = DEFAULT_DIMENSIONS,
                   max_df: float = DEFAULT_MAX_DF,
                   top: int = DEFAULT_TOP,
                   require_both: bool = False,
                   repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Apply the selection rule and show its working.

    Every candidate is reported with its document frequency and whether it was
    kept, dropped as too broad, or simply ranked below the cut. A rule whose
    output cannot be audited is indistinguishable from a choice.
    """
    codebook = codebook or load_codebook(repo_root=repo_root)
    sides = corpus_sides(Path(corpus_dir))
    docs = sides["policy"] + sides["grant"]
    total = len(docs)
    if not total:
        raise RuntimeError(f"no documents found in {corpus_dir}")

    candidates: List[Dict[str, Any]] = []
    for dimension in dimensions:
        for entry in codebook.get("dimensions", {}).get(dimension, []):
            terms = list(entry.get("terms") or [entry["code"]])
            hits = document_frequency(docs, terms)
            # Per-side counts, because a corpus-wide frequency hides which side
            # a term lives on. The funding side outnumbers the policy side
            # several times over, so a term can look well attested while being
            # absent from every act — and a term in only one corpus cannot
            # support any comparison between the two.
            candidates.append({
                "code": entry["code"],
                "dimension": dimension,
                "terms": terms,
                "papers": int(entry.get("papers") or 0),
                "documents": hits,
                "df": round(hits / total, 4),
                "policy_documents": document_frequency(sides["policy"], terms),
                "grant_documents": document_frequency(sides["grant"], terms),
            })

    for cand in candidates:
        cand["both_sides"] = bool(cand["policy_documents"] and cand["grant_documents"])
        if cand["df"] > max_df:
            cand["status"] = "dropped: too broad"
        elif cand["documents"] == 0:
            # A code absent from the corpus cannot be ranked against the others
            # on subsequent uptake, so it is not a usable query either.
            cand["status"] = "dropped: absent from corpus"
        elif require_both and not cand["both_sides"]:
            cand["status"] = "dropped: one side only"
        else:
            cand["status"] = "eligible"

    # Rank eligible codes by the codebook's paper count, ties alphabetically.
    eligible = sorted((c for c in candidates if c["status"] == "eligible"),
                      key=lambda c: (-c["papers"], c["code"]))
    for cand in eligible[top:]:
        cand["status"] = "eligible, below the cut"
    selected = eligible[:top]
    for rank, cand in enumerate(selected, start=1):
        cand["status"] = "selected"
        cand["rank"] = rank

    return {
        "corpus": str(corpus_dir),
        "documents": total,
        "documents_by_side": {"policy": len(sides["policy"]),
                              "grant": len(sides["grant"])},
        "rule": {"dimensions": list(dimensions), "max_df": max_df, "top": top,
                 "require_both_sides": require_both,
                 "tie_break": "alphabetical by code",
                 "matching": "leading word boundary, case-insensitive, no thesaurus"},
        "queries": [c["code"] for c in selected],
        # How many of the chosen queries exist on both sides at all. A low
        # number here means a bridge-versus-single-corpus comparison has
        # almost nothing to work with, whatever the outcome data later says.
        "selected_on_both_sides": sum(1 for c in selected if c["both_sides"]),
        "selected": selected,
        "candidates": sorted(candidates, key=lambda c: (-c["papers"], c["code"])),
        "short": len(selected) < top,
    }


def write_selection(out_path: Path, selection: Dict[str, Any]) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(selection, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    return out_path
