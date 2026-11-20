#!/usr/bin/env python3
"""WP3 — the outcome measures of the registered back-test.

Registered in PREREGISTRATION.md §6 (doi:10.17605/OSF.IO/QC2SP); the operational
detail the registration leaves open is fixed in PROTOCOL.md Appendix B.2, which
was committed together with this file, before any outcome data was retrieved.

For each arm and each unit — every topic term in the recorded tool output, and
every codebook code — this computes, over CORDIS FP7, H2020 and Horizon Europe
projects that *started* in the arm's outcome window:

* primary:   EC contribution to matching projects, as a share of the EC
             contribution of all projects starting in the window;
* secondary: matching project count; distinct participating organisations;
             matching EUR-Lex acts in the outcome window.

Matching is the tool's own ``gif.cordis.term_pattern`` — leading word boundary,
case-insensitive, no thesaurus — imported from the tool at the registered
commit rather than reimplemented, so it is the rule that selected the queries.

Nothing here computes a test statistic. ``wp3_analysis.py`` does that, from the
files this writes.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: The registered outcome programmes (registration, "Data collection procedures").
PROGRAMMES = ("fp7", "h2020", "horizon")

#: Outcome windows: the day after T to the end of 2026 (registration §3).
ARMS = {
    "A1": {"T": "2009-12-31", "since": "2010-01-01", "until": "2026-12-31"},
    "A2": {"T": "2013-12-31", "since": "2014-01-01", "until": "2026-12-31"},
}

RECORDINGS = ("recorded.json", "recorded-both-sides.json")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------

def topic_terms(arm_dir: Path) -> List[str]:
    """Every topic term the tool listed in either recording for this arm."""
    terms = set()
    for name in RECORDINGS:
        rec = json.loads((arm_dir / name).read_text(encoding="utf-8"))
        for run in rec["runs"]:
            for scope in run["scopes"]:
                for topic in scope["topics"]:
                    terms.add(topic["term"])
    return sorted(terms)


def codebook_codes(codebook: Dict[str, Any]) -> Dict[str, List[str]]:
    """``dimension:code`` → the code's terms, for all codebook dimensions."""
    out: Dict[str, List[str]] = {}
    for dim, entries in codebook["dimensions"].items():
        for entry in entries:
            out[f"{dim}:{entry['code']}"] = list(entry["terms"])
    return out


# --------------------------------------------------------------------------
# CORDIS
# --------------------------------------------------------------------------

def parse_eur(value: Any) -> Optional[float]:
    """An EC contribution as euros, or None when the field is empty or not a number.

    Same reading as the tool's ``normalize_project``: a decimal comma is a
    decimal point. A zero is a real zero, not a missing value.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def organisations_by_project(members, cordis) -> Dict[str, set]:
    """Project id → distinct organisation keys.

    The key is CORDIS's ``organisationID``; where that is empty, the
    case-folded organisation name, prefixed so the two never collide.
    """
    entry = members.get("organization.csv")
    if not entry:
        return {}
    rows, _ = cordis._rows_as_dicts(*entry)
    out: Dict[str, set] = {}
    for row in rows:
        pid = str(row.get("projectID") or "").strip()
        if not pid:
            continue
        oid = str(row.get("organisationID") or "").strip()
        key = oid or ("name:" + cordis._clean(row.get("name")).casefold())
        if key and key != "name:":
            out.setdefault(pid, set()).add(key)
    return out


def outcome_projects(members, programme: str, cordis) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Every project in one archive with a start date, as matchable records.

    Window filtering happens per arm, later; this reads the archive once.
    """
    entry = members.get("project.csv")
    if not entry:
        raise RuntimeError(f"{programme}: archive has no project.csv")
    rows, ragged = cordis._rows_as_dicts(*entry)
    topics = cordis.euroscivoc_by_project(members)
    orgs = organisations_by_project(members, cordis)

    out, seen = [], set()
    undated = duplicate = 0
    for row in rows:
        pid = str(row.get("id") or "").strip()
        if not pid or pid in seen:
            duplicate += 1
            continue
        seen.add(pid)
        start = cordis._iso(row.get("startDate"))
        if not start:
            undated += 1
            continue
        text = " ".join([cordis._clean(row.get("title")),
                         cordis._clean(row.get("objective")),
                         " ".join(topics.get(pid, []))])
        out.append({
            "id": f"{programme}:{pid}",
            "programme": programme,
            "start": start,
            "ec": parse_eur(row.get("ecMaxContribution")),
            "text": text,
            "orgs": orgs.get(pid, set()),
        })
    return out, {"rows": len(rows), "ragged": ragged, "undated": undated,
                 "duplicate_or_no_id": duplicate, "usable": len(out),
                 "with_euroscivoc": sum(1 for p in out if p["id"].split(":", 1)[1] in topics),
                 "with_organisations": sum(1 for p in out if p["orgs"])}


