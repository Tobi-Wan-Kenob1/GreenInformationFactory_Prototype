"""Tests for the Tier B frame and sample (PROTOCOL.md B.4), synthetic data only."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wp4_tierb as B   # noqa: E402

cordis = pytest.importorskip("gif.cordis")


def _rec(runs):
    return {"runs": [{"query": q, "scopes": [{"scope": "bridge", "topics": [
        {"rank": i + 1, "term": t} for i, t in enumerate(terms)]},
        {"scope": "grant", "topics": [{"rank": 1, "term": "ignored"}]}]} for q, terms in runs]}


def test_pairs_skip_self_order_by_rank_then_query_order():
    rec = _rec([("water", ["water", "soil", "crop"]), ("land", ["land", "farm", "soil"])])
    pairs = B.ordered_pairs(rec, ["land", "water"])
    assert [(p["query"], p["topic"], p["rank"]) for p in pairs] == [
        ("land", "farm", 2), ("water", "soil", 2), ("land", "soil", 3), ("water", "crop", 3)]


def _projects_orgs(spec):
    """spec: {project_id: (text, [org keys])}"""
    projects = [{"id": pid, "text": text, "start": "2011-01-01"} for pid, (text, _) in spec.items()]
    orgs = [{"project": pid, "key": k, "name": k, "country": "DE", "activityType": "PRC",
             "vatNumber": "", "url": "", "role": "participant", "ecContribution": 1.0}
            for pid, (_, keys) in spec.items() for k in keys]
    return projects, orgs


def test_frame_needs_both_query_and_topic_and_stops_at_minimum(monkeypatch):
    monkeypatch.setattr(B, "FRAME_MIN", 3)
    monkeypatch.setattr(B, "FRAME_MAX", 10)
    projects, orgs = _projects_orgs({
        "p1": ("land and farm", ["a", "b"]),
        "p2": ("farm only", ["x"]),               # topic without query: not in the frame
        "p3": ("land soil", ["c", "d"]),
        "p4": ("land crop", ["e"]),
    })
    pairs = [{"query": "land", "topic": "farm", "rank": 2},
             {"query": "land", "topic": "soil", "rank": 3},
             {"query": "land", "topic": "crop", "rank": 4}]
    fr = B.build_frame(pairs, projects, orgs, cordis)
    assert fr["k"] == 2 and fr["frame_size"] == 4 and fr["stop_reason"] == "minimum reached"
    assert fr["frame_keys"] == {"a", "b", "c", "d"}


def test_frame_stops_before_a_pair_that_overshoots(monkeypatch):
    monkeypatch.setattr(B, "FRAME_MIN", 5)
    monkeypatch.setattr(B, "FRAME_MAX", 6)
    projects, orgs = _projects_orgs({
        "p1": ("land farm", ["a", "b"]),
        "p2": ("land soil", ["c", "d", "e", "f", "g"]),
    })
    pairs = [{"query": "land", "topic": "farm", "rank": 2}, {"query": "land", "topic": "soil", "rank": 3}]
    fr = B.build_frame(pairs, projects, orgs, cordis)
    assert fr["k"] == 1 and fr["frame_size"] == 2
    assert fr["stop_reason"] == "next pair would exceed the maximum"


def test_first_pair_alone_over_the_maximum_is_used_alone(monkeypatch):
    monkeypatch.setattr(B, "FRAME_MIN", 2)
    monkeypatch.setattr(B, "FRAME_MAX", 3)
    projects, orgs = _projects_orgs({"p1": ("land farm", ["a", "b", "c", "d"])})
    fr = B.build_frame([{"query": "land", "topic": "farm", "rank": 2}], projects, orgs, cordis)
    assert fr["k"] == 1 and fr["frame_size"] == 4 and "used alone" in fr["stop_reason"]


def test_allocation_largest_remainder():
    assert B.allocate({"PRC": 60, "HES": 25, "REC": 15}, 5) == {"PRC": 3, "HES": 1, "REC": 1}
    assert sum(B.allocate({"PRC": 1, "HES": 1, "REC": 1, "PUB": 1, "OTH": 1, }, 5).values()) == 5


def test_draw_is_deterministic_spreads_countries_and_keeps_a_reserve():
    frame = [{"key": f"k{i}", "name": f"n{i}", "activityType": "PRC" if i < 8 else "HES",
              "country": "DE" if i % 2 else "FR"} for i in range(10)]
    s1, extra1 = B.draw(frame, 3, 7)
    s2, _ = B.draw(frame, 3, 7)
    assert [s["key"] for s in s1] == [s["key"] for s in s2]
    prc = [s for s in s1 if s["stratum"] == "PRC"]
    assert len({s["country"] for s in prc}) == len(prc)          # two PRC, two countries
    sampled = {s["key"] for s in s1}
    assert not sampled & set(sum(extra1["reserve"].values(), []))
    assert len(sampled) + len(sum(extra1["reserve"].values(), [])) == len(frame)
