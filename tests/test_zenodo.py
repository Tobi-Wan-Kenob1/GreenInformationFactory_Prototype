"""Tests for gif.zenodo (no network access required)."""
import pytest

from gif.zenodo import record_id_from_doi, record_summary, verify_checksum


def test_record_id_from_doi_variants():
    assert record_id_from_doi("10.5281/zenodo.20743706") == "20743706"
    assert record_id_from_doi("https://doi.org/10.5281/zenodo.16256961") == "16256961"
    assert record_id_from_doi("https://zenodo.org/records/12345") == "12345"
    assert record_id_from_doi("12345") == "12345"
    assert record_id_from_doi(" 10.5281/zenodo.7 ") == "7"


def test_record_id_from_doi_rejects_garbage():
    with pytest.raises(ValueError):
        record_id_from_doi("not-a-doi")


def test_verify_checksum_md5(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello world")
    md5 = "5eb63bbbe01eeed093cb22bb8f5acdc3"  # md5 of "hello world"
    assert verify_checksum(p, f"md5:{md5}")
    assert not verify_checksum(p, "md5:" + "0" * 32)


def test_verify_checksum_absent_or_unsupported(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"x")
    assert verify_checksum(p, None)          # nothing to verify against
    assert verify_checksum(p, "")            # empty
    assert verify_checksum(p, "sha256:abc")  # unsupported scheme: skip


def test_record_summary_extracts_fields():
    record = {
        "id": 20743706,
        "doi": "10.5281/zenodo.20743706",
        "metadata": {
            "title": "WP1_D1.2_Literature Results",
            "publication_date": "2026-06-18",
            "resource_type": {"title": "Dataset"},
        },
        "files": [{"key": "list.xlsx", "size": 436366, "checksum": "md5:abc"}],
        "links": {"self_html": "https://zenodo.org/records/20743706"},
    }
    s = record_summary(record)
    assert s["record_id"] == 20743706
    assert s["doi"] == "10.5281/zenodo.20743706"
    assert s["publication_date"] == "2026-06-18"
    assert s["resource_type"] == "Dataset"
    assert s["files"][0]["key"] == "list.xlsx"
