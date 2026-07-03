"""Ingestion of the BioFairNet WP1/D1.2 literature datasets (June 2026).

Turns the two CC-BY-4.0 Zenodo uploads into tidy, validated CSVs the rest of
the pipeline (and future ML-assisted coding) can consume:

- **Full list**  (10.5281/zenodo.20743706, ``Literature Analysis _ FULL LIST.xlsx``):
  ~1000 papers on agricultural/mining hotspots (EU + Canada/Kenya extension)
  with Italian column headers → ``papers.csv`` with English snake_case columns.
- **Codebook**   (10.5281/zenodo.20744025, ``Literature Analysis _ Coded File.xlsx``):
  the same corpus manually coded (CE / BIO / BARRIERS / DRIVERS / STAKEHOLDERS,
  business model, region, sector tag) → ``codes_long.csv`` (tidy long format)
  and ``papers_coded.csv`` (papers joined with wide codes).

Attribution: datasets by Guerreschi, Lomuscio & Albanese (CC-BY-4.0); keep the
`source DOIs <https://doi.org/10.5281/zenodo.20743706>`_ in derived releases.

xlsx reading uses :func:`pandas.read_excel` when ``openpyxl`` is installed and
falls back to a small stdlib parser otherwise, so the module works in minimal
environments.
"""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from helper.utils import find_repo_root, save_run_log

#: DOIs of the June-2026 D1.2 uploads (defaults for the CLI fetch command).
D12_FULL_LIST_DOI = "10.5281/zenodo.20743706"
D12_CODEBOOK_DOI = "10.5281/zenodo.20744025"

# --------------------------------------------------------------------------- #
# Minimal stdlib xlsx reader (fallback when openpyxl is unavailable)
# --------------------------------------------------------------------------- #
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _col_index(ref: str) -> int:
    """Excel column letters -> 0-based index (``"A"``→0, ``"AB"``→27)."""
    letters = re.match(r"[A-Z]+", ref.upper())
    if not letters:
        raise ValueError(f"Bad cell reference: {ref!r}")
    idx = 0
    for ch in letters.group(0):
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def read_xlsx_rows(path: Path | str, sheet: Optional[str] = None) -> List[List[str]]:
    """Read one worksheet as a list of rows (list of strings), stdlib only.

    Honors cell references so sparse rows (Excel omits empty cells) stay
    correctly aligned to their columns. Values are returned as strings; empty
    cells become ``""``.
    """
    z = zipfile.ZipFile(path)
    shared: List[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % _NS["m"])))

    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.get("Id"): r.get("Target") for r in rels}
    sheets = wb.find("m:sheets", _NS)
    chosen = None
    for sh in sheets:
        if sheet is None or sh.get("name") == sheet:
            chosen = sh
            break
    if chosen is None:
        names = [sh.get("name") for sh in sheets]
        raise ValueError(f"Sheet {sheet!r} not found in {path}. Available: {names}")

    target = relmap[chosen.get("{%s}id" % _NS["r"])]
    if not target.startswith("xl/"):
        target = "xl/" + target
    root = ET.fromstring(z.read(target))

    def cellval(c) -> str:
        v = c.find("m:v", _NS)
        if v is None:
            ist = c.find("m:is", _NS)
            if ist is not None:
                return "".join(t.text or "" for t in ist.iter("{%s}t" % _NS["m"]))
            return ""
        if c.get("t") == "s":
            return shared[int(v.text)]
        return v.text or ""

    rows: List[List[str]] = []
    sheet_data = root.find("m:sheetData", _NS)
    for row in (sheet_data.findall("m:row", _NS) if sheet_data is not None else []):
        cells: Dict[int, str] = {}
        for pos, c in enumerate(row.findall("m:c", _NS)):
            ref = c.get("r")
            cells[_col_index(ref) if ref else pos] = cellval(c)
        width = max(cells) + 1 if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def read_xlsx(path: Path | str, sheet: Optional[str] = None, header: int = 0) -> pd.DataFrame:
    """Read an xlsx sheet into a DataFrame (openpyxl if present, else stdlib)."""
    try:
        import openpyxl  # noqa: F401
        return pd.read_excel(path, sheet_name=sheet or 0, header=header, dtype=str,
                             engine="openpyxl").fillna("")
    except ImportError:
        rows = read_xlsx_rows(path, sheet)
        if len(rows) <= header:
            return pd.DataFrame()
        cols = rows[header]
        width = max([len(cols)] + [len(r) for r in rows[header + 1:]] or [0])
        cols = list(cols) + [""] * (width - len(cols))
        data = [list(r) + [""] * (width - len(r)) for r in rows[header + 1:]]
        return pd.DataFrame(data, columns=cols)


