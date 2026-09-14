"""Tests for gif.finder_codebook (WP1/D1.2 code vocabulary for the finder)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from gif import finder_codebook as fc


@pytest.fixture()
def lit_dir(tmp_path):
    """A miniature codes_long.csv with variants, a singleton and a generic code."""
    rows = [
        # "landscape"/"landscapes" are the same code in substance
        (1, "barriers", "kw", "landscape"),
        (2, "barriers", "kw", "landscapes"),
        (3, "barriers", "kw", "Landscape"),
        # a code recorded twice for the same paper must count once
        (4, "barriers", "kw", "water"),
        (4, "barriers", "abstract", "water"),
        (5, "barriers", "kw", "water"),
        # below min_papers
        (6, "barriers", "kw", "singleton"),
        # too generic to carry signal
        (7, "barriers", "kw", "data"),
        (8, "barriers", "kw", "data"),
        # other dimensions
        (1, "drivers", "kw", "demand"),
        (2, "drivers", "kw", "demands"),
        (1, "stakeholders", "kw", "policy makers"),
        (2, "stakeholders", "kw", "policymakers"),
        (1, "bio", "kw", "biogas"),
        (2, "bio", "kw", "biogas"),
        (1, "ce", "kw", "recycling"),
        (2, "ce", "kw", "recycling"),
    ]
    df = pd.DataFrame(rows, columns=["paper_id", "dimension", "source", "code"])
    d = tmp_path / "lit"
    d.mkdir()
    df.to_csv(d / "codes_long.csv", index=False)
    return d


def _codes(book, dimension):
    return {e["code"]: e for e in book["dimensions"][dimension]}


def test_canonical_collapses_spelling_variants():
    assert fc.canonical("landscapes") == fc.canonical("landscape")
    assert fc.canonical("policy makers") == fc.canonical("policymakers")
    assert fc.canonical("Water") == "water"
    assert fc.canonical("waste management") == "wastemanagement"
    # short words and double-s keep their s
    assert fc.canonical("biomass") == "biomass"


def test_variants_are_merged_into_one_code(lit_dir):
    book = fc.build_codebook(lit_dir=lit_dir, min_papers=2)
    barriers = _codes(book, "barriers")
    assert "landscape" in barriers                    # most frequent surface form
    assert "landscapes" not in barriers
    assert barriers["landscape"]["papers"] == 3       # three distinct papers
    assert set(barriers["landscape"]["terms"]) == {"landscape", "landscapes"}


def test_code_counted_once_per_paper(lit_dir):
    book = fc.build_codebook(lit_dir=lit_dir, min_papers=2)
    # paper 4 recorded "water" twice (title kw + abstract) → still one paper
    assert _codes(book, "barriers")["water"]["papers"] == 2


def test_rare_and_generic_codes_are_dropped(lit_dir):
    book = fc.build_codebook(lit_dir=lit_dir, min_papers=2)
    barriers = _codes(book, "barriers")
    assert "singleton" not in barriers                # below min_papers
    assert "data" not in barriers                     # in TOO_GENERIC


def test_all_dimensions_present_and_ordered(lit_dir):
    book = fc.build_codebook(lit_dir=lit_dir, min_papers=2)
    assert set(book["dimensions"]) <= set(fc.DIMENSIONS)
    for dim in ("barriers", "drivers", "stakeholders", "bio", "ce"):
        assert dim in book["dimensions"], dim
    counts = [e["papers"] for e in book["dimensions"]["barriers"]]
    assert counts == sorted(counts, reverse=True)     # most-cited first


def test_top_per_dimension_caps_the_list(lit_dir):
    book = fc.build_codebook(lit_dir=lit_dir, min_papers=2, top_per_dimension=1)
    assert len(book["dimensions"]["barriers"]) == 1


def test_metadata_documents_provenance_and_method(lit_dir):
    book = fc.build_codebook(lit_dir=lit_dir, min_papers=2)
    assert "zenodo.20744025" in book["source"]
    assert "agriculture and mining" in book["scope"]
    assert "Lexical match only" in book["method"]
    assert book["dimension_labels"]["ce"] == "Circular economy"


def test_write_codebook_emits_loadable_json(tmp_path, lit_dir):
    path = fc.write_codebook(out_dir=tmp_path, lit_dir=lit_dir, min_papers=2)
    assert path.name == "wp1_codebook.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dimensions"]["bio"][0]["code"] == "biogas"
    assert payload["generated"].endswith("Z")
