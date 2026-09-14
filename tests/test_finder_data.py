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


def test_extract_budget_from_budget_year_map():
    """The real shape: money lives under budgetTopicActionMap.*.budgetYearMap."""
    overview = json.dumps({"budgetTopicActionMap": {"3203666": [
        {"action": "BBI-RIA", "budgetYearMap": {"2016": 188650000}},
    ]}})
    assert fd.extract_budget_eur({"budgetOverview": [overview]}) == 188650000


def test_budget_year_map_spans_years_but_not_duplicated_actions():
    overview = json.dumps({"budgetTopicActionMap": {"1": [
        {"action": "RIA", "budgetYearMap": {"2024": 10000000, "2025": 5000000}},
        {"action": "IA", "budgetYearMap": {"2024": 10000000, "2025": 5000000}},
    ]}})
    # years summed within a map (15M), identical actions not double-counted
    assert fd.extract_budget_eur({"budgetOverview": [overview]}) == 15000000


def test_extract_budget_from_indicative_free_text():
    meta = {"additionalInfos": [
        '{"additionalInfo":"<p>Indicative budget: 188.65 Million Euros</p>"}']}
    assert fd.extract_budget_eur(meta) == 188650000


def test_is_call_topic_filters_faqs_and_tenders():
    topic = {"metadata": {"type": ["1"], "identifier": ["BBI-2016-S04"]}}
    assert fd.is_call_topic(topic) is True
    assert fd.is_call_topic({"metadata": {"type": ["3"], "identifier": ["x"]}}) is False
    assert fd.is_call_topic({"metadata": {"type": ["2"], "identifier": ["x"]}}) is False
    assert fd.is_call_topic({"metadata": {}}) is False


def test_is_call_topic_rejects_faqs_indexed_as_type_1():
    """Some FAQ entries carry type 1; they have no topic identifier."""
    faq = {"metadata": {"type": ["1"], "esST_nid": ["11815"],
                        "esST_question": ["Can the proposal use biomass plus plastic?"]}}
    assert fd.is_call_topic(faq) is False
    # even with an identifier, an FAQ question disqualifies it
    faq_with_id = dict(faq)
    faq_with_id["metadata"] = dict(faq["metadata"], identifier=["11815"])
    assert fd.is_call_topic(faq_with_id) is False


def test_fetch_grants_drops_non_topic_results(monkeypatch):
    faq = {"metadata": {"type": ["3"], "esST_nid": ["51816"]}}
    topic = {"metadata": {"type": ["1"], "identifier": ["BBI-2016-S04"],
                          "title": ["Clustering and networking"]}}
    _record_posts(monkeypatch, lambda text: FakeResp([faq, topic]))
    docs = fd.fetch_grants(["bioeconomy"])
    assert [d["id"] for d in docs] == ["g:BBI-2016-S04"]


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
            "deadlineDate": ["2026-02-18T00:00:00.000+0000"],
            "callIdentifier": ["HORIZON-CL6-2025-02"],
            "programmePeriod": ["2021 - 2027"],
            "status": ["31094502"],
            "keywords": ["Circular economy", "biomass"],
            "tags": ["biomass", "valorisation"],
            "type": ["1"],
            "budget": ["12000000"],
        },
    })
    assert doc["id"] == "g:HORIZON-CL6-2025-CIRCBIO-01-1"
    assert doc["kind"] == "grant"
    assert doc["title"] == "Circular solutions"          # tags stripped, ws collapsed
    assert doc["summary"].startswith("Bio-based value chains.")
    assert doc["date"] == "2025-09-15"
    assert doc["deadline"] == "2026-02-18"
    assert doc["callId"] == "HORIZON-CL6-2025-02"
    assert doc["programmePeriod"] == "2021 - 2027"
    assert doc["budgetEUR"] == 12000000
    assert doc["doctype"] == "Call topic"
    assert "topic-details/horizon-cl6-2025-circbio-01-1" in doc["url"]
    # curated keywords/tags are appended once each for the topic analytics
    assert "Circular economy" in doc["summary"]
    assert doc["summary"].count("valorisation") == 1
    assert doc["summary"].count("biomass") == 1


def test_normalize_grant_falls_back_to_sort_date_and_description_byte():
    doc = fd.normalize_grant({"metadata": {
        "identifier": ["BBI-2016-S04"],
        "title": ["Clustering and networking for new value chains"],
        "descriptionByte": ["<SPAN class='x'>Specific Challenge</SPAN>:<p>Effectively…</p>"],
        "es_SortDate": ["2016-04-19T00:00:00.000+0000"],
        "type": ["1"],
    }})
    assert doc["date"] == "2016-04-19"
    assert doc["summary"].startswith("Specific Challenge")
    assert "<" not in doc["summary"]


class FakeResp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, results=(), status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self._results = list(results)

    def json(self):
        return {"results": self._results}


def _record_posts(monkeypatch, responder):
    """Capture every SEDIA request; `responder(text)` supplies the response."""
    calls = []

    def fake_post(url, params=None, data=None, files=None, timeout=None):
        calls.append({"params": params, "data": data, "files": files})
        return responder(params["text"])

    monkeypatch.setattr(fd.requests, "post", fake_post)
    return calls


