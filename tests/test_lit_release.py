"""Tests for gif.lit_release (staging only — never touches the network)."""
import json

from gif.lit_release import (
    default_release_params, collect_release_files, stage_literature_release,
    GIF_SOFTWARE_DOI,
)
from gif.literature import D12_FULL_LIST_DOI, D12_CODEBOOK_DOI


def _fake_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "metadata").mkdir()
    lp = tmp_path / "data/processed/literature"
    lr = tmp_path / "data/results/literature"
    lm = tmp_path / "notebooks/models"
    for d in (lp, lr, lm):
        d.mkdir(parents=True)
    (lp / "papers.csv").write_text("paper_id,title\n0,A\n")
    (lp / "codes_long.csv").write_text("paper_id,dimension,source,code\n0,barriers,title_kw,cost\n")
    (lr / "lit_top_codes.csv").write_text("dimension,code,papers\nbarriers,cost,1\n")
    (lr / "lit_coding_f1_by_task.png").write_bytes(b"\x89PNG")
    (lm / "literature_coder.pkl").write_bytes(b"blob")
    return tmp_path


def test_default_params_are_safe_and_attributed():
    params = default_release_params()
    assert params["use_sandbox"] is True                 # sandbox-first
    assert params["license"] == "cc-by-4.0"              # derivative of CC-BY data
    assert params["related_dois"] == [D12_FULL_LIST_DOI, D12_CODEBOOK_DOI]
    desc = params["description"]
    assert "Guerreschi" in desc and GIF_SOFTWARE_DOI in desc


def test_collect_release_files_lists_existing(tmp_path):
    repo = _fake_repo(tmp_path)
    groups = collect_release_files(repo)
    assert "data/processed/literature/papers.csv" in groups["files"]
    assert any("lit_top_codes.csv" in f for f in groups["results"])
    assert groups["models"] == ["notebooks/models/literature_coder.pkl"]


def test_stage_release_copies_payload_and_writes_params(tmp_path):
    repo = _fake_repo(tmp_path)
    report = stage_literature_release(repo_root=repo, log=False)
    assert set(report["copied"]) == {
        "papers.csv", "codes_long.csv", "lit_top_codes.csv",
        "lit_coding_f1_by_task.png", "literature_coder.pkl",
    }
    assert report["missing"] == []
    assert (repo / "notebooks/release_payload/papers.csv").exists()

    params = json.loads((repo / "metadata/zenodo_params.json").read_text(encoding="utf-8"))
    assert params["use_sandbox"] is True
    assert params["license"] == "cc-by-4.0"
    assert params["related_dois"] == [D12_FULL_LIST_DOI, D12_CODEBOOK_DOI]
    assert params["creators"][0]["name"] == "Rosnitschek, Tobias"


def test_stage_release_production_flag(tmp_path):
    repo = _fake_repo(tmp_path)
    stage_literature_release(repo_root=repo, use_sandbox=False, log=False)
    params = json.loads((repo / "metadata/zenodo_params.json").read_text(encoding="utf-8"))
    assert params["use_sandbox"] is False


def test_stage_release_cleans_previous_payload(tmp_path):
    repo = _fake_repo(tmp_path)
    payload = repo / "notebooks/release_payload"
    payload.mkdir(parents=True)
    (payload / "stale_from_older_release.csv").write_text("x")
    report = stage_literature_release(repo_root=repo, log=False)
    assert not (payload / "stale_from_older_release.csv").exists()
    assert "papers.csv" in report["copied"]
