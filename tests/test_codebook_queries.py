"""Tests for the codebook query selection rule.

The rule exists so that query terms are not hand-picked, so the tests are
mostly about it being a rule: that a term matching most of the corpus is
dropped however many papers back it, that ranking and tie-breaking are
deterministic, and that the working is reported rather than only the answer.
"""
from __future__ import annotations

import json

import pytest

from gif import codebook_queries as cq


def _corpus(tmp_path, policies=(), projects=()):
    path = tmp_path / "corpus"
    path.mkdir(parents=True, exist_ok=True)
    (path / "policies.json").write_text(json.dumps({"items": list(policies)}),
                                        encoding="utf-8")
    (path / "projects.json").write_text(json.dumps({"items": list(projects)}),
                                        encoding="utf-8")
    return path


def _doc(doc_id, title, summary=""):
    return {"id": doc_id, "title": title, "summary": summary}


def _codebook(barriers=(), drivers=()):
    return {
        "dimension_labels": {"barriers": "Barriers", "drivers": "Drivers"},
        "dimensions": {
            "barriers": [{"code": c, "terms": t, "papers": p} for c, t, p in barriers],
            "drivers": [{"code": c, "terms": t, "papers": p} for c, t, p in drivers],
        },
    }


def test_a_term_matching_most_of_the_corpus_is_dropped(tmp_path):
    """The failure the rule exists to prevent: "water" as a topic.

    It leads the codebook on paper count and matches EU acts on drinking
    water, bathing water and maritime policy alike, so it describes the corpus
    rather than a topic within it.
    """
    corpus = _corpus(tmp_path, policies=[
        _doc("p:1", "Water framework directive"),
        _doc("p:2", "Bathing water quality"),
        _doc("p:3", "Drinking water standards"),
        _doc("p:4", "Soil monitoring and water retention"),
        _doc("p:5", "Mine tailings management"),
    ])
    codebook = _codebook(barriers=[("water", ["water"], 90),
                                   ("tailings", ["tailings"], 5)])
    result = cq.select_queries(corpus, codebook=codebook, top=5)

    water = next(c for c in result["candidates"] if c["code"] == "water")
    assert water["documents"] == 4 and water["df"] == 0.8
    assert water["status"] == "dropped: too broad"
    assert result["queries"] == ["tailings"], \
        "the 90-paper code must lose to the specific one it swamps"


def test_ranking_is_by_paper_count_with_alphabetical_ties(tmp_path):
    corpus = _corpus(tmp_path, policies=[
        _doc("p:1", "alpha beta gamma delta"),
        _doc("p:2", "unrelated"), _doc("p:3", "unrelated"),
        _doc("p:4", "unrelated"), _doc("p:5", "unrelated"),
    ])
    codebook = _codebook(
        barriers=[("gamma", ["gamma"], 10), ("beta", ["beta"], 20)],
        drivers=[("delta", ["delta"], 20), ("alpha", ["alpha"], 5)])
    result = cq.select_queries(corpus, codebook=codebook, top=3)
    # 20 papers: beta and delta, tie broken alphabetically. Then 10, then 5.
    assert result["queries"] == ["beta", "delta", "gamma"]
    assert [c["rank"] for c in result["selected"]] == [1, 2, 3]


def test_a_code_absent_from_the_corpus_is_not_a_query(tmp_path):
    """It cannot be ranked on subsequent uptake, so it cannot be tested."""
    corpus = _corpus(tmp_path, policies=[
        _doc("p:1", "soil monitoring"), _doc("p:2", "x"), _doc("p:3", "y"),
        _doc("p:4", "z"), _doc("p:5", "w")])
    codebook = _codebook(barriers=[("soil", ["soil"], 30),
                                   ("permafrost", ["permafrost"], 50)])
    result = cq.select_queries(corpus, codebook=codebook, top=5)
    absent = next(c for c in result["candidates"] if c["code"] == "permafrost")
    assert absent["status"] == "dropped: absent from corpus"
    assert result["queries"] == ["soil"]


def test_every_candidate_is_reported_with_its_working(tmp_path):
    corpus = _corpus(tmp_path, policies=[_doc("p:1", "soil"), _doc("p:2", "water"),
                                         _doc("p:3", "water"), _doc("p:4", "x"),
                                         _doc("p:5", "y")])
    codebook = _codebook(barriers=[("soil", ["soil"], 30), ("water", ["water"], 90)])
    result = cq.select_queries(corpus, codebook=codebook, top=1)
    statuses = {c["code"]: c["status"] for c in result["candidates"]}
    assert statuses == {"soil": "selected", "water": "dropped: too broad"}
    assert result["rule"]["max_df"] == cq.DEFAULT_MAX_DF
    assert "no thesaurus" in result["rule"]["matching"]