def test_fetch_grants_queries_one_keyword_at_a_time(monkeypatch):
    """A combined OR query blows the API's 100mb result-set limit."""
    calls = _record_posts(monkeypatch, lambda text: FakeResp())
    fd.fetch_grants(["biomass", "soil", "carbon capture"])

    assert len(calls) == 3
    texts = [c["params"]["text"] for c in calls]
    assert texts == ['"biomass"', '"soil"', '"carbon capture"']
    assert not any(" OR " in t for t in texts)


def test_fetch_grants_caps_page_size_and_posts_form_encoded(monkeypatch):
    calls = _record_posts(monkeypatch, lambda text: FakeResp())
    fd.fetch_grants(["biomass"], page_size=500)

    assert int(calls[0]["params"]["pageSize"]) <= fd.MAX_PAGE_SIZE
    assert calls[0]["files"] is None        # multipart → 500 from the API
    assert "query" in calls[0]["data"]      # form-urlencoded payload


def test_fetch_grants_keeps_other_keywords_when_one_fails(monkeypatch):
    def responder(text):
        if "soil" in text:
            return FakeResp(status_code=400, text="Result size limit 100mb has been reached")
        return FakeResp([{"metadata": {"type": ["1"], "identifier": ["T-" + text.strip('"')]}}])

    _record_posts(monkeypatch, responder)
    docs = fd.fetch_grants(["biomass", "soil", "carbon capture"])

    ids = {d["id"] for d in docs}
    assert ids == {"g:T-biomass", "g:T-carbon capture"}
    assert all(d["matchedKeyword"] in ("biomass", "carbon capture") for d in docs)


def test_fetch_grants_raises_only_when_every_keyword_fails(monkeypatch):
    _record_posts(monkeypatch,
                  lambda text: FakeResp(status_code=400, text="Result size limit 100mb"))
    with pytest.raises(RuntimeError, match="every keyword query failed"):
        fd.fetch_grants(["biomass", "soil"])


def test_fetch_grants_error_surfaces_api_message(monkeypatch):
    _record_posts(monkeypatch,
                  lambda text: FakeResp(status_code=400, text="Result size limit 100mb"))
    with pytest.raises(RuntimeError, match="Result size limit 100mb"):
        fd.fetch_grants(["biomass"])


def test_fetch_grants_deduplicates_across_keywords(monkeypatch):
    same = [{"metadata": {"type": ["1"], "identifier": ["SHARED-1"]}}]
    _record_posts(monkeypatch, lambda text: FakeResp(same))
    docs = fd.fetch_grants(["biomass", "soil"])
    assert len(docs) == 1
    assert docs[0]["matchedKeyword"] == "biomass"     # first keyword wins


def test_fetch_grants_can_exclude_closed_calls(monkeypatch):
    calls = _record_posts(monkeypatch, lambda text: FakeResp())

    fd.fetch_grants(["biomass"], include_closed=False)
    assert fd.STATUS_CLOSED not in calls[-1]["data"]["query"]
    assert fd.STATUS_OPEN in calls[-1]["data"]["query"]

    fd.fetch_grants(["biomass"], include_closed=True)
    assert fd.STATUS_CLOSED in calls[-1]["data"]["query"]


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
        "subjects": {"value": "climate change, greenhouse gas, reduction of gas emissions"},
        "force": {"value": "true"},
    }


def test_normalize_policy_uses_eurovoc_subjects_as_summary():
    """CELLAR has no abstract, so the EuroVoc descriptors carry the topic signal."""
    doc = fd.normalize_policy(_binding())
    assert "climate change" in doc["summary"]
    assert doc["subjects"] == ["climate change", "greenhouse gas",
                               "reduction of gas emissions"]
    assert doc["inForce"] is True


def test_normalize_policy_without_subjects_or_force():
    b = _binding()
    del b["subjects"]
    del b["force"]
    doc = fd.normalize_policy(b)
    assert doc["summary"] == ""
    assert doc["subjects"] == []
    assert doc["inForce"] is None


def test_normalize_policy_marks_repealed_acts():
    b = _binding()
    b["force"] = {"value": "false"}
    assert fd.normalize_policy(b)["inForce"] is False


def test_sparql_query_requests_eurovoc_subjects():
    q = fd.sparql_query(["biomass"])
    assert "work_is_about_concept_eurovoc" in q
    assert "GROUP_CONCAT" in q
    assert "GROUP BY" in q
    assert "skos:prefLabel" in q


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


def test_expand_keyword_covers_eu_spelling_variants():
    bio = fd.expand_keyword("bioeconomy")
    assert "bioeconomy" in bio
    assert "bio-economy" in bio          # the spelling EUR-Lex titles often use
    assert "bio economy" in bio

    ce = fd.expand_keyword("circular economy")
    assert "circular-economy" in ce
    assert "circulareconomy" in ce

    assert "biofuel" in fd.expand_keyword("biofuels")     # plural → singular
    assert "biomasss" not in fd.expand_keyword("biomass")  # no bogus plural