def in_window(projects: Iterable[Dict[str, Any]], since: str, until: str) -> List[Dict[str, Any]]:
    return [p for p in projects if since <= p["start"] <= until]


def project_uptake(projects: List[Dict[str, Any]],
                   units: Dict[str, List[str]], cordis) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Per unit: matched EC, share of the window's total, projects, organisations."""
    total_ec = sum(p["ec"] or 0.0 for p in projects)
    if total_ec <= 0:
        raise RuntimeError("total EC contribution in the window is zero; the archives did not load")
    out: Dict[str, Dict[str, Any]] = {}
    for key, terms in units.items():
        pattern = cordis.term_pattern(terms)
        matched = [p for p in projects if pattern is not None and pattern.search(p["text"])]
        ec = sum(p["ec"] or 0.0 for p in matched)
        out[key] = {
            "ec_eur": round(ec, 2),
            "share": ec / total_ec,
            "projects": len(matched),
            "projects_missing_ec": sum(1 for p in matched if p["ec"] is None),
            "organisations": len(set().union(*(p["orgs"] for p in matched))) if matched else 0,
        }
    denominator = {
        "projects": len(projects),
        "ec_eur": round(total_ec, 2),
        "projects_missing_ec": sum(1 for p in projects if p["ec"] is None),
        "by_programme": {prog: sum(1 for p in projects if p["programme"] == prog)
                         for prog in PROGRAMMES},
    }
    return out, denominator


# --------------------------------------------------------------------------
# EUR-Lex
# --------------------------------------------------------------------------

