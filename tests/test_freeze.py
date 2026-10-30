"""Tests for ``gif freeze``.

The point of the command is that a corpus can be checked later, so these tests
are mostly about the checks: that the manifest describes what is on disk, that
a changed file is detected, and that a corpus breaching its own window fails
loudly instead of being written and trusted.
"""
from __future__ import annotations

import json

import pytest

from gif import freeze as fz


def _write_corpus(path, policies=(), grants=(), projects=None, window=None):
    path.mkdir(parents=True, exist_ok=True)
    files = {"policies.json": policies, "grants.json": grants}
    if projects is not None:
        files["projects.json"] = projects
    for name, items in files.items():
        (path / name).write_text(json.dumps({
            "generated": "2026-10-30T00:00:00Z",
            "keywords": ["mining"],
            "window": window or {"since": None, "until": None},
            "items": list(items),
        }), encoding="utf-8")
    return path


def _doc(doc_id, date_str):
    return {"id": doc_id, "kind": "policy", "title": doc_id,
            "summary": "", "date": date_str}


def test_manifest_describes_every_file_present(tmp_path):
    corpus = _write_corpus(tmp_path / "c",
                           policies=[_doc("p:1", "2005-01-01"), _doc("p:2", "2009-06-01")],
                           grants=[], projects=[_doc("c:fp6:1", "2004-03-01")])
    manifest = fz.build_manifest(corpus, ["mining"], "2000-01-01", "2009-12-31",
                                 label="A1")
    names = {f["name"] for f in manifest["files"]}
    assert names == {"policies.json", "grants.json", "projects.json"}
    assert manifest["label"] == "A1"
    assert manifest["documents"] == 3
    assert manifest["window"] == {"since": "2000-01-01", "until": "2009-12-31"}

    policies = next(f for f in manifest["files"] if f["name"] == "policies.json")
    assert policies["items"] == 2
    assert policies["earliest"] == "2005-01-01"
    assert policies["latest"] == "2009-06-01"
    assert len(policies["sha256"]) == 64


def test_absent_source_is_omitted_not_invented(tmp_path):
    corpus = _write_corpus(tmp_path / "c", policies=[_doc("p:1", "2005-01-01")])
    manifest = fz.build_manifest(corpus, ["mining"], None, None)
    assert {f["name"] for f in manifest["files"]} == {"policies.json", "grants.json"}


def test_verify_detects_a_changed_corpus(tmp_path):
    corpus = _write_corpus(tmp_path / "c", policies=[_doc("p:1", "2005-01-01")])
    fz.write_manifest(corpus, fz.build_manifest(corpus, ["mining"], None, None))
    assert fz.verify(corpus)["ok"] is True

    # Edit one document — the kind of change that is invisible by inspection.
    payload = json.loads((corpus / "policies.json").read_text(encoding="utf-8"))
    payload["items"].append(_doc("p:2", "2024-01-01"))
    (corpus / "policies.json").write_text(json.dumps(payload), encoding="utf-8")

    result = fz.verify(corpus)
    assert result["ok"] is False
    changed = next(f for f in result["files"] if f["name"] == "policies.json")
    assert changed["status"] == "CHANGED"


def test_verify_reports_a_missing_file(tmp_path):
    corpus = _write_corpus(tmp_path / "c", policies=[_doc("p:1", "2005-01-01")])
    fz.write_manifest(corpus, fz.build_manifest(corpus, ["mining"], None, None))
    (corpus / "policies.json").unlink()
    result = fz.verify(corpus)
    assert result["ok"] is False
    assert any(f["status"] == "missing" for f in result["files"])


def test_window_check_separates_late_documents_from_undated_ones(tmp_path):
    corpus = _write_corpus(
        tmp_path / "c",
        policies=[_doc("p:ok", "2009-01-01"), _doc("p:late", "2011-01-01"),
                  _doc("p:unknown", None)])
    audit = fz.check_window(corpus, until="2009-12-31")
    assert [v["id"] for v in audit["violations"]] == ["p:late"]
    assert audit["undated"] == ["policies.json:p:unknown"]


