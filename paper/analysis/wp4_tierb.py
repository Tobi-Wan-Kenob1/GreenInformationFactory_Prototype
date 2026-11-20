#!/usr/bin/env python3
"""WP4 — the Tier B sampling frame, sample and per-organisation data.

Implements PROTOCOL.md Appendix B.4 (a dated deviation from registration §8,
decided before sampling). Tier B is illustrative mechanism evidence, never part
of the validation claim.

Writes, per arm: the ordered (query, topic) pairs and the frame they build,
the sample with its full reserve order, and for each sampled organisation its
CORDIS participations and GLEIF candidate records.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wp3_outcomes as O   # noqa: E402  (project reader shared with the registered run)

FRAME_MIN, FRAME_MAX = 200, 600
PER_ARM = 5
SEEDS = {"A1": 20091233, "A2": 20131233}
WINDOWS = {"A1": ("2010-01-01", "2012-12-31"), "A2": ("2014-01-01", "2016-12-31")}
TYPES = ("PRC", "HES", "REC", "PUB", "OTH")
GLEIF = "https://api.gleif.org/api/v1/lei-records"


# ---------------------------------------------------------------- pairs

def ordered_pairs(recording: Dict[str, Any], queries: List[str]) -> List[Dict[str, Any]]:
    """Bridge (query, topic) pairs by rank, ties by registered query order."""
    qorder = {q: i for i, q in enumerate(queries)}
    pairs = []
    for run in recording["runs"]:
        for scope in run["scopes"]:
            if scope["scope"] != "bridge":
                continue
            for t in scope["topics"]:
                if t["term"].strip().lower() == run["query"].strip().lower():
                    continue
                pairs.append({"query": run["query"], "topic": t["term"], "rank": t["rank"]})
    pairs.sort(key=lambda p: (p["rank"], qorder[p["query"]], p["topic"]))
    return pairs


# ---------------------------------------------------------------- organisations

def organisation_rows(members, cordis, programme: str) -> List[Dict[str, Any]]:
    entry = members.get("organization.csv")
    if not entry:
        return []
    rows, _ = cordis._rows_as_dicts(*entry)
    out = []
    for row in rows:
        pid = str(row.get("projectID") or "").strip()
        if not pid:
            continue
        oid = str(row.get("organisationID") or "").strip()
        name = cordis._clean(row.get("name"))
        key = oid or ("name:" + name.casefold())
        if key == "name:":
            continue
        out.append({"project": f"{programme}:{pid}", "key": key, "name": name,
                    "country": str(row.get("country") or "").strip().upper(),
                    "activityType": str(row.get("activityType") or "").strip().upper(),
                    "vatNumber": str(row.get("vatNumber") or "").strip(),
                    "url": str(row.get("organizationURL") or "").strip(),
                    "role": str(row.get("role") or "").strip(),
                    "ecContribution": O.parse_eur(row.get("ecContribution"))})
    return out


def build_frame(pairs, projects, org_rows, cordis) -> Dict[str, Any]:
    """Accumulate pairs in order into a frame of distinct organisations (B.4)."""
    by_project: Dict[str, List[Dict[str, Any]]] = {}
    for r in org_rows:
        by_project.setdefault(r["project"], []).append(r)

    used, frame_keys, log = [], set(), []
    stop_reason = "pairs exhausted below the minimum"
    for i, pair in enumerate(pairs):
        qp, tp = cordis.term_pattern([pair["query"]]), cordis.term_pattern([pair["topic"]])
        matched = [p["id"] for p in projects if qp.search(p["text"]) and tp.search(p["text"])]
        keys = {r["key"] for pid in matched for r in by_project.get(pid, [])}
        new_size = len(frame_keys | keys)
        entry = {**pair, "projects": len(matched), "organisations": len(keys), "frame_after": new_size}
        if new_size > FRAME_MAX:
            if not used:
                used.append(entry); frame_keys |= keys; entry["included"] = True
                stop_reason = "first pair alone exceeds the maximum; used alone"
            else:
                entry["included"] = False
                stop_reason = "next pair would exceed the maximum"
            log.append(entry)
            break
        entry["included"] = True
        used.append(entry); frame_keys |= keys; log.append(entry)
        if len(frame_keys) >= FRAME_MIN:
            stop_reason = "minimum reached"
            break
    included_projects = set()
    for e in used:
        qp, tp = cordis.term_pattern([e["query"]]), cordis.term_pattern([e["topic"]])
        included_projects |= {p["id"] for p in projects if qp.search(p["text"]) and tp.search(p["text"])}
    return {"pairs_considered": log, "k": len(used), "frame_size": len(frame_keys),
            "stop_reason": stop_reason, "frame_keys": frame_keys,
            "frame_projects": included_projects}


def frame_table(frame_keys, frame_projects, org_rows) -> List[Dict[str, Any]]:
    """One record per frame organisation, with its modal type and country."""
    agg: Dict[str, Dict[str, Any]] = {}
    for r in org_rows:
        if r["key"] in frame_keys and r["project"] in frame_projects:
            a = agg.setdefault(r["key"], {"key": r["key"], "names": Counter(), "types": Counter(),
                                          "countries": Counter(), "projects": set(), "urls": set(),
                                          "vat": set()})
            a["names"][r["name"]] += 1
            a["types"][r["activityType"] or "OTH"] += 1
            a["countries"][r["country"]] += 1
            a["projects"].add(r["project"])
            if r["url"]:
                a["urls"].add(r["url"])
            if r["vatNumber"]:
                a["vat"].add(r["vatNumber"])
    out = []
    for key in sorted(agg):
        a = agg[key]
        t = a["types"].most_common(1)[0][0]
        out.append({"key": key, "name": a["names"].most_common(1)[0][0],
                    "activityType": t if t in TYPES else "OTH",
                    "country": a["countries"].most_common(1)[0][0],
                    "frame_projects": sorted(a["projects"]), "urls": sorted(a["urls"]),
                    "vat": sorted(a["vat"])})
    return out


# ---------------------------------------------------------------- sample

def allocate(counts: Dict[str, int], n: int) -> Dict[str, int]:
    """Largest-remainder allocation of n across types, proportional to counts."""
    total = sum(counts.values())
    if not total:
        return {}
    quotas = {t: n * c / total for t, c in counts.items()}
    alloc = {t: math.floor(q) for t, q in quotas.items()}
    for t in sorted(quotas, key=lambda t: (-(quotas[t] - alloc[t]), t))[: n - sum(alloc.values())]:
        alloc[t] += 1
    return {t: a for t, a in alloc.items() if a}


def draw(frame: List[Dict[str, Any]], n: int, seed: int) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    """Stratified sample (B.4) and the full reserve order per type."""
    rng = np.random.default_rng(seed)
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for org in frame:
        by_type.setdefault(org["activityType"], []).append(org)
    order = {t: [orgs[i] for i in rng.permutation(len(orgs))] for t, orgs in sorted(by_type.items())}
    alloc = allocate({t: len(v) for t, v in by_type.items()}, n)
    sample, countries = [], set()
    for t in sorted(alloc):
        taken = 0
        pool = list(order[t])
        while taken < alloc[t] and pool:
            pick = next((o for o in pool if o["country"] not in countries), pool[0])
            pool.remove(pick)
            countries.add(pick["country"])
            sample.append({**pick, "stratum": t, "draw": len(sample) + 1})
            taken += 1
    reserve = {t: [o["key"] for o in order[t] if o["key"] not in {s["key"] for s in sample}]
               for t in order}
    return sample, {"allocation": alloc, "reserve": reserve}


# ---------------------------------------------------------------- per-organisation data

def participations(key: str, org_rows, projects_by_id) -> List[Dict[str, Any]]:
    out = []
    for r in org_rows:
        if r["key"] != key:
            continue
        p = projects_by_id.get(r["project"])
        out.append({"project": r["project"], "start": p["start"] if p else None,
                    "role": r["role"], "ecContribution": r["ecContribution"],
                    "title": (p["text"][:140] if p else None)})
    return sorted(out, key=lambda x: x["start"] or "")


def gleif_candidates(name: str, country: str, session=None) -> Dict[str, Any]:
    import requests
    s = session or requests.Session()
    params = {"filter[fulltext]": name, "page[size]": 5}
    if country and len(country) == 2:
        params["filter[entity.legalAddress.country]"] = "GB" if country == "UK" else country
    try:
        r = s.get(GLEIF, params=params, timeout=60)
        r.raise_for_status()
    except Exception as exc:                       # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    out = []
    for rec in r.json().get("data", []):
        a = rec["attributes"]
        out.append({"lei": a.get("lei"), "legalName": (a["entity"]["legalName"] or {}).get("name"),
                    "country": a["entity"]["legalAddress"].get("country"),
                    "entityStatus": a["entity"].get("status"),
                    "registrationStatus": a["registration"].get("status"),
                    "expiration": a["entity"].get("expiration")})
    return {"query": params, "candidates": out}


# ---------------------------------------------------------------- run

def run(data: Path, archives: Dict[str, bytes], out: Path, gleif=True) -> Dict[str, Any]:
    from gif import cordis

    projects, org_rows = [], []
    for prog in O.PROGRAMMES:
        members = cordis.read_csv_members(zipfile.ZipFile(io.BytesIO(archives[prog])))
        items, _ = O.outcome_projects(members, prog, cordis)
        projects.extend(items)
        org_rows.extend(organisation_rows(members, cordis, prog))
    by_id = {p["id"]: p for p in projects}
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for arm in ("A1", "A2"):
        rec = json.loads((data / f"frozen-{arm}" / "recorded.json").read_text())
        queries = json.loads((data / f"frozen-{arm}" / "queries.json").read_text())["queries"]
        since, until = WINDOWS[arm]
        window = O.in_window(projects, since, until)
        pairs = ordered_pairs(rec, queries)
        fr = build_frame(pairs, window, org_rows, cordis)
        table = frame_table(fr["frame_keys"], fr["frame_projects"], org_rows)
        sample, extra = draw(table, PER_ARM, SEEDS[arm])
        for s in sample:
            s["participations"] = participations(s["key"], org_rows, by_id)
            if gleif:
                s["gleif"] = gleif_candidates(s["name"], s["country"])
        payload = {"arm": arm, "protocol": "Appendix B.4", "window": [since, until],
                   "pairs_available": len(pairs), "pairs_considered": fr["pairs_considered"],
                   "k": fr["k"], "frame_size": fr["frame_size"], "stop_reason": fr["stop_reason"],
                   "frame_by_type": dict(Counter(o["activityType"] for o in table)),
                   "frame_countries": len({o["country"] for o in table}),
                   "seed": SEEDS[arm], **extra, "sample": sample,
                   "frame": [{k: o[k] for k in ("key", "name", "activityType", "country")} for o in table]}
        (out / f"tierb-{arm}.json").write_text(json.dumps(payload, indent=1, default=list) + "\n")
        summary[arm] = {k: payload[k] for k in ("k", "frame_size", "stop_reason", "frame_by_type",
                                                "frame_countries", "allocation")}
        summary[arm]["sample"] = [(s["name"], s["activityType"], s["country"]) for s in sample]
    (out / "TIERB.md").write_text(report(summary))
    return summary


def report(summary: Dict[str, Any]) -> str:
    L = ["# Tier B — frame and sample", "",
         "Illustrative case studies, not validation evidence. Frame rule: PROTOCOL.md Appendix B.4, a dated",
         "deviation from registration §8 decided before sampling. Generated by `paper/analysis/wp4_tierb.py`.", ""]
    for arm, s in summary.items():
        L += [f"## {arm}", "",
              f"- Pairs used (*k*): **{s['k']}**, frame **{s['frame_size']}** organisations "
              f"in {s['frame_countries']} countries — {s['stop_reason']}.",
              f"- Frame by type: {', '.join(f'{t} {n}' for t, n in sorted(s['frame_by_type'].items()))}.",
              f"- Allocation of {PER_ARM}: {', '.join(f'{t} {n}' for t, n in sorted(s['allocation'].items()))}.",
              "", "| # | Organisation | Type | Country |", "|---|---|---|---|"]
        L += [f"| {i} | {n} | {t} | {c} |" for i, (n, t, c) in enumerate(s["sample"], 1)]
        L.append("")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("paper/data"))
    ap.add_argument("--archives", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("paper/results/tierb"))
    ap.add_argument("--no-gleif", action="store_true")
    args = ap.parse_args(argv)
    from gif import cordis
    archives = {p: (args.archives / cordis.PROGRAMMES[p].rsplit("/", 1)[1]).read_bytes()
                for p in O.PROGRAMMES}
    summary = run(args.data, archives, args.out, gleif=not args.no_gleif)
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
