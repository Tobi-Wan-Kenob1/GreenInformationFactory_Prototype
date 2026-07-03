"""Tests for gif.lit_analytics (synthetic corpus, no I/O beyond tmp_path)."""
import matplotlib
matplotlib.use("Agg")

import pandas as pd

from gif.lit_analytics import (
    code_frequencies, code_frequencies_by_sector, code_cooccurrence,
    explode_countries, normalize_geo_level, crosstab_by_sector,
    year_distribution, run_literature_analytics,
)


def _papers():
    return pd.DataFrame({
        "paper_id": [0, 1, 2, 3],
        "title": ["A", "B", "C", "D"],
        "sector_tag": ["AGRI_EU", "AGRI_EU", "MINING_EU", "AGRI_OUT"],
        "countries_mentioned": ["Italy, Germany", "Italy", "", "Kenya"],
        "geographic_level": ["Nazionale", "NUTS 2, Nazionale", "", "National"],
        "relevance": ["Alta", "", "Media", ""],
        "year": [2024, 2024, 2025, 2023],
        "abstract": ["x", "y", "z", "w"],
    })


def _codes():
    return pd.DataFrame({
        # paper 0 has "cost" from BOTH sources -> must count once
        "paper_id": [0, 0, 1, 2, 0, 1, 3],
        "dimension": ["barriers", "barriers", "barriers", "barriers",
                      "drivers", "drivers", "drivers"],
        "source": ["title_kw", "abstract", "title_kw", "title_kw",
                   "abstract", "abstract", "title_kw"],
        "code": ["cost", "cost", "cost", "policy", "demand", "demand", "tech"],
    })


def test_code_frequencies_dedups_per_paper():
    freq = code_frequencies(_codes(), dimension="barriers")
    cost = freq[freq["code"] == "cost"]["papers"].iloc[0]
    assert cost == 2  # papers 0 and 1, not 3 raw rows


def test_code_frequencies_top_per_dimension():
    freq = code_frequencies(_codes(), top=1)
    assert set(freq["dimension"]) == {"barriers", "drivers"}
    assert len(freq) == 2


def test_code_frequencies_by_sector_pivot():
    piv = code_frequencies_by_sector(_codes(), _papers(), "barriers")
    row = piv[piv["code"] == "cost"].iloc[0]
    assert row["AGRI_EU"] == 2 and row["total"] == 2


def test_code_cooccurrence_counts_shared_papers():
    cooc = code_cooccurrence(_codes(), "barriers", "drivers", min_count=1)
    assert cooc.loc["cost", "demand"] == 2  # papers 0 and 1


def test_code_cooccurrence_min_count_filters():
    cooc = code_cooccurrence(_codes(), "barriers", "drivers", min_count=2)
    assert "policy" not in cooc.index  # only 1 paper


def test_explode_countries():
    cc = explode_countries(_papers())
    assert cc[cc["country"] == "Italy"]["papers"].iloc[0] == 2
    assert cc[cc["country"] == "Kenya"]["papers"].iloc[0] == 1
    assert "" not in set(cc["country"])


def test_normalize_geo_level_merges_it_en():
    geo = normalize_geo_level(_papers())
    nat = geo[geo["geo_level"] == "National"]["papers"].iloc[0]
    assert nat == 3  # Nazionale, "NUTS 2, Nazionale", National
    assert geo[geo["geo_level"] == "(unspecified)"]["papers"].iloc[0] == 1


def test_crosstab_and_year_distribution():
    ct = crosstab_by_sector(_papers(), "relevance")
    assert "(none)" in set(ct["relevance"])
    yd = year_distribution(_papers())
    assert set(yd["year"]) == {2023, 2024, 2025}


def test_run_literature_analytics_end_to_end(tmp_path):
    lit = tmp_path / "lit"
    lit.mkdir()
    _papers().to_csv(lit / "papers.csv", index=False)
    _codes().to_csv(lit / "codes_long.csv", index=False)
    report = run_literature_analytics(lit, tmp_path / "res",
                                      cooccurrence_min=1, log=False)
    assert report["papers"] == 4
    assert len(report["tables"]) >= 8
    for p in report["tables"].values():
        assert pd.read_csv(p) is not None
    assert len(report["figures"]) >= 4
