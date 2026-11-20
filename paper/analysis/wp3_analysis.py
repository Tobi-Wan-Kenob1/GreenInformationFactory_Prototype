#!/usr/bin/env python3
"""WP3 — the registered tests, run once on the outcome files.

Implements PREREGISTRATION.md §7, §7.1 and §7.2 (doi:10.17605/OSF.IO/QC2SP),
with the operational definitions of PROTOCOL.md Appendix B.2, all committed
before any outcome data was retrieved.

Reads the recorded tool output (``paper/data/frozen-*/recorded*.json``) and the
outcome files written by ``wp3_outcomes.py``; writes ``analysis-<arm>.json``
and a side-by-side ``RESULTS.md``. Nothing in here looks at the outcome data
to decide how to analyse it.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import stats

N_DRAWS = 10_000
ALPHA = 0.05
MIN_LIST = 5
#: Fixed seeds, one per arm: the freeze date as a number.
SEEDS = {"A1": 20091231, "A2": 20131231}
PRIMARY = "share"
SECONDARY = ("projects", "organisations", "acts")


# --------------------------------------------------------------------------
# Units from the recorded output
# --------------------------------------------------------------------------

def ranked_lists(recording: Dict[str, Any]) -> Tuple[List[List[Dict[str, Any]]], int]:
    """Every (run, scope) list with at least MIN_LIST topics, and how many were shorter."""
    lists, short = [], 0
    for run in recording["runs"]:
        for scope in run["scopes"]:
            topics = scope["topics"]
            if len(topics) >= MIN_LIST:
                lists.append(topics)
            else:
                short += 1
    return lists, short


def distinct_topics(recording: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Each term once: best (lowest) rank in any list; bridge if any run lists it so."""
    out: Dict[str, Dict[str, Any]] = {}
    for run in recording["runs"]:
        for scope in run["scopes"]:
            for t in scope["topics"]:
                rec = out.setdefault(t["term"], {"best_rank": t["rank"], "bridge": False})
                rec["best_rank"] = min(rec["best_rank"], t["rank"])
                rec["bridge"] = rec["bridge"] or scope["scope"] == "bridge"
    return out