def test_window_check_also_catches_documents_before_since(tmp_path):
    corpus = _write_corpus(tmp_path / "c",
                           policies=[_doc("p:early", "1998-01-01"),
                                     _doc("p:ok", "2005-01-01")])
    audit = fz.check_window(corpus, until="2009-12-31", since="2000-01-01")
    assert [v["id"] for v in audit["violations"]] == ["p:early"]


def test_freeze_fails_when_the_corpus_breaches_its_window(tmp_path, monkeypatch):
    """A corpus that quietly contains later documents is worse than none."""
    monkeypatch.setattr(fz, "find_repo_root", lambda: tmp_path)
    out = tmp_path / "frozen"

    def fake_snapshot(keywords=None, out_dir=None, since=None, until=None):
        _write_corpus(out_dir, policies=[_doc("p:late", "2015-01-01")])
        return {"errors": {}}

    import gif.finder_data as fd
    import gif.cordis as cd
    monkeypatch.setattr(fd, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(fd, "load_snapshot_keywords", lambda root=None: ["mining"])
    monkeypatch.setattr(cd, "build_projects", lambda **kw: {"projects": 0})

    with pytest.raises(RuntimeError, match="not a record of that period"):
        fz.freeze(out, since="2000-01-01", until="2009-12-31", label="A1")

    # The manifest is still written, so the breach can be inspected rather than
    # only reported in an exception that scrolls past.
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["window_violations"][0]["id"] == "p:late"


def test_freeze_writes_manifest_and_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(fz, "find_repo_root", lambda: tmp_path)
    out = tmp_path / "frozen"

    import gif.finder_data as fd
    import gif.cordis as cd

    def fake_snapshot(keywords=None, out_dir=None, since=None, until=None):
        _write_corpus(out_dir, policies=[_doc("p:1", "2005-01-01")], grants=[])
        return {"errors": {}}

    def fake_projects(programmes=None, keywords=None, out_dir=None,
                      as_of=None, since=None):
        (out_dir / "projects.json").write_text(json.dumps({
            "generated": "2026-10-30T00:00:00Z", "keywords": keywords,
            "window": {"since": since, "until": as_of},
            "items": [_doc("c:fp6:1", "2004-03-01")]}), encoding="utf-8")
        return {"projects": 1}

    monkeypatch.setattr(fd, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(fd, "load_snapshot_keywords", lambda root=None: ["mining"])
    monkeypatch.setattr(cd, "build_projects", fake_projects)

    report = fz.freeze(out, since="2000-01-01", until="2009-12-31", label="A1")
    assert report["documents"] == 2
    assert fz.verify(out)["ok"] is True
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"] == "A1"
    assert manifest["keywords"] == ["mining"]


def test_freeze_refuses_a_partially_fetched_corpus(tmp_path, monkeypatch):
    """Two runs minutes apart gave 148 and 111 policies, both recorded clean.

    Partial failures — some keywords or some date slices erroring while others
    succeed — used to be printed and forgotten, so a corpus missing whole
    slices looked complete. A corpus like that is an unknown fraction of its
    period and its size means nothing, so freezing it has to fail.
    """
    monkeypatch.setattr(fz, "find_repo_root", lambda: tmp_path)
    out = tmp_path / "frozen"
    import gif.cordis as cd
    import gif.finder_data as fd

    def fake_snapshot(keywords=None, out_dir=None, since=None, until=None):
        _write_corpus(out_dir, policies=[_doc("p:1", "2005-01-01")])
        return {"errors": {}, "partial": {"policies": ["2000-2004: HTTP 500"]}}

    monkeypatch.setattr(fd, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(fd, "load_snapshot_keywords", lambda root=None: ["mining"])
    monkeypatch.setattr(cd, "build_projects", lambda **kw: {"projects": 0})

    with pytest.raises(RuntimeError, match="unknown fraction"):
        fz.freeze(out, until="2009-12-31", label="A1")

    # Written anyway, so the incompleteness is inspectable.
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is False
    assert manifest["partial_failures"]["policies"] == ["2000-2004: HTTP 500"]

    # And keepable on purpose, for a known-degraded source.
    report = fz.freeze(out, until="2009-12-31", label="A1", allow_partial=True)
    assert report["complete"] is False
    assert report["partial_failures"]["policies"]


def test_partial_failures_reach_the_caller(monkeypatch):
    """fetch_policies collected failures and then dropped them on the floor."""
    import gif.finder_data as fd
    calls = []

    def fake_cellar(keywords, since, until, limit):
        calls.append(since)
        if since.startswith("2000"):
            raise RuntimeError("HTTP 500")
        return [{"id": f"p:{since[:4]}", "kind": "policy", "date": f"{since[:4]}-06-01",
                 "title": "act", "summary": ""}]

    monkeypatch.setattr(fd, "_cellar_query", fake_cellar)
    failures = []
    docs = fd.fetch_policies(["mining"], since="2000-01-01", until="2009-12-31",
                             failures_out=failures)
    assert docs, "the slices that worked should still be returned"
    assert len(failures) == 1 and "HTTP 500" in failures[0]


def test_freeze_can_skip_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(fz, "find_repo_root", lambda: tmp_path)
    out = tmp_path / "frozen"
    import gif.finder_data as fd
    import gif.cordis as cd
    called = []

    monkeypatch.setattr(fd, "build_snapshot",
                        lambda keywords=None, out_dir=None, since=None, until=None:
                        (_write_corpus(out_dir, policies=[_doc("p:1", "2005-01-01")]),
                         {"errors": {}})[1])
    monkeypatch.setattr(fd, "load_snapshot_keywords", lambda root=None: ["mining"])
    monkeypatch.setattr(cd, "build_projects",
                        lambda **kw: called.append(kw) or {"projects": 0})

    fz.freeze(out, until="2009-12-31", skip_projects=True)
    assert called == [], "CORDIS must not be fetched when it is skipped"
    assert not (out / "projects.json").exists()


def test_tool_version_reports_commit_and_dirty_state():
    """Provenance has to say 'dirty', not just give a hash.

    A corpus built from uncommitted changes cannot be rebuilt from the
    repository, so a manifest that implied a clean provenance would be
    misleading in exactly the case that matters.
    """
    version = fz.tool_version()
    assert set(version) == {"commit", "dirty", "untracked"}
    if version["commit"] is not None:
        assert len(version["commit"]) == 40
        assert isinstance(version["dirty"], bool)
        assert isinstance(version["untracked"], int)


def test_untracked_files_do_not_make_a_corpus_unreproducible(tmp_path):
    """The first real run came back dirty because of an egg-info directory.

    An editable install drops one in the tree. Treating that as unreproducible
    would train the reader to ignore the flag, which is worse than not having
    one, so untracked files are counted instead of raising it.
    """
    import subprocess
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e", "PATH": "/usr/bin:/bin"}
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True,
                                    capture_output=True, env=env)
    run("init", "-q")
    (repo / "src" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "initial")

    clean = fz.tool_version(repo)
    assert clean["dirty"] is False and clean["untracked"] == 0

    (repo / "thing.egg-info").mkdir()
    (repo / "thing.egg-info" / "PKG-INFO").write_text("meta\n", encoding="utf-8")
    with_untracked = fz.tool_version(repo)
    assert with_untracked["dirty"] is False, "an untracked build artifact is not a code change"
    assert with_untracked["untracked"] >= 1

    (repo / "src" / "mod.py").write_text("x = 2\n", encoding="utf-8")
    modified = fz.tool_version(repo)
    assert modified["dirty"] is True, "a modified tracked file must still flag"
