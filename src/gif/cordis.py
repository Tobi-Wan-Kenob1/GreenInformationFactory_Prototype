"""CORDIS adapter for the Policy & Grant Finder (``docs/finder/``).

The finder's grant side comes from the EU Funding & Tenders search API, which
indexes **Horizon 2020 onward**. Anything earlier is simply absent, so the tool
could not look at a period before roughly 2014 — which also made it useless for
benchmarking a past setting against what came later.

CORDIS fills that in. It publishes every framework programme as a CSV archive,
back to FP1 (1984), each one carrying the fields the finder needs: a title, an
objective to read, an EC contribution, and dates. This module turns those
archives into the same document shape the rest of the finder speaks, so a
funded project sits beside a call topic and an act without the app knowing the
difference.

What a CORDIS record is, and is not: a **project**, i.e. an award already made,
not an invitation to apply. That makes it the right evidence for "what is
already being financed in this area" and the wrong evidence for "what can I
apply to". Projects therefore carry ``doctype: "Funded project"`` and no
deadline, and the app shows them as the past-facing records they are.

Observed schema, measured rather than assumed (2026-10-30):

* ``project.csv`` is 20 columns and identical across FP6 and FP7. FP6 nests its
  files under ``csv/``; FP7 and later do not.
* ``ecSignatureDate`` **exists but is empty** for FP6 and FP7, so the date a
  project became public knowledge has to be taken from ``startDate``.
* Both archives contain ragged rows — a few hundred in each — which a reader
  that assumes a clean CSV will either crash on or silently mis-attribute.
* ``euroSciVoc.csv`` carries topical classification for every programme and is
  worth folding into the summary; it is the one independent topic label in the
  data.

Run via ``gif cordis``.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from helper.utils import find_repo_root

CORDIS_BASE = "https://cordis.europa.eu/data"
TIMEOUT = 300

#: Programme → bulk CSV archive. Keys are what ``--programmes`` accepts.
PROGRAMMES: Dict[str, str] = {
    "fp5": f"{CORDIS_BASE}/cordis-fp5projects-csv.zip",
    "fp6": f"{CORDIS_BASE}/cordis-fp6projects-csv.zip",
    "fp7": f"{CORDIS_BASE}/cordis-fp7projects-csv.zip",
    "h2020": f"{CORDIS_BASE}/cordis-h2020projects-csv.zip",
    "horizon": f"{CORDIS_BASE}/cordis-HORIZONprojects-csv.zip",
}

#: Default selection: the programmes that reach below the Funding & Tenders
#: API's coverage, plus the ones that overlap it with richer metadata.
DEFAULT_PROGRAMMES = ["fp6", "fp7", "h2020", "horizon"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _clean(text: Any) -> str:
    """Collapse whitespace; CORDIS objectives contain newlines and tabs."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _iso(value: Any) -> Optional[str]:
    """A CORDIS date as ``YYYY-MM-DD``, or None if it is not one.

    Only the ISO prefix is trusted. A column that should hold a date but holds
    a programme name is a mis-split row, not a date, and must not become one.
    """
    text = str(value or "").strip()
    return text[:10] if DATE_RE.match(text) else None


def read_csv_members(archive: zipfile.ZipFile) -> Dict[str, Tuple[List[str], List[List[str]]]]:
    """Every CSV in the archive as ``name -> (header, rows)``.

    Names are reduced to their basename, which is what lets FP6 (``csv/``
    prefixed) and FP7 (flat) be read by the same code. Rows whose length does
    not match the header are dropped and counted by the caller: CORDIS archives
    contain a few hundred of them, and a ragged row read positionally puts an
    objective where a date belongs.
    """
    out: Dict[str, Tuple[List[str], List[List[str]]]] = {}
    for member in archive.namelist():
        if not member.lower().endswith(".csv"):
            continue
        with archive.open(member) as handle:
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            reader = csv.reader(text, delimiter=";")
            try:
                header = next(reader)
            except StopIteration:
                continue
            if len(header) == 1:                  # the file is comma-separated
                text.seek(0)
                reader = csv.reader(text, delimiter=",")
                header = next(reader)
            rows = list(reader)
        out[Path(member).name.lower()] = (header, rows)
    return out


