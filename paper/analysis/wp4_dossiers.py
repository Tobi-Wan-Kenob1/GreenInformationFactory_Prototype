#!/usr/bin/env python3
"""WP4 — one case dossier per sampled Tier B organisation.

Turns ``results/tierb-scoped/tierb-<arm>.json`` into ``paper/cases/<arm>-<n>-<slug>.md``:
what the registers already say about the organisation, laid out as the starting
point for the case work, with the parts that need desk research left as
explicit, empty headings. Nothing here infers status, size or performance.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

T = {"A1": "2009-12-31", "A2": "2013-12-31"}
FIRST_YEARS = {"A1": ("2010-01-01", "2012-12-31"), "A2": ("2014-01-01", "2016-12-31")}
TYPE_NAMES = {"PRC": "private for-profit", "HES": "higher education", "REC": "research organisation",
              "PUB": "public body", "OTH": "other"}


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


def euros(v) -> str:
    return "—" if v is None else f"€{v:,.0f}"


def funding_phases(parts: List[Dict[str, Any]], arm: str) -> Dict[str, Any]:
    """Participations and EC contribution before T, in the first three years, and later."""
    lo, hi = FIRST_YEARS[arm]
    tests = {"before T": lambda d: d <= T[arm],
             "first three years": lambda d: lo <= d <= hi,
             "later": lambda d: d > hi}
    out = {}
    for label, test in tests.items():
        sel = [p for p in parts if p["start"] and test(p["start"])]
        out[label] = {"n": len(sel), "ec": sum(p["ecContribution"] or 0 for p in sel)}
    return out


def dossier(org: Dict[str, Any], arm: str, payload: Dict[str, Any]) -> str:
    pair = next((p for p in payload["pairs_considered"] if p["included"]), None)
    phases = funding_phases(org["participations"], arm)
    g = org.get("gleif") or {}
    L = [f"# {org['name']}", "",
         f"**Tier B case {arm}-{org['draw']}** · illustrative, not validation evidence · "
         f"sampled under PROTOCOL.md {payload['protocol']}", "",
         "| | |", "|---|---|",
         f"| CORDIS key | `{org['key']}` |",
         f"| Type (stratum) | {org['activityType']} — {TYPE_NAMES.get(org['activityType'], '')} |",
         f"| Country | {org['country']} |",
         f"| Web (CORDIS) | {', '.join(org.get('urls') or []) or '—'} |",
         f"| VAT (CORDIS) | {', '.join(org.get('vat') or []) or '—'} |",
         f"| Sampled via | *{pair['topic']}* within *{pair['query']}* (rank {pair['rank']}), "
         f"projects starting {FIRST_YEARS[arm][0][:4]}–{FIRST_YEARS[arm][1][:4]} |" if pair else "| Sampled via | — |",
         f"| Frame projects | {', '.join(org.get('frame_projects') or [])} |", "",
         "## What the registers already say", "",
         f"### EU funding, FP7 onward (CORDIS) — {len(org['participations'])} participations", "",
         "| Phase | Participations | EC contribution |", "|---|---|---|"]
    L += [f"| {k} | {v['n']} | {euros(v['ec'])} |" for k, v in phases.items()]
    L += ["", "| Start | Project | Role | EC contribution | Title / objective (start) |", "|---|---|---|---|---|"]
    for p in org["participations"]:
        title = (p.get("title") or "").replace("|", "/")
        L.append(f"| {p['start'] or '—'} | `{p['project']}` | {p['role'] or '—'} | "
                 f"{euros(p['ecContribution'])} | {title} |")
    L += ["", "### Legal entity (GLEIF) — candidates only, unverified", ""]
    if g.get("error"):
        L.append(f"Lookup failed: {g['error']}")
    elif not g.get("candidates"):
        L.append("No LEI record matched the name and country. Many organisations have none; "
                 "absence says nothing about survival.")
    else:
        L += ["| LEI | Legal name | Country | Entity status | Registration |", "|---|---|---|---|---|"]
        L += [f"| `{c['lei']}` | {c['legalName']} | {c['country']} | {c['entityStatus']} | "
              f"{c['registrationStatus']} |" for c in g["candidates"]]
        L += ["", "A fuzzy name search: confirm the right entity before using any status."]
    L += ["", "## Case work — to be completed", "",
          "Past (*T* = " + T[arm] + ") versus present, within the limits of PROTOCOL.md §9.2. "
          "No causal attribution (§9.3).", "",
          "### Status", "- [ ] Still operating, merged, renamed, dissolved or exited? Source and date:",
          "- [ ] If dissolved or exited: it stays in the sample (B.4); note when and how.", "",
          "### Economic", "- [ ] Trajectory since *T* (from own reporting, registers, the funding table above):",
          "- [ ] Size, where it matters, from the organisation's own filings (not a sampling property):", "",
          "### Social", "- [ ] Regional context (NUTS-2 employment; agricultural cases only, §9.2):",
          "- [ ] Project-reported social outcomes:", "",
          "### Environmental", "- [ ] ETS-covered installation? If so, verified emissions 2005–2025 (EEA Union Registry):",
          "- [ ] Otherwise, own reporting, flagged as such:", "",
          "### Mechanism", "- [ ] What, if anything, connects the sampled topic to what the organisation did after *T*?", "",
          "### Sources", "- ", ""]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tierb", type=Path, default=Path("paper/results/tierb-scoped"))
    ap.add_argument("--out", type=Path, default=Path("paper/cases"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    index = ["# Tier B case dossiers", "",
             f"Generated by `paper/analysis/wp4_dossiers.py` from `{args.tierb}`. The register sections are",
             "generated; the case-work sections are filled in by hand and dated.", "",
             "| Case | Organisation | Type | Country | Participations |", "|---|---|---|---|---|"]
    for arm in ("A1", "A2"):
        payload = json.loads((args.tierb / f"tierb-{arm}.json").read_text())
        for org in payload["sample"]:
            name = f"{arm}-{org['draw']:02d}-{slug(org['name'])}.md"
            (args.out / name).write_text(dossier(org, arm, payload), encoding="utf-8")
            index.append(f"| [{arm}-{org['draw']}]({name}) | {org['name']} | {org['activityType']} | "
                         f"{org['country']} | {len(org['participations'])} |")
    (args.out / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print("\n".join(index))
    return 0


if __name__ == "__main__":
    sys.exit(main())
