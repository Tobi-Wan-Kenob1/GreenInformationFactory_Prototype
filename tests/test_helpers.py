"""Tests for helper.utils and helper.upload_collector."""
from pathlib import Path

from helper.utils import sha256_file, save_json, load_json, ensure_dir, utc_now_iso
from helper.upload_collector import _resolve_group, prepare_release_payload


def test_sha256_file_stable(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello world")
    # Known SHA-256 of "hello world"
    assert sha256_file(p) == (
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    )


def test_save_and_load_json_roundtrip(tmp_path):
    p = tmp_path / "nested" / "data.json"
    save_json(p, {"a": 1, "b": "ä"})  # non-ascii preserved
    assert load_json(p) == {"a": 1, "b": "ä"}


def test_utc_now_iso_has_offset():
    s = utc_now_iso()
    assert s.endswith("+00:00")


def test_resolve_group_prefixing(tmp_path):
    root = tmp_path
    ensure_dir(root / "data/processed/Train")
    items = ["Train/x.csv", "data/processed/Train/y.csv"]
    resolved = _resolve_group(items, root, Path("data/processed"))
    assert resolved[0] == root / "data/processed/Train/x.csv"
    assert resolved[1] == root / "data/processed/Train/y.csv"


def test_prepare_release_payload_copies_and_reports(tmp_path, monkeypatch):
    # Build a fake repo with a .git marker so _find_repo_root stops here.
    (tmp_path / ".git").mkdir()
    (tmp_path / "data/processed/Train").mkdir(parents=True)
    (tmp_path / "data/results").mkdir(parents=True)
    (tmp_path / "notebooks/models").mkdir(parents=True)
    (tmp_path / "data/processed/Train/X_train.csv").write_text("a,b\n1,2\n")
    (tmp_path / "data/results/plot.png").write_bytes(b"\x89PNG")
    (tmp_path / "notebooks/models/all_models.pkl").write_bytes(b"blob")

    monkeypatch.chdir(tmp_path)
    result = prepare_release_payload(
        files=["Train/X_train.csv"],
        results=["plot.png"],
        models=["all_models.pkl"],
    )
    names = {p.name for p in result["copied"]}
    assert names == {"X_train.csv", "plot.png", "all_models.pkl"}
    assert result["missing"] == []
    assert result["payload_dir"].is_dir()


def test_prepare_release_payload_reports_missing(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    result = prepare_release_payload(files=["nope.csv"], results=[], models=[])
    assert len(result["missing"]) == 1
    assert result["copied"] == []
