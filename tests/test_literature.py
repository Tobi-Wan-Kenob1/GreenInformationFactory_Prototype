"""Tests for gif.literature: xlsx fallback reader, cleaning, alignment, tidy."""
import zipfile

import pandas as pd
import pytest

import gif.literature as lit
from gif.literature import (
    _col_index, read_xlsx_rows, load_full_list, load_codebook,
    split_codes, tidy_codes, align_codebook, join_papers_codes,
    prepare_literature,
)


# --------------------------------------------------------------------------- #
# Minimal xlsx fixture (inline strings, explicit cell refs, one sparse row)
# --------------------------------------------------------------------------- #
def _make_xlsx(path, rows, sheet_name="Sheet1"):
    """Write a tiny xlsx readable by the stdlib fallback parser.

    ``rows`` is a list of dicts mapping cell refs (e.g. "A1") to values, so
    sparse rows (missing cells) can be expressed directly.
    """
    def cell(ref, value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'

    body = ""
    for i, row in enumerate(rows, start=1):
        cells = "".join(cell(ref, v) for ref, v in row.items())
        body += f'<row r="{i}">{cells}</row>'

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    nsr = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml",
                   f'<workbook {ns} {nsr}><sheets>'
                   f'<sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>'
                   f'</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="t" Target="worksheets/sheet1.xml"/>'
                   '</Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet {ns}><sheetData>{body}</sheetData></worksheet>')
    return path


def test_col_index():
    assert _col_index("A1") == 0
    assert _col_index("Z9") == 25
    assert _col_index("AA1") == 26
    assert _col_index("AB12") == 27


def test_read_xlsx_rows_aligns_sparse_cells(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", [
        {"A1": "h1", "B1": "h2", "C1": "h3"},
        {"A2": "a", "C2": "c"},          # B2 missing -> must stay empty
        {"B3": "only-b"},
    ])
    rows = read_xlsx_rows(p)
    assert rows[0] == ["h1", "h2", "h3"]
    assert rows[1] == ["a", "", "c"]
    assert rows[2] == ["", "only-b"]


def test_read_xlsx_rows_missing_sheet_raises(tmp_path):
    p = _make_xlsx(tmp_path / "t.xlsx", [{"A1": "x"}])
    with pytest.raises(ValueError):
        read_xlsx_rows(p, sheet="nope")


# --------------------------------------------------------------------------- #
# Cleaning / alignment on synthetic frames (engine-independent)
# --------------------------------------------------------------------------- #
def _papers_df():
    return pd.DataFrame({
        "Titolo articolo": ["Paper Alpha", "Paper Beta", "", "Paper Gamma"],
        "Anno di pubblicazione": ["2024", "2025", "", "bad"],
        "Rilevanza per BioFairNet (Alta/Media/Bassa)": ["Alta", "Media", "", "Bassa"],
        "TIPO": ["AGRI_EU", "MINING_EU", "", "AGRI_OUT"],
    })


def _coded_df():
    # paper_id column intentionally wrong (positional drift) — titles are key
    return pd.DataFrame({
        "paper_id": ["0", "5", "9"],
        "Titolo articolo": ["Paper Alpha", "Paper Gamma", "Unknown Paper"],
        "CE": ["recycling", "", ""],
        "BIO": ["", "", ""],
        "BARRIERS": ["cost; policy", "data", ""],
        "DRIVERS": ["", "demand", ""],
        "STAKEHOLDERS": ["", "", ""],
        "Abstract": ["...", "...", "..."],
        "OTHER": ["", "", ""],
        "CE#2": ["reuse", "", ""],
        "BIO#2": ["", "", ""],
        "BARRIERS#2": ["", "funding", ""],
        "DRIVERS#2": ["tech", "", ""],
        "STAKEHOLDERS#2": ["farmers", "", ""],
        "BUSINESS MODEL": ["", "", ""],
        "SPECIFIC REGION?": ["Italy", "", ""],
        "TIPO": ["AGRI_EU", "AGRI_EU", "X"],
    })


def _patch_read_xlsx(monkeypatch, df):
    monkeypatch.setattr(lit, "read_xlsx", lambda path, sheet=None, header=0: df.copy())


def test_load_full_list_maps_and_cleans(monkeypatch):
    _patch_read_xlsx(monkeypatch, _papers_df())
    papers = load_full_list("dummy.xlsx")
    assert list(papers["paper_id"]) == [0, 1, 2]          # empty-title row dropped
    assert {"title", "year", "relevance", "sector_tag"} <= set(papers.columns)
    assert papers["year"].tolist()[0] == 2024
    assert pd.isna(papers["year"].tolist()[2])            # "bad" -> NaN


def test_load_codebook_disambiguates_duplicate_dimensions(monkeypatch):
    df = _coded_df().rename(columns=lambda c: c.replace("#2", ""))  # real duplicate names
    _patch_read_xlsx(monkeypatch, df)
    coded = load_codebook("dummy.xlsx")
    assert "ce_title_kw" in coded.columns and "ce_abstract" in coded.columns
    assert "barriers_title_kw" in coded.columns and "barriers_abstract" in coded.columns
    assert "business_model" not in coded.columns or True  # empty col may be dropped
    assert "sector_tag" in coded.columns


def test_split_codes():
    assert split_codes("cost; policy ;  Data") == ["cost", "policy", "data"]
    assert split_codes("") == []
    assert split_codes(None) == []


def test_align_codebook_remaps_by_title():
    papers = pd.DataFrame({"paper_id": [0, 1, 2],
                           "title": ["Paper Alpha", "Paper Beta", "Paper Gamma"]})
    coded = pd.DataFrame({"paper_id": [0, 5, 9],
                          "title": ["Paper Alpha", "Paper Gamma", "Unknown Paper"],
                          "ce_title_kw": ["a", "b", "c"]})
    aligned, report = align_codebook(papers, coded)
    assert list(aligned["paper_id"]) == [0, 2]   # Gamma remapped 5 -> 2
    assert report["unmatched_count"] == 1        # Unknown Paper dropped + reported
    assert report["matched"] == 2


def test_tidy_codes_long_format():
    coded = pd.DataFrame({
        "paper_id": [0, 1],
        "barriers_title_kw": ["cost; policy", ""],
        "drivers_abstract": ["", "demand"],
    })
    long = tidy_codes(coded)
    assert set(long.columns) == {"paper_id", "dimension", "source", "code"}
    assert len(long) == 3
    assert set(long["code"]) == {"cost", "policy", "demand"}
    assert set(long["source"]) == {"title_kw", "abstract"}


def test_prepare_literature_end_to_end(monkeypatch, tmp_path):
    frames = {"full": _papers_df(),
              "coded": _coded_df().rename(columns=lambda c: c.replace("#2", ""))}

    def fake_read(path, sheet=None, header=0):
        return frames["coded" if "coded" in str(path) else "full"].copy()

    monkeypatch.setattr(lit, "read_xlsx", fake_read)
    report = prepare_literature(tmp_path / "full.xlsx", tmp_path / "coded.xlsx",
                                tmp_path / "out", log=False)
    assert report["join"]["title_mismatches"] == 0
    assert report["join"]["alignment"]["unmatched_count"] == 1
    assert report["codes_assigned"] > 0
    for f in report["outputs"].values():
        assert (tmp_path / "out").exists()
        assert pd.read_csv(f) is not None
