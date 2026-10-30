"""Freeze a reproducible corpus for the Policy & Grant Finder.

``gif finder-data`` and ``gif cordis`` fetch what the EU endpoints hold *now*.
That is right for the live app and wrong for any claim that needs to be checked
later: the sources move. CELLAR gains acts, the Funding & Tenders index is
rebuilt, CORDIS reissues its archives weekly. Re-running a fetch with the same
arguments next month does not reliably return the same documents, so "the
corpus as of a past date" is not something a command can promise to reproduce.

What it can promise is a record. This module writes the fetched corpus **once**
into a directory, next to a manifest holding a SHA-256 per file, the counts, the
window asked for, the endpoints used and the tool's own commit. From then on the
corpus is checkable: anyone can hash the files and compare. That is the
difference between a frozen corpus and a re-run.

It also enforces the window rather than trusting it. With ``--until`` set, every
document is checked against it and the command fails if any postdates it,
listing the offenders. A corpus that is supposed to represent a past date and
quietly contains later documents is worse than no corpus, because nothing
downstream can detect it.

Run via ``gif freeze``.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from helper.utils import find_repo_root

#: Files a frozen corpus may contain, and the source each comes from.
CORPUS_SOURCES = {
    "policies.json": "EUR-Lex via CELLAR SPARQL (publications.europa.eu)",
    "grants.json": "EU Funding & Tenders search API (SEDIA)",
    "projects.json": "CORDIS project archives (cordis.europa.eu)",
}

MANIFEST_NAME = "manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_digest(items: List[Dict[str, Any]]) -> str:
    """A digest of the documents themselves, ignoring when they were written.

    The file hash answers "are these the same bytes", which is what verifying
    an archived corpus needs. It cannot answer "are these the same documents",
    because every snapshot embeds a ``generated`` timestamp: two runs that
    retrieved an identical 679 projects produced different file hashes purely
    from the clock. Without a content digest, "the corpus changed" and "the
    corpus was written again" are indistinguishable — and the first is a
    finding while the second is noise.

    Documents are sorted by id so retrieval order cannot affect the digest.
    """
    canonical = json.dumps(sorted(items, key=lambda d: str(d.get("id") or "")),
                           sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def tool_version(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """The tool's commit, and whether the tracked tree was modified.

    A corpus is only reproducible against a known version of the code that
    built it, and "dirty" matters as much as the hash: a corpus built from
    uncommitted changes cannot be reconstructed from the repository at all, so
    the manifest says so instead of implying a clean provenance.

    Only **tracked** modifications count. Untracked files were counted at first
    and the first real run came back dirty for an uninteresting reason: an
    editable install drops an ``egg-info`` directory in the tree. Flagging that
    as unreproducible would train the reader to ignore the flag, which is worse
    than not having one. Untracked files are reported as a count, so an
    unexpected pile of them is still visible without crying wolf.
    """
    root = repo_root or find_repo_root()
    out: Dict[str, Any] = {"commit": None, "dirty": None, "untracked": None}

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=30,
                              check=True).stdout

    try:
        out["commit"] = git("rev-parse", "HEAD").strip()
        tracked = git("status", "--porcelain", "--untracked-files=no").strip()
        out["dirty"] = bool(tracked)
        others = git("ls-files", "--others", "--exclude-standard").strip()
        out["untracked"] = len(others.splitlines()) if others else 0
    except Exception:                             # noqa: BLE001 - absence is reported
        pass
    return out


def _items(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("items") or [])


def check_window(corpus_dir: Path, until: Optional[str],
                 since: Optional[str] = None) -> Dict[str, Any]:
    """Every document's date against the window. Reports, does not raise.

    Undated documents are counted separately rather than lumped in with
    violations: with ``until`` set they must not be in a frozen corpus at all,
    but the reason is different (unknown, not late) and the distinction is
    worth keeping in the record.
    """
    violations: List[Dict[str, str]] = []
    undated: List[str] = []
    counted = 0
    for name in CORPUS_SOURCES:
        path = corpus_dir / name
        if not path.exists():
            continue
        for doc in _items(path):
            counted += 1
            doc_date = str(doc.get("date") or "")[:10]
            if not doc_date:
                undated.append(f"{name}:{doc.get('id')}")
                continue
            if until and doc_date > str(until)[:10]:
                violations.append({"file": name, "id": str(doc.get("id")),
                                   "date": doc_date})
            elif since and doc_date < str(since)[:10]:
                violations.append({"file": name, "id": str(doc.get("id")),
                                   "date": doc_date})
    return {"documents": counted, "violations": violations, "undated": undated}


def build_manifest(corpus_dir: Path, keywords: List[str],
                   since: Optional[str], until: Optional[str],
                   programmes: Optional[List[str]] = None,
                   label: Optional[str] = None,
                   repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Describe a corpus directory: checksums, counts, provenance, window."""
    files = []
    for name, source in CORPUS_SOURCES.items():
        path = corpus_dir / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = list(payload.get("items") or [])
        dates = sorted(str(d.get("date"))[:10] for d in items if d.get("date"))
        files.append({
            "name": name,
            "source": source,
            "sha256": sha256_file(path),
            "content_sha256": content_digest(items),
            "bytes": path.stat().st_size,
            "items": len(items),
            "earliest": dates[0] if dates else None,
            "latest": dates[-1] if dates else None,
            "generated": payload.get("generated"),
        })
    audit = check_window(corpus_dir, until, since)
    return {
        "label": label,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"since": since, "until": until},
        "keywords": list(keywords),
        "programmes": list(programmes or []),
        "tool": tool_version(repo_root),
        "files": files,
        "documents": audit["documents"],
        "window_violations": audit["violations"],
        "undated": audit["undated"],
    }


