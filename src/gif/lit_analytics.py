"""Descriptive hotspot analytics for the WP1/D1.2 literature corpus (Phase 2).

Pure aggregation functions over the tidy CSVs produced by
:mod:`gif.literature` (``papers.csv`` + ``codes_long.csv``), plus an
orchestrator that writes the standard tables/figures to
``data/results/literature/``.

All counts are **papers** (a code counted once per paper), not raw code
occurrences, so the same code assigned from both title/keywords and abstract
does not double-count.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from helper.utils import find_repo_root, save_run_log

#: Light normalization for the mixed Italian/English geo-level values.
_GEO_LEVEL_MAP = {
    "nazionale": "National",
    "national": "National",
    "nuts 2": "NUTS 2",
    "nuts2": "NUTS 2",
    "nuts 3": "NUTS 3",
    "nuts3": "NUTS 3",
    "regionale": "Regional",
    "regional": "Regional",
}


def load_literature(lit_dir: Path | str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Load ``papers.csv`` and ``codes_long.csv`` from a literature dir."""
    lit_dir = Path(lit_dir)
    papers = pd.read_csv(lit_dir / "papers.csv")
    codes = pd.read_csv(lit_dir / "codes_long.csv")
    return papers, codes


def code_frequencies(
    codes: pd.DataFrame,
    dimension: Optional[str] = None,
    top: Optional[int] = None,
) -> pd.DataFrame:
    """Papers per code (deduplicated per paper), optionally one dimension.

    Returns columns ``dimension, code, papers`` sorted by count descending.
    """
    df = codes if dimension is None else codes[codes["dimension"] == dimension]
    per_paper = df.drop_duplicates(["paper_id", "dimension", "code"])
    out = (per_paper.groupby(["dimension", "code"]).size()
           .reset_index(name="papers")
           .sort_values(["dimension", "papers"], ascending=[True, False])
           .reset_index(drop=True))
    if top is not None:
        out = (out.groupby("dimension", group_keys=False)
               .apply(lambda g: g.head(top)).reset_index(drop=True))
    return out


def code_frequencies_by_sector(
    codes: pd.DataFrame,
    papers: pd.DataFrame,
    dimension: str,
    top: int = 15,
) -> pd.DataFrame:
    """Pivot of papers-per-code × sector for one dimension (top codes only)."""
    df = codes[codes["dimension"] == dimension].drop_duplicates(["paper_id", "code"])
    df = df.merge(papers[["paper_id", "sector_tag"]], on="paper_id", how="left")
    counts = df.groupby(["code", "sector_tag"]).size().unstack(fill_value=0)
    counts["total"] = counts.sum(axis=1)
    counts = counts.sort_values("total", ascending=False).head(top)
    return counts.reset_index()


def code_cooccurrence(
    codes: pd.DataFrame,
    dim_a: str,
    dim_b: str,
    min_count: int = 5,
) -> pd.DataFrame:
    """Cross-dimension co-occurrence: papers where code A and code B co-appear.

    Rows are ``dim_a`` codes, columns ``dim_b`` codes; only codes appearing in
    at least ``min_count`` papers are kept so the matrix stays readable.
    """
    a = codes[codes["dimension"] == dim_a].drop_duplicates(["paper_id", "code"])
    b = codes[codes["dimension"] == dim_b].drop_duplicates(["paper_id", "code"])
    keep_a = a["code"].value_counts()
    keep_b = b["code"].value_counts()
    a = a[a["code"].isin(keep_a[keep_a >= min_count].index)]
    b = b[b["code"].isin(keep_b[keep_b >= min_count].index)]
    pairs = a.merge(b, on="paper_id", suffixes=("_a", "_b"))
    if pairs.empty:
        return pd.DataFrame()
    return (pairs.groupby(["code_a", "code_b"]).size()
            .unstack(fill_value=0))


def explode_countries(papers: pd.DataFrame) -> pd.DataFrame:
    """Papers per mentioned country (comma-split, stripped, as written).

    Values are kept as they appear in the source (mixed IT/EN spellings such
    as ``Cipro`` are not translated); aggregate labels like ``EU-27`` count
    like any other value.
    """
    col = papers["countries_mentioned"].fillna("")
    rows: List[Tuple[int, str]] = []
    for pid, cell in zip(papers["paper_id"], col):
        for c in str(cell).split(","):
            c = c.strip()
            if c:
                rows.append((pid, c))
    long = pd.DataFrame(rows, columns=["paper_id", "country"]).drop_duplicates()
    return (long.groupby("country").size().reset_index(name="papers")
            .sort_values("papers", ascending=False).reset_index(drop=True))


def normalize_geo_level(papers: pd.DataFrame) -> pd.DataFrame:
    """Papers per geographic level, normalized across IT/EN spellings.

    Multi-valued cells ("NUTS 2, Nazionale") count once per level mentioned.
    Empty cells are reported as ``(unspecified)``.
    """
    rows: List[Tuple[int, str]] = []
    for pid, cell in zip(papers["paper_id"], papers["geographic_level"].fillna("")):
        parts = [p.strip() for p in str(cell).split(",") if p.strip()]
        if not parts:
            rows.append((pid, "(unspecified)"))
            continue
        for p in parts:
            rows.append((pid, _GEO_LEVEL_MAP.get(p.lower(), p)))
    long = pd.DataFrame(rows, columns=["paper_id", "geo_level"]).drop_duplicates()
    return (long.groupby("geo_level").size().reset_index(name="papers")
            .sort_values("papers", ascending=False).reset_index(drop=True))