def _column_index(header: Iterable[str]) -> Dict[str, int]:
    return {name.strip().lower(): i for i, name in enumerate(header)}


def _rows_as_dicts(header: List[str], rows: List[List[str]]) -> Tuple[List[Dict[str, str]], int]:
    """Well-formed rows as dicts, plus how many ragged rows were discarded."""
    width = len(header)
    names = [h.strip() for h in header]
    good, ragged = [], 0
    for row in rows:
        if len(row) != width:
            ragged += 1
            continue
        good.append(dict(zip(names, row)))
    return good, ragged


def euroscivoc_by_project(members: Dict[str, Tuple[List[str], List[List[str]]]]
                          ) -> Dict[str, List[str]]:
    """Project id → euroSciVoc topic titles, if the archive carries them."""
    entry = members.get("euroscivoc.csv")
    if not entry:
        return {}
    rows, _ = _rows_as_dicts(*entry)
    out: Dict[str, List[str]] = {}
    for row in rows:
        pid = str(row.get("projectID") or "").strip()
        title = _clean(row.get("euroSciVocTitle"))
        if pid and title and title not in out.setdefault(pid, []):
            out[pid].append(title)
    return out


def normalize_project(row: Dict[str, str], programme: str,
                      topics: Optional[List[str]] = None) -> Dict[str, Any]:
    """One ``project.csv`` row → finder document."""
    pid = str(row.get("id") or "").strip()
    objective = _clean(row.get("objective"))
    acronym = _clean(row.get("acronym"))
    title = _clean(row.get("title")) or acronym or pid

    summary = objective[:600]
    if topics:
        summary = (summary + " · " + ", ".join(topics[:8])).strip(" ·")

    contribution = row.get("ecMaxContribution") or ""
    try:
        budget = int(round(float(str(contribution).replace(",", ".")))) or None
    except (TypeError, ValueError):
        budget = None

    return {
        "id": f"c:{programme}:{pid}",
        "kind": "grant",
        "title": title,
        "summary": summary,
        # The award date. See the module docstring: ecSignatureDate is empty in
        # the older programmes, so startDate is what there is.
        "date": _iso(row.get("startDate")),
        "endDate": _iso(row.get("endDate")),
        # A project has no deadline to apply to; leaving the key present but
        # empty keeps the shape uniform for the app's renderer.
        "deadline": None,
        "status": _clean(row.get("status")) or None,
        "callId": _clean(row.get("masterCall")) or None,
        "programmePeriod": _clean(row.get("frameworkProgramme")) or programme.upper(),
        "acronym": acronym or None,
        "url": f"https://cordis.europa.eu/project/id/{pid}" if pid else "",
        "budgetEUR": budget,
        "doctype": "Funded project",
        "level": "EU",
        "source": "cache",
    }


def available_at(doc: Dict[str, Any], as_of: Optional[str]) -> bool:
    """Whether a project was public knowledge on ``as_of``.

    A project is knowable once its grant agreement is signed, and signature
    always precedes the start date, so ``startDate <= as_of`` is a sufficient
    condition: anything starting by then was certainly awarded by then. It is
    not a necessary one — a project signed just before the cut-off but starting
    after it is excluded — which makes the filter conservative. That is the
    right direction of error here: it can drop a record the tool could have
    seen, but it can never admit one the tool could not have seen.

    Projects with no usable start date are excluded whenever ``as_of`` is set,
    for the same reason: absence of evidence is not evidence of being in time.
    """
    if not as_of:
        return True
    start = doc.get("date")
    return bool(start) and start <= str(as_of)[:10]