def write_manifest(corpus_dir: Path, manifest: Dict[str, Any]) -> Path:
    path = corpus_dir / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path


def verify(corpus_dir: Path) -> Dict[str, Any]:
    """Re-hash a corpus against its manifest. The point of freezing it."""
    manifest = json.loads((corpus_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    results, ok = [], True
    for entry in manifest.get("files") or []:
        path = corpus_dir / entry["name"]
        if not path.exists():
            results.append({"name": entry["name"], "status": "missing"})
            ok = False
            continue
        actual = sha256_file(path)
        matched = actual == entry.get("sha256")
        # Same documents, different bytes: a rewrite, not a change. Reported as
        # its own status so it is not mistaken for either a clean match or a
        # corpus that has actually been altered.
        same_content = (entry.get("content_sha256") is not None
                        and content_digest(_items(path)) == entry["content_sha256"])
        if matched:
            status = "ok"
        elif same_content:
            status = "rewritten"
        else:
            status = "CHANGED"
        ok = ok and (matched or same_content)
        results.append({"name": entry["name"], "status": status,
                        "expected": entry.get("sha256"), "actual": actual})
    return {"ok": ok, "label": manifest.get("label"),
            "created": manifest.get("created"), "files": results}


def freeze(out_dir: Path,
           since: Optional[str] = None,
           until: Optional[str] = None,
           keywords: Optional[List[str]] = None,
           programmes: Optional[Iterable[str]] = None,
           label: Optional[str] = None,
           skip_projects: bool = False,
           allow_partial: bool = False) -> Dict[str, Any]:
    """Fetch every source into ``out_dir`` and write the manifest.

    Raises in two cases, both of which produce a corpus that cannot carry the
    meaning its label claims:

    * **The window is breached.** A corpus containing documents from after its
      cut-off is not a record of a past date.
    * **A source failed partially.** Some keywords, or some date slices, came
      back as errors while others succeeded. The corpus is then an unknown
      fraction of the period and its size says nothing — two runs minutes apart
      returned 148 and 111 policies for the same window, and without this check
      both would have been recorded as complete. ``allow_partial`` keeps the
      corpus anyway and leaves the failures in the manifest, which is the right
      choice only when a source is known to be permanently degraded and the
      incompleteness is going to be reported.

    The manifest is written before either check, so a rejected corpus can be
    inspected rather than merely described by an exception.
    """
    from .cordis import DEFAULT_PROGRAMMES, build_projects
    from .finder_data import build_snapshot, load_snapshot_keywords

    root = find_repo_root()
    keywords = keywords if keywords is not None else load_snapshot_keywords(root)
    programmes = list(programmes or DEFAULT_PROGRAMMES)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: Dict[str, str] = {}
    snapshot = build_snapshot(keywords=list(keywords), out_dir=out_dir,
                              since=since or "1990-01-01", until=until)
    errors.update(snapshot.get("errors") or {})
    partial: Dict[str, List[str]] = dict(snapshot.get("partial") or {})

    projects: Dict[str, Any] = {}
    if not skip_projects:
        try:
            projects = build_projects(programmes=programmes, keywords=list(keywords),
                                      out_dir=out_dir, as_of=until, since=since)
        except Exception as exc:                  # noqa: BLE001 - reported below
            errors["projects"] = f"{type(exc).__name__}: {exc}"

    manifest = build_manifest(out_dir, list(keywords), since, until,
                              programmes=programmes, label=label, repo_root=root)
    manifest["errors"] = errors
    manifest["partial_failures"] = partial
    manifest["complete"] = not partial and not errors
    path = write_manifest(out_dir, manifest)

    if manifest["window_violations"]:
        breaches = manifest["window_violations"]
        raise RuntimeError(
            f"{len(breaches)} document(s) fall outside {since or 'any'}..{until or 'any'} — "
            f"the corpus is not a record of that period. First few: "
            + "; ".join(f"{b['file']}:{b['id']}@{b['date']}" for b in breaches[:5]))

    if partial and not allow_partial:
        detail = "; ".join(f"{src}: {len(items)} failure(s) — {items[0]}"
                           for src, items in partial.items())
        raise RuntimeError(
            "a source failed partially, so this corpus is an unknown fraction of "
            f"the period and its size means nothing: {detail}. Re-run, or pass "
            "allow_partial to keep it and report the incompleteness.")

    return {
        "label": label,
        "dir": str(out_dir),
        "manifest": str(path),
        "documents": manifest["documents"],
        "files": manifest["files"],
        "undated": len(manifest["undated"]),
        "complete": manifest["complete"],
        "partial_failures": partial,
        "errors": errors,
        "projects": projects.get("projects") if projects else None,
        "generated": date.today().isoformat(),
    }
