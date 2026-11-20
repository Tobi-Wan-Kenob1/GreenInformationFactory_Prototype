#!/usr/bin/env python3
"""Exploratory C.1 — do H3 and H4 survive controlling for input term frequency?

Specified in PROTOCOL.md Appendix C.1 and committed before it was run. Not
registered; everything it writes is labelled exploratory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wp3_analysis as A    # noqa: E402  (unit definitions, shared with the registered run)
import wp3_outcomes as O    # noqa: E402

N_DRAWS = 10_000
SEEDS = {"A1": 20091232, "A2": 20131232}


def input_frequency(arm_dir: Path, units: Dict[str, List[str]]) -> Dict[str, int]:
    from gif.codebook_queries import corpus_documents, document_frequency
    docs = corpus_documents(arm_dir)
    return {k: document_frequency(docs, terms) for k, terms in units.items()}


def _resid(v: np.ndarray, z: np.ndarray) -> np.ndarray:
    X = np.column_stack([np.ones_like(z), z])
    beta, *_ = np.linalg.lstsq(X, v, rcond=None)
    return v - X @ beta


def partial_r(cls: np.ndarray, uptake: np.ndarray, freq: np.ndarray) -> Optional[float]:
    y, z = stats.rankdata(uptake), stats.rankdata(freq)
    rx, ry = _resid(cls.astype(float), z), _resid(y, z)
    if np.allclose(rx, 0) or np.allclose(ry, 0):
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def terciles(freq: np.ndarray) -> np.ndarray:
    r = stats.rankdata(freq)
    return np.minimum(2, ((r - 1) * 3 // len(r)).astype(int))


def analyse(cls, uptake, freq, sign: int, rng) -> Dict:
    cls, uptake, freq = (np.asarray(a, float) for a in (cls, uptake, freq))
    strata = terciles(freq)
    obs = partial_r(cls, uptake, freq)
    out = {"n": [int(cls.sum()), int(len(cls) - cls.sum())],
           "spearman_freq_uptake": float(stats.spearmanr(freq, uptake)[0]),
           "freq_by_class": {
               lab: {"min": float(freq[cls == v].min()), "median": float(np.median(freq[cls == v])),
                     "max": float(freq[cls == v].max()),
                     "per_tercile": [int(np.sum((cls == v) & (strata == t))) for t in range(3)]}
               for lab, v in (("class_1", 1), ("class_0", 0)) if np.any(cls == v)},
           "within_tercile_superiority": []}
    for t in range(3):
        a, b = uptake[(cls == 1) & (strata == t)], uptake[(cls == 0) & (strata == t)]
        out["within_tercile_superiority"].append(
            None if not len(a) or not len(b) else float(A.superiority(a, b)))
    overlap = all(c is not None for c in out["within_tercile_superiority"])
    out["overlap_in_every_tercile"] = overlap
    if obs is None:
        out.update({"partial_r": None, "p": None, "ci95": None,
                    "note": "class or uptake is fully determined by frequency; not separable"})
        return out
    null = np.empty(N_DRAWS)
    for i in range(N_DRAWS):
        perm = cls.copy()
        for t in range(3):
            idx = np.where(strata == t)[0]
            perm[idx] = rng.permutation(perm[idx])
        r = partial_r(perm, uptake, freq)
        null[i] = 0.0 if r is None else r
    extreme = np.sum(null >= obs) if sign > 0 else np.sum(null <= obs)
    boot = []
    for _ in range(N_DRAWS):
        i = rng.integers(0, len(cls), len(cls))
        r = partial_r(cls[i], uptake[i], freq[i])
        if r is not None:
            boot.append(r)
    out.update({"partial_r": obs, "p_one_sided": float((1 + extreme) / (1 + N_DRAWS)),
                "ci95": A.percentile_ci(np.array(boot)), "expected_sign": sign})
    return out


def run_arm(arm: str, data: Path, results: Path, codebook: Path) -> Dict:
    rng = np.random.default_rng(SEEDS[arm])
    arm_dir = data / f"frozen-{arm}"
    rec = json.loads((arm_dir / "recorded-both-sides.json").read_text())
    outc = json.loads((results / f"outcomes-{arm}.json").read_text())

    topics = A.distinct_topics(rec)
    tf = input_frequency(arm_dir, {t: [t] for t in topics})
    terms = sorted(topics)
    h3 = analyse([topics[t]["bridge"] for t in terms],
                 [outc["topics"][t][A.PRIMARY] for t in terms], [tf[t] for t in terms], +1, rng)

    classes = A.code_classes(rec)
    keep = sorted(k for k, c in classes.items() if c in ("blind", "covered"))
    codes = O.codebook_codes(json.loads(codebook.read_text()))
    cf = input_frequency(arm_dir, {k: codes[k] for k in keep})
    h4 = analyse([classes[k] == "blind" for k in keep],
                 [outc["codes"][k][A.PRIMARY] for k in keep], [cf[k] for k in keep], -1, rng)
    return {"arm": arm, "exploratory": True, "protocol": "Appendix C.1", "seed": SEEDS[arm],
            "H3_bridge_vs_single": h3, "H4_blind_vs_covered": h4}


def report(res: Dict[str, Dict]) -> str:
    f = A.fmt
    L = ["# Exploratory C.1 — H3 and H4 controlling for input term frequency", "",
         "**Exploratory, not registered.** Method fixed in PROTOCOL.md Appendix C.1 before it was run.",
         "Partial Spearman correlation of class with uptake, controlling for each unit's document",
         "frequency in the frozen input corpus; p one-sided, class permuted within frequency terciles.", ""]
    arms = list(res)
    L += ["| | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for key, name in (("H3_bridge_vs_single", "H3 bridge vs single"), ("H4_blind_vs_covered", "H4 blind vs covered")):
        def cell(a, fn):
            return fn(res[a][key])
        L.append(f"| **{name}** partial r [95 % CI] | " + " | ".join(
            cell(a, lambda r: f"**{f(r.get('partial_r'))}** [{', '.join(f(x) for x in (r.get('ci95') or [None, None]))}]")
            for a in arms) + " |")
        L.append(f"| {name}: p (one-sided) | " + " | ".join(cell(a, lambda r: f(r.get('p_one_sided'))) for a in arms) + " |")
        L.append(f"| {name}: ρ(frequency, uptake) | " + " | ".join(cell(a, lambda r: f(r['spearman_freq_uptake'])) for a in arms) + " |")
        L.append(f"| {name}: P(class 1 > class 0) by frequency tercile (low, mid, high) | " + " | ".join(
            cell(a, lambda r: ", ".join(f(x) for x in r["within_tercile_superiority"])) for a in arms) + " |")
        L.append(f"| {name}: class 1 / class 0 counts per tercile | " + " | ".join(
            cell(a, lambda r: " / ".join(str(r["freq_by_class"].get(c, {}).get("per_tercile")) for c in ("class_1", "class_0")))
            for a in arms) + " |")
        L.append(f"| {name}: median input frequency, class 1 / class 0 | " + " | ".join(
            cell(a, lambda r: " / ".join(f(r["freq_by_class"].get(c, {}).get("median")) for c in ("class_1", "class_0")))
            for a in arms) + " |")
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("paper/data"))
    ap.add_argument("--results", type=Path, default=Path("paper/results"))
    ap.add_argument("--codebook", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("paper/results/exploratory"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    res = {}
    for arm in ("A1", "A2"):
        res[arm] = run_arm(arm, args.data, args.results, args.codebook)
        (args.out / f"frequency-{arm}.json").write_text(json.dumps(res[arm], indent=1) + "\n")
    text = report(res)
    (args.out / "FREQUENCY_CONTROL.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
