#!/usr/bin/env python3
"""Score the two-rater relevance check (PROTOCOL.md B.7) from the returned workbooks.

    python paper/analysis/relevance_score.py R1.xlsx R2.xlsx

Precision per arm and side (a shared pair counts as the mean of the two
judgements); Cohen's kappa on the shared pairs with a percentile bootstrap
interval; disagreements listed. Refuses incomplete workbooks.
"""
import json
import sys
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

KEY = Path("paper/results/relevance/key.json")
OUT = Path("paper/results/relevance")
SEED, N_BOOT = 20261121, 10_000
VALUE = {"On-topic": 1, "Not on-topic": 0}


def read_workbook(path):
    ws = load_workbook(path, data_only=True)["Ratings"]
    out = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        if row[0] is None:
            continue
        item, judgement, note = int(row[0]), row[7], row[8]
        if judgement not in VALUE:
            raise SystemExit(f"{path}: item {item} has no valid judgement ({judgement!r})")
        out[item] = {"v": VALUE[judgement], "note": (note or "").strip()}
    return out


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    po = float(np.mean(a == b))
    pe = float(np.mean(a) * np.mean(b) + (1 - np.mean(a)) * (1 - np.mean(b)))
    return None if pe == 1 else (po - pe) / (1 - pe)


def main(r1_path, r2_path):
    key = json.loads(KEY.read_text())
    ratings = {"R1": read_workbook(r1_path), "R2": read_workbook(r2_path)}
    pairs = {}
    for k in key["items"]:
        j = ratings[k["rater"]].get(k["item"])
        if j is None:
            raise SystemExit(f"{k['rater']} item {k['item']} missing")
        pid = (k["arm"], k["query"], k["id"])
        p = pairs.setdefault(pid, {"arm": k["arm"], "side": k["side"], "query": k["query"], "id": k["id"],
                                   "shared": k["shared"], "judgements": {}})
        p["judgements"][k["rater"]] = j
    precision = {}
    for arm in ("A1", "A2"):
        for side in ("policy", "grant", "all"):
            sel = [p for p in pairs.values() if p["arm"] == arm and (side == "all" or p["side"] == side)]
            if sel:
                vals = [np.mean([j["v"] for j in p["judgements"].values()]) for p in sel]
                precision[f"{arm}/{side}"] = {"pairs": len(sel), "precision": float(np.mean(vals))}
    vals = [np.mean([j["v"] for j in p["judgements"].values()]) for p in pairs.values()]
    precision["both arms/all"] = {"pairs": len(vals), "precision": float(np.mean(vals))}
    shared = [p for p in pairs.values() if p["shared"]]
    a = [p["judgements"]["R1"]["v"] for p in shared]
    b = [p["judgements"]["R2"]["v"] for p in shared]
    k_obs = kappa(a, b)
    rng = np.random.default_rng(SEED)
    boot = [kappa(np.take(a, i), np.take(b, i)) for i in (rng.integers(0, len(a), len(a)) for _ in range(N_BOOT))]
    boot = np.array([x for x in boot if x is not None])
    ci = [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))] if len(boot) else [None, None]
    disagreements = [{"arm": p["arm"], "side": p["side"], "query": p["query"], "id": p["id"],
                      "R1": p["judgements"]["R1"], "R2": p["judgements"]["R2"]}
                     for p in shared if p["judgements"]["R1"]["v"] != p["judgements"]["R2"]["v"]]
    result = {"protocol": "Appendix B.7", "precision": precision,
              "agreement": {"shared_pairs": len(shared), "raw": float(np.mean(np.array(a) == np.array(b))),
                            "kappa": k_obs, "kappa_ci95": ci, "bootstrap_undefined": N_BOOT - len(boot)},
              "disagreements": disagreements}
    (OUT / "relevance-result.json").write_text(json.dumps(result, indent=1) + "\n")
    L = ["# Relevance check — result (protocol B.7)", "",
         "| Arm / side | Pairs | Precision |", "|---|---|---|"]
    L += [f"| {k} | {v['pairs']} | {v['precision']:.2f} |" for k, v in precision.items()]
    kk = "undefined" if k_obs is None else f"{k_obs:.2f}"
    L += ["", f"Agreement on {len(shared)} shared pairs: raw {result['agreement']['raw']:.2f}, "
              f"Cohen's κ = {kk} [{', '.join('—' if x is None else f'{x:.2f}' for x in ci)}].",
          f"Disagreements: {len(disagreements)} (listed in `relevance-result.json`)."]
    (OUT / "RELEVANCE.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