def test_shortfall_is_flagged_rather_than_hidden(tmp_path):
    corpus = _corpus(tmp_path, policies=[_doc("p:1", "soil"), _doc("p:2", "x"),
                                         _doc("p:3", "y"), _doc("p:4", "z"),
                                         _doc("p:5", "w")])
    codebook = _codebook(barriers=[("soil", ["soil"], 30)])
    result = cq.select_queries(corpus, codebook=codebook, top=10)
    assert result["queries"] == ["soil"]
    assert result["short"] is True


def test_matching_uses_a_word_boundary_like_the_app(tmp_path):
    corpus = _corpus(tmp_path, policies=[
        _doc("p:1", "Determining the structure of proteins"),
        _doc("p:2", "Mining waste"), _doc("p:3", "x"), _doc("p:4", "y"),
        _doc("p:5", "z")])
    codebook = _codebook(barriers=[("mining", ["mining"], 10)])
    result = cq.select_queries(corpus, codebook=codebook, top=5)
    mining = next(c for c in result["candidates"] if c["code"] == "mining")
    assert mining["documents"] == 1, '"determining" must not count as mining'


def test_all_sources_in_the_corpus_are_counted(tmp_path):
    corpus = _corpus(tmp_path,
                     policies=[_doc("p:1", "soil act")],
                     projects=[_doc("c:fp7:1", "soil project"), _doc("c:fp7:2", "x")])
    codebook = _codebook(barriers=[("soil", ["soil"], 10)])
    result = cq.select_queries(corpus, codebook=codebook, top=5, max_df=0.9)
    assert result["documents"] == 3
    soil = next(c for c in result["candidates"] if c["code"] == "soil")
    assert soil["documents"] == 2


def test_per_side_counts_expose_a_term_that_lives_on_one_side_only(tmp_path):
    """The failure the first real run showed: 8 of 10 queries matched no act.

    The funding side outnumbered the policy side four to one, so corpus-wide
    frequency chose terms that were well attested in projects and absent from
    every policy — leaving a bridge-versus-single-corpus comparison with
    nothing to compare.
    """
    corpus = _corpus(
        tmp_path,
        policies=[_doc("p:1", "soil monitoring act"), _doc("p:2", "water act")],
        projects=[_doc("c:1", "technology for soil"), _doc("c:2", "technology"),
                  _doc("c:3", "technology"), _doc("c:4", "unrelated")])
    codebook = _codebook(barriers=[("technology", ["technology"], 50),
                                   ("soil", ["soil"], 20)])

    wide = cq.select_queries(corpus, codebook=codebook, top=2, max_df=0.9)
    tech = next(c for c in wide["candidates"] if c["code"] == "technology")
    assert tech["policy_documents"] == 0 and tech["grant_documents"] == 3
    assert tech["both_sides"] is False
    assert wide["queries"] == ["technology", "soil"]
    assert wide["selected_on_both_sides"] == 1, "only soil spans both sides"
    assert wide["documents_by_side"] == {"policy": 2, "grant": 4}

    strict = cq.select_queries(corpus, codebook=codebook, top=2, max_df=0.9,
                               require_both=True)
    assert strict["queries"] == ["soil"]
    assert next(c for c in strict["candidates"]
                if c["code"] == "technology")["status"] == "dropped: one side only"
    assert strict["rule"]["require_both_sides"] is True


def test_projects_count_on_the_funding_side_with_call_topics(tmp_path):
    """Both answer "what is being financed here", which is how the tool reads them."""
    corpus = _corpus(tmp_path, policies=[_doc("p:1", "act")],
                     projects=[_doc("c:1", "project")])
    sides = cq.corpus_sides(corpus)
    assert len(sides["policy"]) == 1 and len(sides["grant"]) == 1


def test_empty_corpus_is_an_error_not_an_empty_answer(tmp_path):
    corpus = _corpus(tmp_path)
    with pytest.raises(RuntimeError, match="no documents"):
        cq.select_queries(corpus, codebook=_codebook(barriers=[("soil", ["soil"], 1)]))


def test_real_codebook_has_the_dimensions_the_rule_expects():
    """Guards against the codebook being regenerated into a different shape."""
    codebook = cq.load_codebook()
    for dimension in cq.DEFAULT_DIMENSIONS:
        entries = codebook["dimensions"][dimension]
        assert entries, f"{dimension} should not be empty"
        assert {"code", "terms", "papers"} <= set(entries[0])