def fetch_archive(url: str, timeout: int = TIMEOUT) -> zipfile.ZipFile:
    """Download one CORDIS archive into memory."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return zipfile.ZipFile(io.BytesIO(resp.content))


def projects_from_archive(archive: zipfile.ZipFile, programme: str,
                          keywords: Optional[Iterable[str]] = None,
                          as_of: Optional[str] = None,
                          since: Optional[str] = None) -> Dict[str, Any]:
    """Normalise one archive's projects, with keyword and date filtering.

    Returns the documents and a report of what was discarded and why, because
    "3 of 25785 projects matched" is far more often a wrong filter than a true
    finding, and a silent count hides that.
    """
    members = read_csv_members(archive)
    entry = members.get("project.csv")
    if not entry:
        raise RuntimeError(f"{programme}: archive has no project.csv "
                           f"(members: {', '.join(sorted(members)) or 'none'})")
    rows, ragged = _rows_as_dicts(*entry)
    topics = euroscivoc_by_project(members)

    terms = [str(k).lower() for k in (keywords or []) if str(k).strip()]
    docs: List[Dict[str, Any]] = []
    dropped_keyword = dropped_window = 0

    for row in rows:
        pid = str(row.get("id") or "").strip()
        doc = normalize_project(row, programme, topics.get(pid))
        if terms:
            haystack = (doc["title"] + " " + doc["summary"]).lower()
            if not any(term in haystack for term in terms):
                dropped_keyword += 1
                continue
        if not available_at(doc, as_of) or (since and (doc["date"] or "") < since[:10]):
            dropped_window += 1
            continue
        docs.append(doc)

    docs.sort(key=lambda d: d.get("date") or "", reverse=True)
    return {
        "programme": programme,
        "items": docs,
        "projects_in_archive": len(rows),
        "ragged_rows": ragged,
        "dropped_keyword": dropped_keyword,
        "dropped_window": dropped_window,
        "with_euroscivoc": sum(1 for d in docs if " · " in d["summary"]),
    }


def fetch_projects(programmes: Optional[Iterable[str]] = None,
                   keywords: Optional[Iterable[str]] = None,
                   as_of: Optional[str] = None,
                   since: Optional[str] = None) -> Dict[str, Any]:
    """Fetch and normalise several programmes. One failure does not stop the rest."""
    names = [str(p).lower() for p in (programmes or DEFAULT_PROGRAMMES)]
    unknown = [p for p in names if p not in PROGRAMMES]
    if unknown:
        raise ValueError(f"unknown programme(s): {', '.join(unknown)}; "
                         f"choose from {', '.join(PROGRAMMES)}")

    docs: List[Dict[str, Any]] = []
    reports: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    for name in names:
        try:
            archive = fetch_archive(PROGRAMMES[name])
            report = projects_from_archive(archive, name, keywords=keywords,
                                           as_of=as_of, since=since)
        except Exception as exc:                  # noqa: BLE001 - reported, not raised
            errors[name] = f"{type(exc).__name__}: {exc}"
            continue
        docs.extend(report.pop("items"))
        reports.append(report)

    if errors and not docs:
        raise RuntimeError("every programme failed — "
                           + "; ".join(f"{k}: {v}" for k, v in errors.items()))
    docs.sort(key=lambda d: d.get("date") or "", reverse=True)
    return {"items": docs, "programmes": reports, "errors": errors}


def write_projects(out_dir: Path, items: List[Dict[str, Any]],
                   keywords: Optional[List[str]] = None,
                   as_of: Optional[str] = None,
                   since: Optional[str] = None) -> Path:
    """Write ``projects.json`` beside the finder's other snapshots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "projects.json"
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "keywords": list(keywords or []),
        "window": {"since": since, "until": as_of},
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    return path


def build_projects(programmes: Optional[Iterable[str]] = None,
                   keywords: Optional[List[str]] = None,
                   out_dir: Optional[Path] = None,
                   as_of: Optional[str] = None,
                   since: Optional[str] = None) -> Dict[str, Any]:
    """Fetch CORDIS projects and write the snapshot. Returns a report."""
    from .finder_data import load_snapshot_keywords

    root = find_repo_root()
    keywords = keywords if keywords is not None else load_snapshot_keywords(root)
    out = out_dir or (root / "docs" / "finder" / "data")

    result = fetch_projects(programmes=programmes, keywords=keywords,
                            as_of=as_of, since=since)
    path = write_projects(out, result["items"], keywords=keywords,
                          as_of=as_of, since=since)
    return {
        "keywords": keywords,
        "window": {"since": since, "until": as_of},
        "projects": len(result["items"]),
        "programmes": result["programmes"],
        "errors": result["errors"],
        "file": str(path),
        "generated": date.today().isoformat(),
    }