def crosstab_by_sector(papers: pd.DataFrame, column: str) -> pd.DataFrame:
    """Crosstab of a categorical paper column × sector_tag (blank→(none))."""
    vals = papers[column].fillna("").astype(str).str.strip().replace("", "(none)")
    return pd.crosstab(vals, papers["sector_tag"]).reset_index()


def year_distribution(papers: pd.DataFrame) -> pd.DataFrame:
    """Papers per publication year × sector."""
    df = papers.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    return pd.crosstab(df["year"], df["sector_tag"]).reset_index()


# --------------------------------------------------------------------------- #
# Orchestration + plots
# --------------------------------------------------------------------------- #
def run_literature_analytics(
    lit_dir: Path | str,
    results_dir: Path | str,
    *,
    top: int = 15,
    cooccurrence_min: int = 8,
    make_plots: bool = True,
    log: bool = True,
) -> Dict[str, object]:
    """Compute the standard analytics tables/figures and write them to disk.

    Tables are prefixed ``lit_`` under ``results_dir``; the report lists all
    written paths plus headline numbers.
    """
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    papers, codes = load_literature(lit_dir)

    tables: Dict[str, pd.DataFrame] = {
        "lit_top_codes": code_frequencies(codes, top=top),
        "lit_country_counts": explode_countries(papers),
        "lit_geo_levels": normalize_geo_level(papers),
        "lit_relevance_by_sector": crosstab_by_sector(papers, "relevance"),
        "lit_year_by_sector": year_distribution(papers),
    }
    for dim in ("barriers", "drivers", "stakeholders"):
        tables[f"lit_{dim}_by_sector"] = code_frequencies_by_sector(codes, papers, dim, top=top)
    cooc = code_cooccurrence(codes, "barriers", "drivers", min_count=cooccurrence_min)
    if not cooc.empty:
        tables["lit_cooccurrence_barriers_drivers"] = cooc.reset_index()

    written: Dict[str, str] = {}
    for name, df in tables.items():
        p = results_dir / f"{name}.csv"
        df.to_csv(p, index=False)
        written[name] = str(p)

    figures: List[str] = []
    if make_plots:
        try:
            figures = _analytics_plots(papers, codes, cooc, results_dir, top=top)
        except Exception as exc:  # plotting is best-effort, never fatal
            print(f"⚠️ Skipped analytics plots: {exc}")

    report: Dict[str, object] = {
        "papers": int(len(papers)),
        "codes": int(len(codes)),
        "sectors": papers["sector_tag"].value_counts().to_dict(),
        "tables": written,
        "figures": figures,
    }
    if log:
        try:
            save_run_log("literature_analytics", report, repo_root=find_repo_root())
        except Exception as exc:
            print(f"⚠️ Could not write run log: {exc}")
    return report


def _analytics_plots(papers, codes, cooc, results_dir: Path, top: int) -> List[str]:
    from .plots import _plt
    plt = _plt()
    saved: List[str] = []

    def _save(fig, name: str):
        p = results_dir / name
        fig.savefig(p, dpi=200, bbox_inches="tight")
        plt.close(fig)
        saved.append(str(p))

    # Top codes per dimension (horizontal bars, most frequent on top)
    for dim in ("barriers", "drivers", "stakeholders"):
        freq = code_frequencies(codes, dimension=dim, top=top)
        if freq.empty:
            continue
        freq = freq.iloc[::-1]
        fig = plt.figure(figsize=(7, max(3, 0.35 * len(freq))))
        plt.barh(freq["code"], freq["papers"])
        plt.title(f"Top {dim} codes (papers)")
        plt.xlabel("papers")
        _save(fig, f"lit_top_{dim}.png")

    # Countries (top 15)
    cc = explode_countries(papers).head(15).iloc[::-1]
    fig = plt.figure(figsize=(7, 5.5))
    plt.barh(cc["country"], cc["papers"])
    plt.title("Most mentioned countries (papers)")
    plt.xlabel("papers")
    _save(fig, "lit_country_counts.png")

    # Publication years, stacked by sector
    yd = year_distribution(papers).set_index("year")
    fig = plt.figure(figsize=(8, 4.5))
    bottom = None
    for sector in yd.columns:
        plt.bar(yd.index, yd[sector], bottom=bottom, label=sector)
        bottom = yd[sector] if bottom is None else bottom + yd[sector]
    plt.title("Publications per year by sector")
    plt.xlabel("year"); plt.ylabel("papers")
    plt.legend()
    _save(fig, "lit_year_by_sector.png")

    # Barriers × drivers co-occurrence heatmap
    if cooc is not None and not cooc.empty:
        fig = plt.figure(figsize=(1 + 0.5 * len(cooc.columns), 1 + 0.4 * len(cooc.index)))
        plt.imshow(cooc.to_numpy(), aspect="auto")
        plt.xticks(range(len(cooc.columns)), cooc.columns, rotation=45, ha="right")
        plt.yticks(range(len(cooc.index)), cooc.index)
        plt.title("Co-occurrence: barriers × drivers (papers)")
        plt.colorbar()
        _save(fig, "lit_cooccurrence_barriers_drivers.png")

    return saved
