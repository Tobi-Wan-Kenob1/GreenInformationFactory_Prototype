"""Tests for the WP3 outcome extraction and analysis, on synthetic data only.

Run with the tool at the registered commit on the path:
    PYTHONPATH=<tool>/src python -m pytest paper/analysis/test_wp3.py

No real outcome data is used; these exist so the code that will run once on
real data has been shown to give known answers first.
"""
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wp3_analysis as A   # noqa: E402
import wp3_outcomes as O   # noqa: E402

cordis = pytest.importorskip("gif.cordis")


# ---------------------------------------------------------------- outcomes

def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, rows in members.items():
            s = io.StringIO()
            csv.writer(s, delimiter=";").writerows(rows)
            z.writestr(name, s.getvalue())
    return buf.getvalue()


PROJECT_HEADER = ["id", "acronym", "status", "title", "startDate", "endDate",
                  "totalCost", "ecMaxContribution", "frameworkProgramme", "masterCall", "objective"]


def _archive(rows, orgs=(), scivoc=()):
    members = {"project.csv": [PROJECT_HEADER] + rows}
    members["organization.csv"] = [["projectID", "organisationID", "name"]] + list(orgs)
    members["euroSciVoc.csv"] = [["projectID", "euroSciVocTitle"]] + list(scivoc)
    return cordis.read_csv_members(zipfile.ZipFile(io.BytesIO(_zip(members))))


def test_outcome_projects_reads_window_fields_and_organisations():
    m = _archive([
        ["1", "A", "", "Soil carbon in farming", "2015-03-01", "", "", "1000,5", "H2020", "", "obj"],
        ["2", "B", "", "Landing gear", "2009-06-01", "", "", "", "FP7", "", "aero"],
        ["3", "C", "", "Undated", "", "", "", "5", "H2020", "", ""],
        ["1", "A", "", "duplicate row", "2015-03-01", "", "", "1", "H2020", "", ""],
    ], orgs=[["1", "999", "X"], ["1", "", "Uni Y"], ["1", "999", "X again"]],
       scivoc=[["1", "agronomy"]])
    items, counts = O.outcome_projects(m, "h2020", cordis)
    assert counts["usable"] == 2 and counts["undated"] == 1 and counts["duplicate_or_no_id"] == 1
    p1 = next(p for p in items if p["id"] == "h2020:1")
    assert p1["ec"] == 1000.5
    assert p1["orgs"] == {"999", "name:uni y"}
    assert "agronomy" in p1["text"]
    p2 = next(p for p in items if p["id"] == "h2020:2")
    assert p2["ec"] is None
    assert [p["id"] for p in O.in_window(items, "2010-01-01", "2026-12-31")] == ["h2020:1"]


def test_parse_eur_keeps_zero_and_rejects_junk():
    assert O.parse_eur("0") == 0.0
    assert O.parse_eur("") is None
    assert O.parse_eur("n/a") is None
    assert O.parse_eur("12.5") == 12.5


def test_uptake_uses_the_registered_leading_boundary_rule():
    projects = [
        {"id": "a", "programme": "h2020", "start": "2015-01-01", "ec": 60.0, "text": "landscape restoration", "orgs": {"o1"}},
        {"id": "b", "programme": "h2020", "start": "2015-01-01", "ec": 30.0, "text": "Finland forestry", "orgs": {"o2"}},
        {"id": "c", "programme": "fp7", "start": "2011-01-01", "ec": None, "text": "Land use change", "orgs": {"o1", "o3"}},
        {"id": "d", "programme": "fp7", "start": "2011-01-01", "ec": 10.0, "text": "nothing relevant", "orgs": set()},
    ]
    out, denom = O.project_uptake(projects, {"land": ["land"], "zzz": ["zzz"]}, cordis)
    # leading boundary: 'landscape' and 'Land use' match, 'Finland' does not
    assert out["land"]["projects"] == 2
    assert out["land"]["ec_eur"] == 60.0 and out["land"]["share"] == pytest.approx(0.6)
    assert out["land"]["projects_missing_ec"] == 1
    assert out["land"]["organisations"] == 2
    assert out["zzz"] == {"ec_eur": 0.0, "share": 0.0, "projects": 0,
                          "projects_missing_ec": 0, "organisations": 0}
    assert denom["projects"] == 4 and denom["ec_eur"] == 100.0 and denom["projects_missing_ec"] == 1


