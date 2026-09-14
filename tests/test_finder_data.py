"""Tests for gif.finder_data (Policy & Grant Finder snapshot fetcher).

No network: fetchers are exercised through their pure normalisers and by
monkeypatching the fetch functions for build_snapshot.
"""
from __future__ import annotations

import json

import pytest

from gif import finder_data as fd


# ---------------------------------------------------------------------------
# budget extraction
# ---------------------------------------------------------------------------

def test_extract_budget_from_direct_field():
    assert fd.extract_budget_eur({"budget": ["12000000"]}) == 12000000


def test_extract_budget_from_overview_json():
    overview = json.dumps({"budgetTopicActionMap": {
        "HORIZON-X": [{"action": "IA", "budget": "9 000 000"}]}})
    assert fd.extract_budget_eur({"budgetOverviewJSONItem": [overview]}) == 9000000


def test_extract_budget_missing_or_tiny():
    assert fd.extract_budget_eur({}) is None
    # numbers ≤ 1000 are treated as codes/counts, not EUR budgets
    assert fd.extract_budget_eur({"budget": ["42"]}) is None
    assert fd.extract_budget_eur({"budget": ["not a number"]}) is None


# ---------------------------------------------------------------------------
# grant normalisation
# ---------------------------------------------------------------------------

def test_normalize_grant_full():
    doc = fd.normalize_grant({
        "metadata": {
            "identifier": ["HORIZON-CL6-2025-CIRCBIO-01-1"],
            "title": ["<b>Circular</b>  solutions"],
            "description": ["Bio-based   value chains."],
            "startDate": ["2025-09-15T00:00:00.000+0200"],
            "type": ["1"],
            "budget": ["12000000"],
        },
    })
    assert doc["id"] == "g:HORIZON-CL6-2025-CIRCBIO-01-1"
    assert doc["kind"] == "grant"
    assert doc["title"] == "Circular solutions"          # tags stripped, ws collapsed
    assert doc["summary"] == "Bio-based value chains."
    assert doc["date"] == "2025-09-15"
    assert doc["budgetEUR"] == 12000000
    assert doc["doctype"] == "Call topic"
    assert "topic-details/horizon-cl6-2025-circbio-01-1" in doc["url"]


def test_fetch_grants_caps_page_size_and_posts_form_encoded(monkeypatch):
    """The API 400s above pageSize=50 and 500s on multipart bodies."""
    seen = {}

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    def fake_post(url, params=None, data=None, files=None, timeout=None):
        seen.update(params=params, data=data, files=files)
        return FakeResp()

    monkeypatch.setattr(fd.requests, "post", fake_post)
    fd.fetch_grants(["biomass"], page_size=100)

    assert int(seen["params"]["pageSize"]) <= fd.MAX_PAGE_SIZE
    assert seen["files"] is None            # multipart → 500 from the API
    assert "query" in seen["data"]          # form-urlencoded payload


def test_fetch_grants_can_exclude_closed_calls(monkeypatch):
    seen = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": []}

    monkeypatch.setattr(
        fd.requests, "post",
        lambda url, params=None, data=None, files=None, timeout=None:
            (seen.update(data=data), FakeResp())[1])

    fd.fetch_grants(["biomass"], include_closed=False)
    assert fd.STATUS_CLOSED not in seen["data"]["query"]
    assert fd.STATUS_OPEN in seen["data"]["query"]

    fd.fetch_grants(["biomass"], include_closed=True)
    assert fd.STATUS_CLOSED in seen["data"]["query"]


def test_normalize_grant_sparse_is_safe():
    doc = fd.normalize_grant({})
    assert doc["kind"] == "grant"
    assert doc["budgetEUR"] is None
    assert doc["date"] is None


# ---------------------------------------------------------------------------
# policy normalisation + SPARQL query
# ---------------------------------------------------------------------------

def _binding(celex="32021R1119"):
    return {
        "work": {"value": "http://publications.europa.eu/resource/cellar/abc"},
        "title": {"value": "European Climate Law"},
        "date": {"value": "2021-06-30"},
        "type": {"value": "http://publications.europa.eu/resource/authority/resource-type/REG"},
        "celex": {"value": celex},
    }


def test_normalize_policy_with_celex():
    doc = fd.normalize_policy(_binding())
    assert doc["id"] == "p:32021R1119"
    assert doc["kind"] == "policy"
    assert doc["doctype"] == "REG"
    assert doc["date"] == "2021-06-30"
    assert doc["url"].endswith("CELEX:32021R1119")


def test_normalize_policy_without_celex_falls_back_to_uri():
    b = _binding()
    del b["celex"]
    doc = fd.normalize_policy(b)
    assert doc["id"].startswith("p:http://publications.europa.eu/")
    assert doc["url"].startswith("http://publications.europa.eu/")