def test_expand_keyword_is_conservative():
    """Spelling variants only — no semantic widening."""
    assert "renewables" not in fd.expand_keyword("solar")
    assert "energy" not in fd.expand_keyword("renewable energy")
    assert fd.expand_keyword("") == []


def test_expand_keywords_dedupes_and_preserves_order():
    out = fd.expand_keywords(["biomass", "biomass", "soil"])
    assert out[0] == "biomass"
    assert len(out) == len(set(out))
    assert "soil" in out


THESAURUS = {
    "muck": ["manure", "muck", "slurry", "organic fertiliser"],
    "manure": ["manure", "muck", "slurry", "organic fertiliser"],
    "slurry": ["manure", "muck", "slurry", "organic fertiliser"],
    "organic fertiliser": ["manure", "muck", "slurry", "organic fertiliser"],
}


def test_synonyms_map_plain_language_to_jargon():
    """A practitioner types 'muck'; the act says 'organic fertiliser'."""
    syn = fd.synonyms_for("muck", THESAURUS)
    assert "manure" in syn and "organic fertiliser" in syn
    assert "muck" not in syn                       # never itself


def test_synonyms_are_bidirectional():
    """Typing the jargon must also find the plain word — grant abstracts are plainer."""
    assert "muck" in fd.synonyms_for("organic fertiliser", THESAURUS)


def test_synonyms_ignore_case_and_spacing():
    assert fd.synonyms_for("Organic-Fertiliser", THESAURUS)
    assert fd.synonyms_for("unknown term", THESAURUS) == []


def test_expand_keywords_folds_in_synonyms_only_when_asked():
    plain = fd.expand_keywords(["muck"], THESAURUS, use_synonyms=False)
    rich = fd.expand_keywords(["muck"], THESAURUS, use_synonyms=True)
    assert "manure" not in plain
    assert "manure" in rich
    assert "organic fertiliser" in rich
    assert "organic-fertiliser" in rich             # orthographic variants too


def test_plural_of_consonant_y_words():
    assert "slurries" in fd.expand_keyword("slurry")
    assert "slurrys" not in fd.expand_keyword("slurry")


def test_sparql_query_uses_synonyms_and_caps_term_count():
    q = fd.sparql_query(["muck"], use_synonyms=True, thesaurus=THESAURUS)
    assert '"manure"' in q and '"organic fertiliser"' in q
    # the cap protects the endpoint from an over-expanded filter
    many = [f"kw{i}" for i in range(60)]
    capped = fd.sparql_query(many)
    assert capped.count("CONTAINS(") <= fd.MAX_SPARQL_TERMS


def test_sparql_query_includes_keyword_variants():
    q = fd.sparql_query(["bioeconomy"])
    assert '"bioeconomy"' in q
    assert '"bio-economy"' in q


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


def test_date_buckets_split_the_window():
    buckets = fd.date_buckets("2000-01-01", "2014-12-31", span_years=5)
    assert buckets == [("2000-01-01", "2004-12-31"),
                       ("2005-01-01", "2009-12-31"),
                       ("2010-01-01", "2014-12-31")]


def test_date_buckets_handle_short_and_inverted_windows():
    assert fd.date_buckets("2020-01-01", "2020-12-31", 5) == [("2020-01-01", "2020-12-31")]
    # an inverted window must not loop forever or return nothing
    assert len(fd.date_buckets("2020-01-01", "2010-12-31", 5)) == 1


def test_fetch_policies_samples_every_period(monkeypatch):
    """ORDER BY DESC + LIMIT returns only the newest slice for broad keywords,
    so each period is queried separately or historical depth is lost."""
    asked = []

    def fake_query(keywords, since, until, limit):
        asked.append((since[:4], until[:4]))
        year = since[:4]
        return [{"id": f"p:{year}", "kind": "policy", "date": f"{year}-06-01"}]

    monkeypatch.setattr(fd, "_cellar_query", fake_query)
    docs = fd.fetch_policies(["mining"], since="2000-01-01", until="2019-12-31",
                             span_years=5)

    assert [a[0] for a in asked] == ["2000", "2005", "2010", "2015"]
    assert {d["id"] for d in docs} == {"p:2000", "p:2005", "p:2010", "p:2015"}
    assert [d["date"] for d in docs] == sorted((d["date"] for d in docs), reverse=True)


def test_fetch_policies_survives_one_failing_slice(monkeypatch):
    def fake_query(keywords, since, until, limit):
        if since.startswith("2005"):
            raise RuntimeError("CELLAR timeout")
        return [{"id": f"p:{since[:4]}", "kind": "policy", "date": f"{since[:4]}-06-01"}]

    monkeypatch.setattr(fd, "_cellar_query", fake_query)
    docs = fd.fetch_policies(["mining"], since="2000-01-01", until="2014-12-31",
                             span_years=5)
    assert {d["id"] for d in docs} == {"p:2000", "p:2010"}


def test_fetch_policies_raises_when_every_slice_fails(monkeypatch):
    monkeypatch.setattr(fd, "_cellar_query",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(RuntimeError, match="every CELLAR slice failed"):
        fd.fetch_policies(["mining"], since="2000-01-01", until="2009-12-31")


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
