"""CORDIS adapter tests.

Built on synthetic archives that reproduce the quirks WP0 measured in the real
files — FP6's ``csv/`` nesting, ragged rows, and an ``ecSignatureDate`` column
that exists but is empty — because those are what the adapter exists to
survive. Nothing here touches the network.
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from gif import cordis

PROJECT_HEADER = [
    "id", "acronym", "status", "title", "startDate", "endDate", "totalCost",
    "ecMaxContribution", "legalBasis", "topics", "ecSignatureDate",
    "frameworkProgramme", "masterCall", "subCall", "fundingScheme", "nature",
    "objective", "contentUpdateDate", "rcn", "grantDoi",
]


def _project_row(pid, title, start, objective, contribution="1000000",
                 end="2012-12-31", acronym="ACR"):
    row = dict.fromkeys(PROJECT_HEADER, "")
    row.update({
        "id": pid, "acronym": acronym, "status": "CLOSED", "title": title,
        "startDate": start, "endDate": end, "totalCost": "2000000",
        "ecMaxContribution": contribution, "frameworkProgramme": "FP7",
        "masterCall": "FP7-KBBE-2010", "objective": objective,
        # Present and empty, exactly as the real archives have it.
        "ecSignatureDate": "",
    })
    return [row[c] for c in PROJECT_HEADER]


def _archive(rows, nested=False, euroscivoc=None, extra_raw=()):
    """A CORDIS-shaped zip in memory. `nested` mimics FP6's csv/ prefix."""
    prefix = "csv/" if nested else ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        lines = [";".join(PROJECT_HEADER)]
        lines += [";".join(r) for r in rows]
        lines += list(extra_raw)
        zf.writestr(f"{prefix}project.csv", "\n".join(lines) + "\n")
        if euroscivoc is not None:
            head = "projectID;euroSciVocCode;euroSciVocPath;euroSciVocTitle;euroSciVocDescription"
            body = [f"{pid};/1/2;/a/b;{title};" for pid, title in euroscivoc]
            zf.writestr(f"{prefix}euroSciVoc.csv", "\n".join([head] + body) + "\n")
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_reads_fp6_style_nested_archive_and_fp7_style_flat_one():
    """FP6 nests its CSVs under csv/; FP7 does not. One reader, both layouts."""
    rows = [_project_row("1", "Soil carbon in arable systems", "2005-01-01", "obj")]
    for nested in (False, True):
        report = cordis.projects_from_archive(_archive(rows, nested=nested), "fp6")
        assert report["projects_in_archive"] == 1
        assert report["items"][0]["title"] == "Soil carbon in arable systems"


def test_ragged_rows_are_skipped_not_misread():
    """A short row read positionally puts an objective where a date belongs."""
    good = _project_row("1", "Mine tailings reuse", "2009-06-01", "objective text")
    report = cordis.projects_from_archive(
        _archive([good], extra_raw=["2;ACR;CLOSED;Truncated record"]), "fp7")
    assert report["ragged_rows"] == 1
    assert [d["id"] for d in report["items"]] == ["c:fp7:1"]


def test_non_iso_date_never_becomes_a_date():
    """The failure WP0 hit: a mis-split row showing a programme name as a date."""
    assert cordis._iso("2009-06-01") == "2009-06-01"
    assert cordis._iso("FP7-PEOPLE") is None
    assert cordis._iso("") is None
    assert cordis._iso("the study of soils") is None


def test_available_at_uses_start_date_and_is_conservative():
    started_before = {"date": "2009-06-01"}
    started_after = {"date": "2010-02-01"}
    undated = {"date": None}

    assert cordis.available_at(started_before, "2009-12-31")
    assert not cordis.available_at(started_after, "2009-12-31")
    # Boundary belongs to the past.
    assert cordis.available_at({"date": "2009-12-31"}, "2009-12-31")
    # Undated records are excluded when a cut-off is given, kept when not.
    assert not cordis.available_at(undated, "2009-12-31")
    assert cordis.available_at(undated, None)