def test_sparql_query_contains_keywords_and_guards():
    q = fd.sparql_query(['bio"economy', "circular economy"], since="2019-01-01", limit=42)
    assert '"bioeconomy"' in q            # quotes are stripped from keywords
    assert '"circular economy"' in q
    assert "2019-01-01" in q
    assert "LIMIT 42" in q
    assert "resource-type/REG" in q
    assert "?date <=" not in q            # no upper bound unless asked for


def test_sparql_query_windows_a_past_period():
    """Benchmark mode: both ends bounded so an earlier setting can be replayed."""
    q = fd.sparql_query(["biomass"], since="2007-01-01", until="2013-12-31")
    assert '?date >= "2007-01-01"' in q
    assert '?date <= "2013-12-31"' in q


# ---------------------------------------------------------------------------
# snapshot writing / config / orchestration
# ---------------------------------------------------------------------------

def test_write_snapshot_shape(tmp_path):
    grants = [{"id": "g:1", "kind": "grant"}]
    policies = [{"id": "p:1", "kind": "policy"}]
    written = fd.write_snapshot(tmp_path, ["bioeconomy"], grants, policies)
    for name, items in (("grants", grants), ("policies", policies)):
        payload = json.loads(written[name].read_text(encoding="utf-8"))
        assert payload["keywords"] == ["bioeconomy"]
        assert payload["items"] == items
        assert payload["generated"].endswith("Z")


def test_load_snapshot_keywords_prefers_config(tmp_path):
    cfg_dir = tmp_path / "docs" / "finder" / "data"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "snapshot_config.json").write_text(
        json.dumps({"keywords": ["algae"]}), encoding="utf-8")
    assert fd.load_snapshot_keywords(tmp_path) == ["algae"]


def test_load_snapshot_keywords_defaults_without_config(tmp_path):
    assert fd.load_snapshot_keywords(tmp_path) == list(fd.DEFAULT_KEYWORDS)


def _patch_sources(monkeypatch, tmp_path, grants=None, policies=None,
                   grants_exc=None, policies_exc=None):
    """Point build_snapshot at a temp repo with stubbed fetchers."""
    monkeypatch.setattr(fd, "find_repo_root", lambda: tmp_path)

    def fake_grants(kws):
        if grants_exc:
            raise grants_exc
        return list(grants or [])

    def fake_policies(kws, since="2015-01-01", until=None):
        if policies_exc:
            raise policies_exc
        return list(policies or [])

    monkeypatch.setattr(fd, "fetch_grants", fake_grants)
    monkeypatch.setattr(fd, "fetch_policies", fake_policies)


def test_build_snapshot_monkeypatched(tmp_path, monkeypatch):
    _patch_sources(monkeypatch, tmp_path,
                   grants=[{"id": "g:x", "kind": "grant"}],
                   policies=[{"id": "p:x", "kind": "policy"}])
    out = tmp_path / "out"
    report = fd.build_snapshot(keywords=["biomass"], out_dir=out)
    assert report["grants"] == 1
    assert report["policies"] == 1
    assert report["errors"] == {}
    assert (out / "grants.json").exists()
    assert (out / "policies.json").exists()
    payload = json.loads((out / "policies.json").read_text(encoding="utf-8"))
    assert payload["items"][0]["id"] == "p:x"


def test_build_snapshot_survives_one_failing_source(tmp_path, monkeypatch):
    """A 400 from SEDIA must not cost us the EUR-Lex half of the snapshot."""
    _patch_sources(monkeypatch, tmp_path,
                   grants_exc=RuntimeError("400 Client Error"),
                   policies=[{"id": "p:x", "kind": "policy"}])
    out = tmp_path / "out"
    report = fd.build_snapshot(keywords=["biomass"], out_dir=out)
    assert report["policies"] == 1
    assert "grants" in report["errors"]
    assert (out / "policies.json").exists()
    assert json.loads((out / "policies.json").read_text(encoding="utf-8"))["items"]


def test_build_snapshot_keeps_existing_file_when_fetch_fails(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    good = {"generated": "2026-01-01T00:00:00Z", "keywords": ["x"],
            "items": [{"id": "g:kept", "kind": "grant"}]}
    (out / "grants.json").write_text(json.dumps(good), encoding="utf-8")

    _patch_sources(monkeypatch, tmp_path,
                   grants_exc=RuntimeError("boom"),
                   policies=[{"id": "p:x", "kind": "policy"}])
    report = fd.build_snapshot(keywords=["biomass"], out_dir=out)

    assert "grants" in report["skipped"]
    kept = json.loads((out / "grants.json").read_text(encoding="utf-8"))
    assert kept["items"][0]["id"] == "g:kept"      # not clobbered with an empty list
