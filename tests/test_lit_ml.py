"""Tests for gif.lit_ml (small synthetic corpus; CV kept tiny for speed)."""
import matplotlib
matplotlib.use("Agg")

import numpy as np
import pandas as pd
import pytest

from gif.lit_ml import (
    build_text, derive_targets, code_target_matrix,
    make_text_models, evaluate_task, run_literature_coding, predict_codes,
)


def _corpus(n_per_class=15, seed=0):
    """Synthetic separable corpus: farm vs mine vocabulary."""
    rng = np.random.default_rng(seed)
    agri = ["crop soil harvest farm fertilizer yield wheat livestock pasture",
            "agriculture irrigation grain manure tractor field organic"]
    mine = ["ore mining excavation coal quarry mineral tailings drilling",
            "extraction pit lignite copper smelting geology seam blast"]
    rows = []
    for i in range(n_per_class):
        rows.append({"paper_id": len(rows), "title": f"agri paper {i}",
                     "abstract": agri[i % 2] + f" extra{rng.integers(9)}",
                     "sector_tag": "AGRI_EU", "relevance": "Alta" if i % 2 else "Media"})
    for i in range(n_per_class):
        rows.append({"paper_id": len(rows), "title": f"mine paper {i}",
                     "abstract": mine[i % 2] + f" extra{rng.integers(9)}",
                     "sector_tag": "MIN_OUT", "relevance": ""})
    return pd.DataFrame(rows)


def test_build_text_combines_title_and_abstract():
    papers = pd.DataFrame({"title": ["T"], "abstract": ["A"]})
    assert build_text(papers).iloc[0] == "T. A"


def test_build_text_tolerates_missing_abstract_column():
    papers = pd.DataFrame({"title": ["Only title"]})
    assert build_text(papers).iloc[0] == "Only title."


def test_derive_targets_mapping():
    papers = pd.DataFrame({
        "sector_tag": ["AGRI_EU", "MINING_EU", "MIN_OUT", "AGRI_OUT", ""],
        "relevance": ["Alta", "Molto Alta", "Media", "Bassa", "Media/Alta"],
    })
    t = derive_targets(papers)
    assert list(t["sector"][:4]) == ["agri", "mining", "mining", "agri"]
    assert pd.isna(t["sector"].iloc[4])
    assert list(t["region"][:4]) == ["eu", "eu", "out", "out"]
    assert list(t["relevance"]) == ["high", "high", "medium_low", "medium_low", "high"]


def test_code_target_matrix_min_papers_filter():
    papers = pd.DataFrame({"paper_id": range(6)})
    codes = pd.DataFrame({
        "paper_id": [0, 1, 2, 3, 0, 1],
        "dimension": ["barriers"] * 4 + ["drivers"] * 2,
        "source": ["title_kw"] * 6,
        "code": ["cost"] * 4 + ["demand"] * 2,
    })
    mat = code_target_matrix(codes, papers, min_papers=3)
    assert list(mat.columns) == ["barriers:cost"]
    assert mat["barriers:cost"].sum() == 4
    assert set(mat["barriers:cost"].unique()) <= {0, 1}


def test_evaluate_task_ranks_and_reduces_folds():
    papers = _corpus()
    texts = build_text(papers)
    y = derive_targets(papers)["sector"]
    models = {"logreg": make_text_models()["logreg"]}
    res = evaluate_task(texts, y, task="sector", models=models, cv=5)
    assert res.iloc[0]["f1_macro"] > 0.9         # separable vocabulary
    assert res.iloc[0]["cv_folds"] == 5

    # relevance is labeled on the agri half only (8 Alta / 7 Media at n=15)
    y2 = derive_targets(papers)["relevance"]
    res2 = evaluate_task(texts, y2, task="relevance", models=models, cv=10)
    assert res2.iloc[0]["cv_folds"] <= 8          # clamped to rarest class


def test_evaluate_task_raises_on_single_class():
    papers = _corpus()
    texts = build_text(papers)
    y = pd.Series(["only"] * len(papers))
    with pytest.raises(ValueError):
        evaluate_task(texts, y, task="broken")


def test_run_literature_coding_end_to_end(tmp_path):
    papers = _corpus()
    codes = pd.DataFrame({
        "paper_id": list(range(10)),
        "dimension": ["barriers"] * 10,
        "source": ["title_kw"] * 10,
        "code": ["cost"] * 10,
    })
    lit = tmp_path / "lit"
    lit.mkdir()
    papers.to_csv(lit / "papers.csv", index=False)
    codes.to_csv(lit / "codes_long.csv", index=False)

    result = run_literature_coding(lit, tmp_path / "res", tmp_path / "models",
                                   min_papers=5, cv=3, log=False)
    assert {"sector", "region", "relevance", "code:barriers:cost"} <= set(result.models)
    assert (tmp_path / "models" / "literature_coder.pkl").exists()
    assert (tmp_path / "res" / "lit_coding_model_comparison.csv").exists()
    # best table has one row per task, sorted by f1
    assert result.best["task"].is_unique

    # bundle can predict on new papers
    new = pd.DataFrame({"title": ["ore coal mining pit"], "abstract": ["quarry mineral"]})
    preds = predict_codes(tmp_path / "models" / "literature_coder.pkl", new)
    assert preds["pred_sector"].iloc[0] == "mining"