def test_as_of_excludes_projects_that_started_later():
    rows = [
        _project_row("1", "Soil carbon mapping", "2008-03-01", "soil objective"),
        _project_row("2", "Soil carbon mapping II", "2012-03-01", "soil objective"),
        _project_row("3", "Soil carbon mapping III", "", "soil objective"),
    ]
    report = cordis.projects_from_archive(_archive(rows), "fp7", as_of="2009-12-31")
    assert [d["id"] for d in report["items"]] == ["c:fp7:1"]
    assert report["dropped_window"] == 2


def test_no_as_of_keeps_everything_including_undated():
    rows = [
        _project_row("1", "Soil carbon", "2008-03-01", "obj"),
        _project_row("2", "Soil carbon later", "2012-03-01", "obj"),
        _project_row("3", "Soil carbon undated", "", "obj"),
    ]
    report = cordis.projects_from_archive(_archive(rows), "fp7")
    assert len(report["items"]) == 3
    assert report["dropped_window"] == 0


def test_keywords_match_on_a_word_boundary_not_a_substring():
    """The real-data failure: "mining" must not fire on "determining".

    A first run over the full archives matched 6 692 projects with substring
    matching, including work on bilingualism and fungus-farming ants, because
    "mining" is inside "determining" and "land" inside "Finland".
    """
    rows = [
        _project_row("1", "Mining waste valorisation", "2008-01-01", "obj"),
        _project_row("2", "Determining protein structures", "2008-01-01",
                     "a method for determining folds"),
        _project_row("3", "Research in Finland", "2008-01-01", "sited in Finland"),
        _project_row("4", "Land use change", "2008-01-01", "land cover"),
    ]
    report = cordis.projects_from_archive(_archive(rows), "fp7",
                                          keywords=["mining", "land"])
    kept = sorted(d["id"] for d in report["items"])
    assert kept == ["c:fp7:1", "c:fp7:4"], \
        "determining and Finland must not count as mining and land"

    # Leading boundary only, as the web app matches: plurals still count.
    plural = [_project_row("9", "Minings and quarryings", "2008-01-01", "obj")]
    assert cordis.projects_from_archive(_archive(plural), "fp7",
                                        keywords=["mining"])["items"]

    # And the same rule's cost, stated so it is a choice and not a surprise:
    # a leading boundary means "land" does not reach "grassland". That is the
    # app's behaviour, handled there by keyword expansion, and the snapshot
    # agreeing with the app matters more than either rule in isolation.
    compound = [_project_row("8", "Grassland carbon", "2008-01-01", "grassland soils")]
    assert cordis.projects_from_archive(_archive(compound), "fp7",
                                        keywords=["land"])["items"] == []


def test_multi_word_keywords_tolerate_whitespace():
    rows = [_project_row("1", "Towards a circular  economy for plastics",
                         "2008-01-01", "obj")]
    report = cordis.projects_from_archive(_archive(rows), "fp7",
                                          keywords=["circular economy"])
    assert len(report["items"]) == 1


def test_empty_keyword_list_keeps_everything():
    rows = [_project_row("1", "Quantum optics", "2008-01-01", "unrelated")]
    assert cordis.projects_from_archive(_archive(rows), "fp7", keywords=[])["items"]
    assert cordis.projects_from_archive(_archive(rows), "fp7", keywords=None)["items"]


def test_keywords_match_title_and_objective():
    rows = [
        _project_row("1", "Quarry rehabilitation", "2008-01-01", "restoring sites"),
        _project_row("2", "Novel alloys", "2008-01-01", "mining of rare earths"),
        _project_row("3", "Quantum optics", "2008-01-01", "unrelated work"),
    ]
    report = cordis.projects_from_archive(_archive(rows), "fp7",
                                          keywords=["quarry", "mining"])
    assert sorted(d["id"] for d in report["items"]) == ["c:fp7:1", "c:fp7:2"]
    assert report["dropped_keyword"] == 1