# --------------------------------------------------------------------------- #
# Full list (papers)
# --------------------------------------------------------------------------- #
#: Italian headers of the full list → English snake_case names.
FULL_LIST_COLUMNS: Dict[str, str] = {
    "Titolo articolo": "title",
    "Anno di pubblicazione": "year",
    "Autori": "authors",
    "Journal": "journal",
    "Tipo di pubblicazione (su rivista, proceedings, etc)": "publication_type",
    "DOI": "doi",
    "Abstract": "abstract",
    "Keyword 1": "keyword_1",
    "Keyword 2": "keyword_2",
    "Keyword 3": "keyword_3",
    "Keyword 4": "keyword_4",
    "Keyword 5": "keyword_5",
    "Paese/i UE menzionati": "countries_mentioned",
    "Livello geografico (NUTS2/NUTS3/Nazionale)": "geographic_level",
    "Tipo di attività": "activity_type",
    "Tipo di emissioni (CO2/CH4/N2O/GHG totale)": "emission_type",
    "Metodo usato (es. LCA, GIS, modellizzazione)": "method",
    "Tipo di analisi effettuata (economico, ambientale, sociale, mix)": "analysis_type",
    "Hotspot identificati (descrizione)": "hotspots",
    "Dati utilizzati (fonte e granularità)": "data_sources",
    "Rilevanza per BioFairNet (Alta/Media/Bassa)": "relevance",
    "Note aggiuntive": "notes",
    "TIPO": "sector_tag",
}


def _slug(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip().lower()).strip("_")
    return s or "unnamed"


def load_full_list(path: Path | str, sheet: Optional[str] = None) -> pd.DataFrame:
    """Load the full literature list with English snake_case column names.

    Adds a positional ``paper_id`` (0-based) used to join with the codebook.
    Unknown/extra columns are kept with slugified names; fully empty columns
    and fully empty rows are dropped.
    """
    df = read_xlsx(path, sheet=sheet)
    df.columns = [str(c).strip() for c in df.columns]
    rename = {c: FULL_LIST_COLUMNS.get(c, _slug(c)) for c in df.columns}
    df = df.rename(columns=rename)
    # drop unnamed/empty columns
    keep = [c for c in df.columns if c not in ("", "unnamed") and not df[c].astype(str).str.strip().eq("").all()]
    df = df[keep]
    # drop rows without a title
    if "title" in df.columns:
        df = df[df["title"].astype(str).str.strip() != ""]
    df = df.reset_index(drop=True)
    df.insert(0, "paper_id", range(len(df)))
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    return df


# --------------------------------------------------------------------------- #
# Codebook (manual codes)
# --------------------------------------------------------------------------- #
#: Code dimensions as they appear (twice) in the coded sheet.
CODE_DIMENSIONS = ["CE", "BIO", "BARRIERS", "DRIVERS", "STAKEHOLDERS"]

#: Column layout of the ``abstract_only`` sheet. The five code dimensions
#: appear twice: the first block (before the Abstract column) holds codes
#: assigned from title+keywords, the second block codes assigned from the
#: abstract text (sheet/codebook naming in the source file).
CODEBOOK_RENAME_FIRST = {d: f"{d.lower()}_title_kw" for d in CODE_DIMENSIONS}
CODEBOOK_RENAME_SECOND = {d: f"{d.lower()}_abstract" for d in CODE_DIMENSIONS}