def test_act_uptake_counts_title_and_summary():
    acts = [{"title": "Soil directive", "summary": ""}, {"title": "x", "summary": "on soils and land"}]
    assert O.act_uptake(acts, {"soil": ["soil"], "land": ["land"]}, cordis) == {"soil": 2, "land": 1}


# ---------------------------------------------------------------- analysis

def _recording(lists_spec, codes=None):
    """lists_spec: [(scope, [(term, dfPolicy, dfGrant), ...]), ...] grouped one run per list."""
    runs = []
    for scope, terms in lists_spec:
        runs.append({"scopes": [{"scope": scope, "topics": [
            {"rank": i + 1, "term": t, "dfPolicy": p, "dfGrant": g} for i, (t, p, g) in enumerate(terms)]}],
            "codebook": {"full": {"codes": codes or []}}})
    return {"runs": runs}


def test_holm_matches_hand_computation():
    adj = A.holm({"H1": 0.01, "H2": 0.04, "H3": 0.03, "H4": None})
    assert adj["H1"] == pytest.approx(0.03)
    assert adj["H3"] == pytest.approx(0.06)
    assert adj["H2"] == pytest.approx(0.06)   # monotone: max(0.06, 1 * 0.04)
    assert adj["H4"] is None


def test_spearman_constant_is_undefined():
    assert A.spearman([1, 2, 3], [5, 5, 5]) is None
    assert A.spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_h1_detects_a_real_ranking_and_not_a_random_one():
    rng = np.random.default_rng(1)
    lists, uptake_good, uptake_null = [], {}, {}
    for k in range(12):
        terms = [(f"t{k}_{i}", 1, 1) for i in range(8)]
        lists.append([{"rank": i + 1, "term": t, "dfPolicy": 1, "dfGrant": 1} for i, (t, _, _) in enumerate(terms)])
        for i, (t, _, _) in enumerate(terms):
            uptake_good[t] = {"share": 1.0 / (i + 1)}          # rank 1 has most uptake
            uptake_null[t] = {"share": float(rng.random())}
    good = A.test_h1(lists, uptake_good, "share", np.random.default_rng(2))
    assert good["mean_rho"] == pytest.approx(1.0) and good["p"] < 0.001 and good["direction_ok"]
    null = A.test_h1(lists, uptake_null, "share", np.random.default_rng(3))
    assert null["p"] > 0.05


def test_h1_excludes_lists_with_constant_outcome():
    lists = [[{"rank": i + 1, "term": f"a{i}", "dfPolicy": 0, "dfGrant": 0} for i in range(5)],
             [{"rank": i + 1, "term": f"b{i}", "dfPolicy": 0, "dfGrant": 0} for i in range(5)]]
    uptake = {**{f"a{i}": {"share": 0.0} for i in range(5)},
              **{f"b{i}": {"share": float(5 - i)} for i in range(5)}}
    r = A.test_h1(lists, uptake, "share", np.random.default_rng(0))
    assert r["lists"] == 1 and r["lists_constant_outcome"] == 1


def test_h2_is_zero_when_tool_equals_frequency_order():
    # frequency falls with rank, so both rankings are identical: no advantage
    lists = [[{"rank": i + 1, "term": f"k{j}_{i}", "dfPolicy": 10 - i, "dfGrant": 0} for i in range(6)]
             for j in range(6)]
    uptake = {f"k{j}_{i}": {"share": float(10 - i + j)} for j in range(6) for i in range(6)}
    r = A.test_h2(lists, uptake, "share", np.random.default_rng(0))
    assert r["mean_diff"] == pytest.approx(0.0) and r["p"] > 0.5


def test_ranked_lists_drops_short_lists():
    rec = _recording([("bridge", [("a", 1, 1)] * 3), ("grant", [(f"g{i}", 1, 1) for i in range(5)])])
    lists, short = A.ranked_lists(rec)
    assert len(lists) == 1 and short == 1


def test_distinct_topics_best_rank_and_bridge_in_any_run():
    rec = _recording([("grant", [("x", 1, 1), ("y", 1, 1)]), ("bridge", [("y", 1, 1), ("x", 1, 1)])])
    d = A.distinct_topics(rec)
    assert d["x"] == {"best_rank": 1, "bridge": True}
    assert d["y"] == {"best_rank": 1, "bridge": True}