def code_classes(recording: Dict[str, Any]) -> Dict[str, str]:
    """``dimension:code`` → blind / covered / neither, from the tool's full coverage."""
    statuses: Dict[str, List[str]] = {}
    for run in recording["runs"]:
        for c in run["codebook"]["full"]["codes"]:
            statuses.setdefault(f"{c['dimension']}:{c['code']}", []).append(c["status"])
    out = {}
    for key, ss in statuses.items():
        if all(s == "gap" for s in ss):
            out[key] = "blind"
        elif any(s == "both" for s in ss):
            out[key] = "covered"
        else:
            out[key] = "neither"
    return out


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    """Spearman's rho with average ranks; None if either side is constant."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 2 or np.all(x == x[0]) or np.all(y == y[0]):
        return None
    rx, ry = stats.rankdata(x), stats.rankdata(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def percentile_ci(values: np.ndarray) -> List[Optional[float]]:
    values = values[np.isfinite(values)]
    if not len(values):
        return [None, None]
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def holm(pvalues: Dict[str, float]) -> Dict[str, float]:
    """Holm–Bonferroni adjusted p-values (step-down, monotone, capped at 1)."""
    keys = [k for k in pvalues if pvalues[k] is not None]
    order = sorted(keys, key=lambda k: pvalues[k])
    m, adjusted, running = len(order), {}, 0.0
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvalues[k]))
        adjusted[k] = running
    for k in pvalues:
        adjusted.setdefault(k, None)
    return adjusted


def list_rhos(lists, uptake: Dict[str, Dict[str, Any]], measure: str, score) -> Tuple[List[Tuple[np.ndarray, np.ndarray]], int]:
    """(score, outcome) arrays for each list whose outcome is not constant."""
    usable, constant = [], 0
    for topics in lists:
        x = np.array([score(t) for t in topics], float)
        y = np.array([uptake[t["term"]][measure] for t in topics], float)
        if np.all(y == y[0]):
            constant += 1
            continue
        usable.append((x, y))
    return usable, constant


def tool_score(t):          # rank 1 is the tool's top topic: higher score, higher expected uptake
    return -t["rank"]


def frequency_score(t):     # the H2 comparator: raw document frequency on both sides
    return t["dfPolicy"] + t["dfGrant"]


def test_h1(lists, uptake, measure, rng) -> Dict[str, Any]:
    pairs, constant = list_rhos(lists, uptake, measure, tool_score)
    rhos = [spearman(x, y) for x, y in pairs]
    keep = [(p, r) for p, r in zip(pairs, rhos) if r is not None]
    if not keep:
        return {"lists": 0, "lists_constant_outcome": constant, "mean_rho": None, "p": None}
    pairs = [p for p, _ in keep]
    rhos = np.array([r for _, r in keep])
    obs = float(rhos.mean())
    null = np.empty(N_DRAWS)
    for i in range(N_DRAWS):
        null[i] = np.mean([spearman(rng.permutation(x), y) or 0.0 for x, y in pairs])
    boot = np.array([rhos[rng.integers(0, len(rhos), len(rhos))].mean() for _ in range(N_DRAWS)])
    return {"lists": len(rhos), "lists_constant_outcome": constant,
            "mean_rho": obs, "ci95": percentile_ci(boot),
            "p": float((1 + np.sum(null >= obs)) / (1 + N_DRAWS)),
            "direction_ok": obs > 0}


def test_h2(lists, uptake, measure, rng) -> Dict[str, Any]:
    pairs_t, constant = list_rhos(lists, uptake, measure, tool_score)
    pairs_f, _ = list_rhos(lists, uptake, measure, frequency_score)
    diffs, undefined = [], 0
    for (xt, y), (xf, _) in zip(pairs_t, pairs_f):
        rt, rf = spearman(xt, y), spearman(xf, y)
        if rt is None or rf is None:
            undefined += 1
            continue
        diffs.append(rt - rf)
    if not diffs:
        return {"lists": 0, "lists_constant_outcome": constant, "lists_undefined": undefined,
                "mean_diff": None, "p": None}
    d = np.array(diffs)
    obs = float(d.mean())
    null = np.array([np.mean(d * rng.choice([-1.0, 1.0], len(d))) for _ in range(N_DRAWS)])
    boot = np.array([d[rng.integers(0, len(d), len(d))].mean() for _ in range(N_DRAWS)])
    return {"lists": len(d), "lists_constant_outcome": constant, "lists_undefined": undefined,
            "mean_diff": obs, "ci95": percentile_ci(boot),
            "p": float((1 + np.sum(null >= obs)) / (1 + N_DRAWS)),
            "direction_ok": obs > 0}


def superiority(a: np.ndarray, b: np.ndarray) -> float:
    """P(a > b) + ½ P(a = b): the common-language effect size, U / (n_a n_b)."""
    u = stats.mannwhitneyu(a, b, alternative="two-sided").statistic
    return float(u / (len(a) * len(b)))


def test_groups(a: np.ndarray, b: np.ndarray, alternative: str, rng) -> Dict[str, Any]:
    """Mann–Whitney U, one-sided; effect = P(a > b) with a bootstrap CI."""
    if len(a) == 0 or len(b) == 0:
        return {"n": [len(a), len(b)], "p": None, "superiority": None}
    p = float(stats.mannwhitneyu(a, b, alternative=alternative).pvalue)
    ps = superiority(a, b)
    boot = np.array([superiority(a[rng.integers(0, len(a), len(a))],
                                 b[rng.integers(0, len(b), len(b))]) for _ in range(N_DRAWS)])
    return {"n": [len(a), len(b)], "p": p, "superiority": ps, "ci95": percentile_ci(boot),
            "median": [float(np.median(a)), float(np.median(b))],
            "direction_ok": ps > 0.5 if alternative == "greater" else ps < 0.5}


def top_decile_ratio(lists, uptake, measure, rng) -> Dict[str, Any]:
    """Median uptake of the tool's top-decile topics over the median of all listed topics.

    Top decile: a term holding rank ≤ ceil(0.1 × list length) in any list used
    for H1. If the median of all topics is 0 the ratio is undefined and only
    the two medians are reported (PROTOCOL B.2).
    """
    top, every = set(), set()
    for topics in lists:
        cut = math.ceil(0.1 * len(topics))
        for t in topics:
            every.add(t["term"])
            if t["rank"] <= cut:
                top.add(t["term"])
    terms = sorted(every)
    y = np.array([uptake[t][measure] for t in terms], float)
    flag = np.array([t in top for t in terms])

    def ratio(yv, fv):
        denom = float(np.median(yv))
        if denom == 0 or not fv.any():
            return float("nan")
        return float(np.median(yv[fv])) / denom

    obs = ratio(y, flag)
    idx = [rng.integers(0, len(terms), len(terms)) for _ in range(N_DRAWS)]
    boot = np.array([ratio(y[i], flag[i]) for i in idx])
    return {"topics": len(terms), "top_decile": int(flag.sum()),
            "median_top": float(np.median(y[flag])) if flag.any() else None,
            "median_all": float(np.median(y)),
            "ratio": None if math.isnan(obs) else obs,
            "ci95": None if math.isnan(obs) else percentile_ci(boot),
            "bootstrap_undefined": int(np.sum(~np.isfinite(boot)))}


# --------------------------------------------------------------------------
# One arm
# --------------------------------------------------------------------------

def analyse_arm(arm: str, data_dir: Path, results_dir: Path) -> Dict[str, Any]:
    rng = np.random.default_rng(SEEDS[arm])
    rec_broad = json.loads((data_dir / f"frozen-{arm}" / "recorded.json").read_text())
    rec_bridge = json.loads((data_dir / f"frozen-{arm}" / "recorded-both-sides.json").read_text())
    outcomes = json.loads((results_dir / f"outcomes-{arm}.json").read_text())
    topics_u, codes_u = outcomes["topics"], outcomes["codes"]

    lists, short = ranked_lists(rec_broad)

    h1 = test_h1(lists, topics_u, PRIMARY, rng)
    h2 = test_h2(lists, topics_u, PRIMARY, rng)

    bridging = distinct_topics(rec_bridge)
    bridge = np.array([topics_u[t][PRIMARY] for t, r in bridging.items() if r["bridge"]])
    single = np.array([topics_u[t][PRIMARY] for t, r in bridging.items() if not r["bridge"]])
    h3 = test_groups(bridge, single, "greater", rng)

    classes = code_classes(rec_bridge)
    blind = np.array([codes_u[k][PRIMARY] for k, c in sorted(classes.items()) if c == "blind"])
    covered = np.array([codes_u[k][PRIMARY] for k, c in sorted(classes.items()) if c == "covered"])
    h4 = test_groups(blind, covered, "less", rng)
    h4["neither"] = sum(1 for c in classes.values() if c == "neither")

    tests = {"H1": h1, "H2": h2, "H3": h3, "H4": h4}
    adjusted = holm({k: v.get("p") for k, v in tests.items()})
    for k, v in tests.items():
        v["p_holm"] = adjusted[k]
        v["supported"] = bool(v.get("p") is not None and adjusted[k] < ALPHA and v.get("direction_ok"))

    effect = top_decile_ratio(lists, topics_u, PRIMARY, rng)

    # Secondary measures: descriptive only, no tests (registration §6).
    secondary = {}
    for m in SECONDARY:
        if not all(m in topics_u[t] for t in topics_u):
            secondary[m] = {"available": False}
            continue
        pairs, constant = list_rhos(lists, topics_u, m, tool_score)
        rhos = [r for r in (spearman(x, y) for x, y in pairs) if r is not None]
        secondary[m] = {"available": True, "lists": len(rhos), "lists_constant_outcome": constant,
                        "mean_rho": float(np.mean(rhos)) if rhos else None}

    return {"arm": arm, "seed": SEEDS[arm], "draws": N_DRAWS, "alpha": ALPHA,
            "primary_measure": "EC contribution share",
            "lists_used": len(lists), "lists_shorter_than_min": short,
            "tests": tests, "effect_size_top_decile": effect, "secondary": secondary,
            "window": outcomes["window"], "denominator": outcomes["denominator"]}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def fmt(v, digits=3):
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{digits}g}" if abs(v) < 1e-3 and v != 0 else f"{v:.{digits}f}"
    return str(v)


def report(results: Dict[str, Dict[str, Any]]) -> str:
    arms = list(results)
    L = ["# Results — registered back-test", "",
         "Registration: [doi:10.17605/OSF.IO/QC2SP](https://doi.org/10.17605/OSF.IO/QC2SP). "
         "Generated by `paper/analysis/wp3_analysis.py`; nothing here is edited by hand.", "",
         "Arms are reported side by side and never pooled. One-sided tests, α = 0.05, "
         "Holm–Bonferroni across H1–H4 within each arm. Effect size before significance.", ""]
    L += ["| | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]

    def row(label, f):
        L.append(f"| {label} | " + " | ".join(f(results[a]) for a in arms) + " |")

    row("Outcome window", lambda r: f"{r['window']['since']} – {r['window']['until']}")
    row("Projects in window (EC € total)",
        lambda r: f"{r['denominator']['projects']:,} (€{r['denominator']['ec_eur'] / 1e9:,.1f} bn)")
    row("**Effect size**: top-decile / median uptake",
        lambda r: (f"**{fmt(r['effect_size_top_decile']['ratio'])}** "
                   f"[{', '.join(fmt(x) for x in (r['effect_size_top_decile']['ci95'] or [None, None]))}]")
        if r["effect_size_top_decile"]["ratio"] is not None else
        f"undefined (median all = {fmt(r['effect_size_top_decile']['median_all'])}, "
        f"top = {fmt(r['effect_size_top_decile']['median_top'])})")
    labels = {"H1": ("mean ρ", "mean_rho"), "H2": ("mean Δρ", "mean_diff"),
              "H3": ("P(bridge > single)", "superiority"), "H4": ("P(blind > covered)", "superiority")}
    for h, (name, key) in labels.items():
        row(f"**{h}** {name} [95 % CI]",
            lambda r, h=h, key=key: f"{fmt(r['tests'][h].get(key))} "
                                    f"[{', '.join(fmt(x) for x in (r['tests'][h].get('ci95') or [None, None]))}]")
        row(f"{h} p (Holm) · supported",
            lambda r, h=h: f"{fmt(r['tests'][h].get('p'))} ({fmt(r['tests'][h].get('p_holm'))}) · "
                           f"**{fmt(r['tests'][h]['supported'])}**")
    row("H1/H2 lists used (constant outcome, excluded)",
        lambda r: f"{r['tests']['H1']['lists']} ({r['tests']['H1']['lists_constant_outcome']})")
    row("H3 n (bridge, single)", lambda r: ", ".join(map(str, r["tests"]["H3"]["n"])))
    row("H4 n (blind, covered; neither left out)",
        lambda r: ", ".join(map(str, r["tests"]["H4"]["n"])) + f"; {r['tests']['H4']['neither']}")
    for m in SECONDARY:
        row(f"Secondary, descriptive: mean ρ on {m}",
            lambda r, m=m: fmt(r["secondary"][m].get("mean_rho")) if r["secondary"][m]["available"] else "n/a")
    L +=["", "**Replication** (supported in both arms): " + (", ".join(
        h for h in ("H1", "H2", "H3", "H4") if all(results[a]["tests"][h]["supported"] for a in arms))
        or "none") + ".", ""]
    return "\n".join(L) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, default=Path("paper/data"))
    ap.add_argument("--results", type=Path, default=Path("paper/results"))
    ap.add_argument("--arms", default="A1,A2")
    args = ap.parse_args(argv)
    results = {}
    for arm in args.arms.split(","):
        results[arm] = analyse_arm(arm, args.data, args.results)
        (args.results / f"analysis-{arm}.json").write_text(
            json.dumps(results[arm], indent=1) + "\n", encoding="utf-8")
    text = report(results)
    (args.results / "RESULTS.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