def load_codebook(path: Path | str, sheet: str = "abstract_only") -> pd.DataFrame:
    """Load the coded sheet, disambiguating the duplicated code columns.

    Returns snake_case columns: ``paper_id, title, ce_title_kw, …,
    stakeholders_title_kw, abstract, other, ce_abstract, …,
    stakeholders_abstract, business_model, specific_region, sector_tag``.
    """
    df = read_xlsx(path, sheet=sheet)
    seen: Dict[str, int] = {}
    cols: List[str] = []
    for c in df.columns:
        name = str(c).strip()
        n = seen.get(name, 0)
        seen[name] = n + 1
        if name in CODE_DIMENSIONS:
            cols.append(CODEBOOK_RENAME_FIRST[name] if n == 0 else CODEBOOK_RENAME_SECOND[name])
        elif name == "Titolo articolo":
            cols.append("title")
        elif name == "BUSINESS MODEL":
            cols.append("business_model")
        elif name.rstrip("?") == "SPECIFIC REGION":
            cols.append("specific_region")
        elif name == "TIPO":
            cols.append("sector_tag")
        else:
            cols.append(_slug(name) if name else "unnamed")
    df.columns = cols
    keep = [c for c in df.columns if c != "unnamed" and not df[c].astype(str).str.strip().eq("").all()]
    df = df[keep]
    if "paper_id" in df.columns:
        df["paper_id"] = pd.to_numeric(df["paper_id"], errors="coerce").astype("Int64")
        df = df.dropna(subset=["paper_id"]).reset_index(drop=True)
    return df


def split_codes(value: str, sep: str = ";") -> List[str]:
    """Split a multi-value code cell into clean lowercase codes."""
    if value is None:
        return []
    return [p.strip().lower() for p in str(value).split(sep) if p.strip()]


def tidy_codes(coded: pd.DataFrame) -> pd.DataFrame:
    """Melt the wide coded frame into tidy long format.

    Columns: ``paper_id, dimension, source, code`` — one row per assigned
    code, with ``source`` ∈ {``title_kw``, ``abstract``} and ``dimension`` the
    lowercase code dimension (``ce``, ``bio``, ``barriers``, …).
    """
    records: List[Tuple[int, str, str, str]] = []
    for d in CODE_DIMENSIONS:
        for source, col in ((("title_kw"), f"{d.lower()}_title_kw"),
                            (("abstract"), f"{d.lower()}_abstract")):
            if col not in coded.columns:
                continue
            for pid, cell in zip(coded["paper_id"], coded[col]):
                for code in split_codes(cell):
                    records.append((int(pid), d.lower(), source, code))
    return pd.DataFrame(records, columns=["paper_id", "dimension", "source", "code"])


def _norm_title(s: str) -> str:
    return re.sub(r"\W+", " ", str(s)).strip().lower()