def test_euroscivoc_titles_enrich_the_summary():
    rows = [_project_row("1", "Biomass valorisation", "2008-01-01", "objective text")]
    report = cordis.projects_from_archive(
        _archive(rows, euroscivoc=[("1", "bioeconomy"), ("1", "circular economy")]),
        "fp7")
    summary = report["items"][0]["summary"]
    assert "objective text" in summary
    assert "bioeconomy" in summary and "circular economy" in summary


def test_normalized_project_is_a_past_award_not_an_open_call():
    rows = [_project_row("12345", "Carbon farming trial", "2009-04-01", "obj",
                         contribution="2500000.60")]
    doc = cordis.projects_from_archive(_archive(rows), "fp7")["items"][0]
    assert doc["kind"] == "grant"                 # same shape as a call topic
    assert doc["doctype"] == "Funded project"     # but labelled for what it is
    assert doc["deadline"] is None                # nothing to apply to
    # The CSV carries cents; the finder's budgets are whole euros. Which way an
    # exact half rounds is not worth pinning — it is one euro in millions.
    assert doc["budgetEUR"] == 2500001
    assert doc["url"] == "https://cordis.europa.eu/project/id/12345"
    assert doc["level"] == "EU"
    assert doc["date"] == "2009-04-01"


def test_unparseable_contribution_is_none_not_zero():
    rows = [_project_row("1", "No money recorded", "2008-01-01", "obj",
                         contribution="n/a")]
    doc = cordis.projects_from_archive(_archive(rows), "fp7")["items"][0]
    assert doc["budgetEUR"] is None


def test_archive_without_project_csv_says_what_it_found():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("csv/organization.csv", "projectID;name\n1;Someone\n")
    buf.seek(0)
    with pytest.raises(RuntimeError, match="no project.csv"):
        cordis.projects_from_archive(zipfile.ZipFile(buf), "fp6")


def test_ids_are_namespaced_per_programme():
    """The same numeric id can exist in two programmes; documents must not collide."""
    rows = [_project_row("1", "Same number", "2008-01-01", "obj")]
    fp6 = cordis.projects_from_archive(_archive(rows), "fp6")["items"][0]
    fp7 = cordis.projects_from_archive(_archive(rows), "fp7")["items"][0]
    assert fp6["id"] != fp7["id"]


def test_fetch_projects_rejects_unknown_programme():
    with pytest.raises(ValueError, match="unknown programme"):
        cordis.fetch_projects(programmes=["fp99"])


def test_fetch_projects_survives_one_failing_programme(monkeypatch):
    rows = [_project_row("1", "Soil work", "2008-01-01", "obj")]

    def fake_fetch(url, timeout=None):
        if "fp6" in url:
            raise RuntimeError("503 Service Unavailable")
        return _archive(rows)

    monkeypatch.setattr(cordis, "fetch_archive", fake_fetch)
    result = cordis.fetch_projects(programmes=["fp6", "fp7"], keywords=[])
    assert [d["id"] for d in result["items"]] == ["c:fp7:1"]
    assert "fp6" in result["errors"]


def test_fetch_projects_raises_only_when_every_programme_fails(monkeypatch):
    monkeypatch.setattr(cordis, "fetch_archive",
                        lambda url, timeout=None: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="every programme failed"):
        cordis.fetch_projects(programmes=["fp6", "fp7"])


def test_build_projects_writes_snapshot_with_its_window(tmp_path, monkeypatch):
    rows = [_project_row("1", "Soil carbon", "2008-01-01", "obj")]
    monkeypatch.setattr(cordis, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cordis, "fetch_archive", lambda url, timeout=None: _archive(rows))

    out = tmp_path / "out"
    report = cordis.build_projects(programmes=["fp7"], keywords=["soil"],
                                   out_dir=out, as_of="2009-12-31")
    assert report["projects"] == 1
    payload = json.loads((out / "projects.json").read_text(encoding="utf-8"))
    assert payload["window"] == {"since": None, "until": "2009-12-31"}
    assert payload["items"][0]["id"] == "c:fp7:1"