def outcome_acts(keywords: List[str], since: str, until: str, finder_data) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Acts in the outcome window, built exactly as the input corpus was.

    Same keywords, routine-act exclusion, EuroVoc threshold (none), act-text
    enrichment and 150-act budget spread over five-year slices. It is a sample,
    not a census, and is used only for a secondary measure.
    """
    failures: List[str] = []
    report: Dict[str, Any] = {}
    docs = finder_data.fetch_policies(keywords, since=since, until=until, limit=150,
                                      failures_out=failures, exclude_routine=True,
                                      min_subjects=0, enrich_text=True, report_out=report)
    if failures:
        raise RuntimeError(f"EUR-Lex answered only partly, refusing a partial outcome set: {failures}")
    docs = [d for d in docs if since <= (d.get("date") or "") <= until]
    return docs, report


def act_uptake(acts: List[Dict[str, Any]], units: Dict[str, List[str]], cordis) -> Dict[str, int]:
    texts = [str(a.get("title") or "") + " " + str(a.get("summary") or "") for a in acts]
    out = {}
    for key, terms in units.items():
        pattern = cordis.term_pattern(terms)
        out[key] = sum(1 for t in texts if pattern is not None and pattern.search(t))
    return out


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------

def run(data_dir: Path, codebook_path: Path, out_dir: Path,
        archives: Dict[str, bytes], arms: Iterable[str],
        fetch_acts=True, archive_urls: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    from gif import cordis, finder_data  # the tool, at the registered commit

    codebook = json.loads(codebook_path.read_text(encoding="utf-8"))
    codes = codebook_codes(codebook)

    projects: List[Dict[str, Any]] = []
    archive_report = {}
    for prog in PROGRAMMES:
        blob = archives[prog]
        members = cordis.read_csv_members(zipfile.ZipFile(io.BytesIO(blob)))
        items, counts = outcome_projects(members, prog, cordis)
        projects.extend(items)
        archive_report[prog] = {"url": (archive_urls or {}).get(prog), "bytes": len(blob),
                                "sha256": sha256_bytes(blob), **counts}
        print(f"{prog}: {counts}", flush=True)

    manifest: Dict[str, Any] = {
        "retrieved": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "programmes": list(PROGRAMMES),
        "archives": archive_report,
        "codebook": {"path": str(codebook_path), "sha256": sha256_bytes(codebook_path.read_bytes()),
                     "codes": len(codes)},
        "arms": {},
    }
    out_dir.mkdir(parents=True, exist_ok=True)

    for arm in arms:
        cfg = ARMS[arm]
        arm_dir = data_dir / f"frozen-{arm}"
        terms = topic_terms(arm_dir)
        topic_units = {t: [t] for t in terms}
        window = in_window(projects, cfg["since"], cfg["until"])
        topics_out, denominator = project_uptake(window, topic_units, cordis)
        codes_out, _ = project_uptake(window, codes, cordis)

        acts_report: Dict[str, Any] = {"fetched": False}
        if fetch_acts:
            keywords = json.loads((arm_dir / "manifest.json").read_text())["keywords"]
            acts, report = outcome_acts(keywords, cfg["since"], cfg["until"], finder_data)
            for key, n in act_uptake(acts, topic_units, cordis).items():
                topics_out[key]["acts"] = n
            for key, n in act_uptake(acts, codes, cordis).items():
                codes_out[key]["acts"] = n
            dates = sorted(a.get("date") or "" for a in acts)
            acts_report = {"fetched": True, "acts": len(acts), "keywords": keywords,
                           "earliest": dates[0] if dates else None,
                           "latest": dates[-1] if dates else None, "report": report}

        payload = {"arm": arm, "T": cfg["T"], "window": {"since": cfg["since"], "until": cfg["until"]},
                   "denominator": denominator, "acts": acts_report,
                   "topics": topics_out, "codes": codes_out}
        path = out_dir / f"outcomes-{arm}.json"
        path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        manifest["arms"][arm] = {"file": path.name, "sha256": sha256_bytes(path.read_bytes()),
                                 "topics": len(topics_out), "codes": len(codes_out),
                                 "window": payload["window"], "denominator": denominator,
                                 "acts": {k: v for k, v in acts_report.items() if k != "report"}}
        print(f"{arm}: {len(window)} projects in window, {len(terms)} topics, {len(codes)} codes",
              flush=True)

    (out_dir / "outcomes-manifest.json").write_text(json.dumps(manifest, indent=1) + "\n",
                                                   encoding="utf-8")
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=Path("paper/data"))
    ap.add_argument("--codebook", type=Path, required=True,
                    help="docs/finder/data/wp1_codebook.json at the registered tool commit")
    ap.add_argument("--out", type=Path, default=Path("paper/results"))
    ap.add_argument("--archives", type=Path, required=True,
                    help="directory holding cordis-{fp7,h2020,HORIZON}projects-csv.zip")
    ap.add_argument("--arms", default="A1,A2")
    ap.add_argument("--no-acts", action="store_true")
    args = ap.parse_args(argv)

    from gif import cordis
    archives, urls = {}, {}
    for prog in PROGRAMMES:
        url = cordis.PROGRAMMES[prog]
        archives[prog] = (args.archives / url.rsplit("/", 1)[1]).read_bytes()
        urls[prog] = url
    run(args.data, args.codebook, args.out, archives, args.arms.split(","),
        fetch_acts=not args.no_acts, archive_urls=urls)
    return 0


if __name__ == "__main__":
    sys.exit(main())