def align_codebook(papers: pd.DataFrame, coded: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Remap the codebook onto the canonical ``paper_id`` via normalized title.

    The codebook's own ``paper_id`` column tracks raw spreadsheet positions and
    drifts after blank rows, so it cannot be trusted for joining. Titles are
    the reliable key (366/366 in the June 2026 uploads). Returns
    ``(coded_aligned, report)``; unmatched coded rows are dropped and reported,
    never silently misassigned.
    """
    lookup: Dict[str, int] = {}
    duplicates: List[str] = []
    for pid, title in zip(papers["paper_id"], papers["title"]):
        key = _norm_title(title)
        if key in lookup:
            duplicates.append(title)
            continue  # keep first occurrence
        lookup[key] = int(pid)

    out = coded.copy()
    out["_key"] = out["title"].map(_norm_title) if "title" in out.columns else ""
    matched = out["_key"].isin(lookup.keys()) & (out["_key"] != "")
    unmatched = out.loc[~matched, "title"].astype(str).str.strip()
    unmatched = [t for t in unmatched if t]
    out = out[matched].copy()
    out["paper_id"] = out["_key"].map(lookup).astype(int)
    out = out.drop(columns=["_key"]).reset_index(drop=True)
    # if several coded rows map to one paper, keep the first and report
    dup_coded = int(out["paper_id"].duplicated().sum())
    out = out.drop_duplicates(subset=["paper_id"], keep="first").reset_index(drop=True)

    report = {
        "coded_rows": int(len(coded)),
        "matched": int(len(out)),
        "unmatched_titles": unmatched[:10],
        "unmatched_count": len(unmatched),
        "duplicate_paper_titles": duplicates[:10],
        "duplicate_coded_rows_dropped": dup_coded,
    }
    return out, report


def join_papers_codes(papers: pd.DataFrame, coded: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Join papers with wide codes on ``paper_id`` and validate title agreement.

    ``coded`` should already be aligned via :func:`align_codebook`. Returns
    ``(joined, report)``; the report counts residual title mismatches so any
    misalignment is surfaced, not hidden.
    """
    code_cols = [c for c in coded.columns if c not in ("title",)]
    joined = papers.merge(coded[code_cols], on="paper_id", how="left",
                          suffixes=("", "_coded"))
    both = papers.merge(coded[["paper_id", "title"]], on="paper_id", how="inner",
                        suffixes=("", "_coded"))
    mismatches = both[
        both["title"].map(_norm_title) != both["title_coded"].map(_norm_title)
    ]
    report = {
        "papers": int(len(papers)),
        "coded": int(len(coded)),
        "joined": int(len(joined)),
        "title_mismatches": int(len(mismatches)),
        "mismatch_examples": mismatches["title"].head(5).tolist(),
    }
    return joined, report


# --------------------------------------------------------------------------- #
# End-to-end preparation
# --------------------------------------------------------------------------- #
def prepare_literature(
    full_list_path: Path | str,
    codebook_path: Path | str,
    out_dir: Path | str,
    *,
    codebook_sheet: str = "abstract_only",
    log: bool = True,
) -> Dict[str, object]:
    """Ingest both D1.2 xlsx files and write tidy CSVs to ``out_dir``.

    Writes ``papers.csv``, ``codes_long.csv`` and ``papers_coded.csv`` and
    returns a report dict (row counts, join validation, output paths).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    papers = load_full_list(full_list_path)
    coded_raw = load_codebook(codebook_path, sheet=codebook_sheet)
    coded, align_report = align_codebook(papers, coded_raw)
    codes_long = tidy_codes(coded)
    joined, join_report = join_papers_codes(papers, coded)
    join_report["alignment"] = align_report

    files = {
        "papers": out / "papers.csv",
        "codes_long": out / "codes_long.csv",
        "papers_coded": out / "papers_coded.csv",
    }
    papers.to_csv(files["papers"], index=False)
    codes_long.to_csv(files["codes_long"], index=False)
    joined.to_csv(files["papers_coded"], index=False)

    report: Dict[str, object] = {
        "sources": {
            "full_list": {"path": str(full_list_path), "doi": D12_FULL_LIST_DOI},
            "codebook": {"path": str(codebook_path), "doi": D12_CODEBOOK_DOI,
                         "sheet": codebook_sheet},
        },
        "join": join_report,
        "codes_assigned": int(len(codes_long)),
        "code_dimensions": sorted(codes_long["dimension"].unique().tolist()) if len(codes_long) else [],
        "outputs": {k: str(v) for k, v in files.items()},
        "license_note": "Derived from CC-BY-4.0 datasets by Guerreschi, Lomuscio & Albanese; attribute in downstream releases.",
    }
    if log:
        try:
            save_run_log("literature_prepare", report, repo_root=find_repo_root())
        except Exception as exc:  # best-effort outside a repo
            print(f"⚠️ Could not write run log: {exc}")
    return report
