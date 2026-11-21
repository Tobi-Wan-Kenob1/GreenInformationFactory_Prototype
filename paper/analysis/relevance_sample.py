#!/usr/bin/env python3
"""The two-rater relevance sample (PROTOCOL.md B.7).

Reads the returned-document recordings and the frozen corpora, draws the
stratified sample, assigns it to two raters with 20 shared pairs, and writes
one blinded item list per rater plus a key that links items to arms and sides.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

PER_ARM, PER_SIDE, SHARED_PER_ARM = 50, 25, 10
SEEDS = {"A1": 20091235, "A2": 20131235}
ASSIGN_SEED = 20261121
CORPUS_FILES = {"policy": ("policies.json",), "grant": ("grants.json", "projects.json")}


def corpus_index(arm_dir: Path) -> Dict[str, Dict[str, Any]]:
    out = {}
    for files in CORPUS_FILES.values():
        for name in files:
            path = arm_dir / name
            if path.exists():
                for d in json.loads(path.read_text(encoding="utf-8")).get("items") or []:
                    out[d["id"]] = d
    return out


def pairs_for_arm(returned: Dict[str, Any]) -> Dict[str, List[Dict[str, str]]]:
    by_side: Dict[str, List[Dict[str, str]]] = {"policy": [], "grant": []}
    for run in returned["runs"]:
        for doc in run["returned"] or []:
            by_side.setdefault(doc["kind"], []).append({"query": run["query"], "id": doc["id"]})
    return by_side


def draw_arm(by_side: Dict[str, List[Dict[str, str]]], seed: int) -> List[Dict[str, str]]:
    rng = np.random.default_rng(seed)
    want = {"policy": PER_SIDE, "grant": PER_SIDE}
    have = {s: len(v) for s, v in by_side.items()}
    short = {s: max(0, want[s] - have.get(s, 0)) for s in want}
    want["grant"] += short["policy"]
    want["policy"] += short["grant"]
    out = []
    for side in ("policy", "grant"):
        pool = by_side.get(side, [])
        k = min(want[side], len(pool))
        for i in sorted(rng.choice(len(pool), size=k, replace=False)) if k else []:
            out.append({**pool[i], "side": side})
    return out


def assign(sample: Dict[str, List[Dict[str, str]]]) -> Dict[str, List[Dict[str, str]]]:
    rng = np.random.default_rng(ASSIGN_SEED)
    r1, r2 = [], []
    for arm in sorted(sample):
        items = [dict(x, arm=arm) for x in sample[arm]]
        order = rng.permutation(len(items))
        shared = [items[i] for i in order[:SHARED_PER_ARM]]
        rest = [items[i] for i in order[SHARED_PER_ARM:]]
        for x in shared:
            x["shared"] = True
        half = len(rest) // 2
        r1 += shared + rest[:half]
        r2 += shared + rest[half:]
    return {"R1": [r1[i] for i in rng.permutation(len(r1))],
            "R2": [r2[i] for i in rng.permutation(len(r2))]}


def blinded(item: Dict[str, Any], doc: Dict[str, Any], n: int) -> Dict[str, Any]:
    return {"item": n, "query": item["query"],
            "type": "EU act" if item["side"] == "policy" else "EU funding record",
            "title": doc.get("title") or "", "summary": doc.get("summary") or "",
            "date": doc.get("date"), "url": doc.get("url") or ""}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("paper/data"))
    ap.add_argument("--out", type=Path, default=Path("paper/results/relevance"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    sample, docs, available = {}, {}, {}
    for arm in ("A1", "A2"):
        arm_dir = args.data / f"frozen-{arm}"
        returned = json.loads((arm_dir / "returned.json").read_text())
        by_side = pairs_for_arm(returned)
        available[arm] = {s: len(v) for s, v in by_side.items()}
        sample[arm] = draw_arm(by_side, SEEDS[arm])
        docs[arm] = corpus_index(arm_dir)
    raters = assign(sample)
    key = []
    for rater, items in raters.items():
        sheet = []
        for n, it in enumerate(items, 1):
            doc = docs[it["arm"]][it["id"]]
            sheet.append(blinded(it, doc, n))
            key.append({"rater": rater, "item": n, "arm": it["arm"], "side": it["side"],
                        "query": it["query"], "id": it["id"], "shared": bool(it.get("shared"))})
        (args.out / f"items-{rater}.json").write_text(json.dumps(sheet, indent=1, ensure_ascii=False) + "\n")
    (args.out / "key.json").write_text(json.dumps(
        {"protocol": "Appendix B.7", "available_pairs": available,
         "sampled": {a: {s: sum(1 for x in v if x["side"] == s) for s in ("policy", "grant")}
                     for a, v in sample.items()},
         "items": key}, indent=1) + "\n")
    print(json.dumps({"available": available,
                      "sampled": {a: len(v) for a, v in sample.items()},
                      "per_rater": {r: len(v) for r, v in raters.items()},
                      "shared": sum(1 for k in key if k["shared"]) // 2}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