def test_code_classes_blind_needs_every_run():
    runs = {"runs": [
        {"scopes": [], "codebook": {"full": {"codes": [
            {"dimension": "barriers", "code": "a", "status": "gap"},
            {"dimension": "barriers", "code": "b", "status": "gap"},
            {"dimension": "barriers", "code": "c", "status": "partial"}]}}},
        {"scopes": [], "codebook": {"full": {"codes": [
            {"dimension": "barriers", "code": "a", "status": "gap"},
            {"dimension": "barriers", "code": "b", "status": "both"},
            {"dimension": "barriers", "code": "c", "status": "partial"}]}}}]}
    assert A.code_classes(runs) == {"barriers:a": "blind", "barriers:b": "covered", "barriers:c": "neither"}


def test_groups_direction_and_effect():
    a = np.array([5.0, 6, 7, 8, 9])
    b = np.array([1.0, 2, 3, 4, 5])
    r = A.test_groups(a, b, "greater", np.random.default_rng(0))
    assert r["superiority"] > 0.9 and r["p"] < 0.05 and r["direction_ok"]
    r = A.test_groups(b, a, "less", np.random.default_rng(0))
    assert r["superiority"] < 0.1 and r["p"] < 0.05 and r["direction_ok"]


def test_top_decile_ratio_and_undefined_case():
    lists = [[{"rank": i + 1, "term": f"t{j}_{i}"} for i in range(10)] for j in range(3)]
    uptake = {f"t{j}_{i}": {"share": 10.0 if i == 0 else 1.0} for j in range(3) for i in range(10)}
    r = A.top_decile_ratio(lists, uptake, "share", np.random.default_rng(0))
    assert r["top_decile"] == 3 and r["ratio"] == pytest.approx(10.0)
    zero = {k: {"share": 0.0 if not k.endswith("_0") else 1.0} for k in uptake}
    r = A.top_decile_ratio(lists, zero, "share", np.random.default_rng(0))
    assert r["ratio"] is None and r["median_all"] == 0.0 and r["median_top"] == 1.0


def test_whole_arm_end_to_end(tmp_path):
    data = tmp_path / "data" / "frozen-A1"
    data.mkdir(parents=True)
    terms = [f"w{i}" for i in range(8)]
    broad = {"runs": [{"scopes": [
        {"scope": "grant", "topics": [{"rank": i + 1, "term": t, "dfPolicy": 1, "dfGrant": 8 - i}
                                      for i, t in enumerate(terms)]},
        {"scope": "policy", "topics": [{"rank": i + 1, "term": t, "dfPolicy": i, "dfGrant": 0}
                                       for i, t in enumerate(reversed(terms))]},
        {"scope": "bridge", "topics": [{"rank": 1, "term": "w0", "dfPolicy": 1, "dfGrant": 1}]}],
        "codebook": {"full": {"codes": [
            {"dimension": "barriers", "code": "a", "status": "gap"},
            {"dimension": "barriers", "code": "b", "status": "both"}]}}}]}
    (data / "recorded.json").write_text(json.dumps(broad))
    (data / "recorded-both-sides.json").write_text(json.dumps(broad))
    res = tmp_path / "results"
    res.mkdir()
    topics = {t: {"share": 1.0 / (i + 1), "projects": 8 - i, "organisations": 1, "acts": 0}
              for i, t in enumerate(terms)}
    (res / "outcomes-A1.json").write_text(json.dumps({
        "window": {"since": "2010-01-01", "until": "2026-12-31"},
        "denominator": {"projects": 100, "ec_eur": 1e9},
        "topics": topics,
        "codes": {"barriers:a": {"share": 0.1}, "barriers:b": {"share": 0.5}}}))
    out = A.analyse_arm("A1", tmp_path / "data", res)
    assert out["lists_used"] == 2 and out["lists_shorter_than_min"] == 1
    assert set(out["tests"]) == {"H1", "H2", "H3", "H4"}
    assert out["tests"]["H4"]["n"] == [1, 1]
    assert out["secondary"]["acts"]["available"] is True
    text = A.report({"A1": out})
    assert "H1" in text and "Effect size" in text
