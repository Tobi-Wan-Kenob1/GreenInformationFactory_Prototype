"""ML-assisted literature coding (Phase 3).

Uses the manually coded WP1/D1.2 corpus as ground truth to train text
classifiers (TF-IDF on title+abstract) that can pre-code future literature
batches. Tasks are derived to respect the actual label support in the data:

- ``sector``    : AGRI vs MINING (from the ``sector_tag`` prefix; 258 vs 108)
- ``region``    : EU vs OUT (from the ``sector_tag`` suffix; 294 vs 72)
- ``relevance`` : high vs medium_low, **labeled subset only** (~101 papers;
                  Alta/Molto Alta → high, Media/Bassa → medium_low)
- ``code:<dim>:<code>`` : one binary task per manual code assigned to at
                  least ``min_papers`` papers (13 codes at the default 15)

Every task is evaluated with stratified k-fold cross-validation (macro-F1 +
accuracy) across a small model zoo; the best model per task is refit on all
available data and stored in a single bundle for reuse.

Small-corpus caveat: with 366 papers (and ~101 relevance labels) these are
screening aids, not replacements for manual coding — treat predictions as
triage suggestions.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate, cross_val_predict
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from helper.utils import find_repo_root, save_run_log

#: Relevance labels collapsed to a binary target (lowercased comparison).
_RELEVANCE_HIGH = {"alta", "molto alta", "media/alta"}
_RELEVANCE_LOW = {"media", "bassa"}


def build_text(papers: pd.DataFrame) -> pd.Series:
    """Model input text: title + abstract (either may be missing)."""
    title = papers["title"].fillna("").astype(str)
    abstract = papers.get("abstract", pd.Series("", index=papers.index)).fillna("").astype(str)
    return (title + ". " + abstract).str.strip()


def derive_targets(papers: pd.DataFrame) -> Dict[str, pd.Series]:
    """Derive the single-label classification targets from ``papers``.

    Returns name → label Series (indexed like ``papers``, NaN = unlabeled;
    rows with NaN are excluded from that task).
    """
    tag = papers["sector_tag"].fillna("").astype(str).str.upper().str.strip()
    sector = pd.Series(np.nan, index=papers.index, dtype=object)
    sector[tag.str.startswith("AGRI")] = "agri"
    sector[tag.str.startswith(("MINING", "MIN"))] = "mining"

    region = pd.Series(np.nan, index=papers.index, dtype=object)
    region[tag.str.endswith("_EU")] = "eu"
    region[tag.str.endswith("_OUT")] = "out"

    rel_raw = papers["relevance"].fillna("").astype(str).str.strip().str.lower()
    relevance = pd.Series(np.nan, index=papers.index, dtype=object)
    relevance[rel_raw.isin(_RELEVANCE_HIGH)] = "high"
    relevance[rel_raw.isin(_RELEVANCE_LOW)] = "medium_low"

    return {"sector": sector, "region": region, "relevance": relevance}


def code_target_matrix(
    codes: pd.DataFrame,
    papers: pd.DataFrame,
    dimensions: Tuple[str, ...] = ("barriers", "drivers", "stakeholders"),
    min_papers: int = 15,
) -> pd.DataFrame:
    """Binary per-code target matrix aligned to ``papers`` (0/1 per column).

    Only codes assigned to at least ``min_papers`` papers become columns,
    named ``<dimension>:<code>``.
    """
    per_paper = codes[codes["dimension"].isin(dimensions)].drop_duplicates(
        ["paper_id", "dimension", "code"]
    )
    counts = per_paper.groupby(["dimension", "code"]).size()
    keep = counts[counts >= min_papers].index
    mat = pd.DataFrame(0, index=papers["paper_id"], columns=[f"{d}:{c}" for d, c in keep])
    for (d, c) in keep:
        pids = per_paper[(per_paper["dimension"] == d) & (per_paper["code"] == c)]["paper_id"]
        mat.loc[mat.index.isin(pids), f"{d}:{c}"] = 1
    mat.index.name = "paper_id"
    return mat


def make_text_models(random_seed: int = 42) -> Dict[str, Pipeline]:
    """TF-IDF + classifier pipelines evaluated for every task."""
    def tfidf() -> TfidfVectorizer:
        return TfidfVectorizer(
            lowercase=True, stop_words="english", sublinear_tf=True,
            ngram_range=(1, 2), min_df=2, max_features=20000,
        )

    return {
        "logreg": Pipeline([
            ("tfidf", tfidf()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced",
                                       random_state=random_seed)),
        ]),
        "linear_svc": Pipeline([
            ("tfidf", tfidf()),
            ("clf", LinearSVC(class_weight="balanced", random_state=random_seed)),
        ]),
        "nb": Pipeline([("tfidf", tfidf()), ("clf", MultinomialNB())]),
        "rf": Pipeline([
            ("tfidf", tfidf()),
            ("clf", RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                           random_state=random_seed)),
        ]),
    }


def evaluate_task(
    texts: pd.Series,
    y: pd.Series,
    *,
    task: str,
    models: Optional[Dict[str, Pipeline]] = None,
    cv: int = 5,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Cross-validate every model on one task; rows sorted best-first.

    Unlabeled rows (NaN in ``y``) are dropped. ``cv`` is reduced automatically
    when the rarest class has fewer members than the fold count.
    """
    mask = y.notna()
    X = texts[mask].to_numpy()
    yy = y[mask].astype(str).to_numpy()
    class_counts = pd.Series(yy).value_counts()
    if len(class_counts) < 2:
        raise ValueError(f"Task {task!r} has fewer than 2 classes after dropping unlabeled rows.")
    folds = int(min(cv, class_counts.min()))
    if folds < 2:
        raise ValueError(f"Task {task!r}: rarest class has {class_counts.min()} sample(s); cannot CV.")

    models = models or make_text_models(random_seed)
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_seed)
    rows: List[Dict[str, object]] = []
    for name, pipe in models.items():
        scores = cross_validate(pipe, X, yy, cv=skf,
                                scoring=["f1_macro", "accuracy"], n_jobs=1)
        rows.append({
            "task": task,
            "model": name,
            "f1_macro": float(np.mean(scores["test_f1_macro"])),
            "f1_macro_std": float(np.std(scores["test_f1_macro"])),
            "accuracy": float(np.mean(scores["test_accuracy"])),
            "n": int(len(yy)),
            "cv_folds": folds,
            "class_counts": class_counts.to_dict(),
        })
    return (pd.DataFrame(rows)
            .sort_values(["f1_macro", "accuracy"], ascending=False)
            .reset_index(drop=True))


@dataclass
class CodingResult:
    """Outcome of :func:`run_literature_coding`."""

    results: pd.DataFrame                       # all task × model CV rows
    best: pd.DataFrame                          # best row per task
    models: Dict[str, Pipeline] = field(default_factory=dict)  # refit best per task


def run_literature_coding(
    lit_dir: Path | str,
    results_dir: Path | str,
    models_dir: Path | str,
    *,
    min_papers: int = 15,
    cv: int = 5,
    random_seed: int = 42,
    make_plots: bool = True,
    log: bool = True,
) -> CodingResult:
    """Train/evaluate all coding tasks and persist comparison, bundle, plots.

    Writes ``lit_coding_model_comparison.csv`` (all rows) and
    ``lit_coding_best_models.csv`` (best per task) to ``results_dir`` and a
    ``literature_coder.pkl`` bundle (best pipeline per task, refit on all
    labeled data) to ``models_dir``.
    """
    lit_dir, results_dir, models_dir = Path(lit_dir), Path(results_dir), Path(models_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    papers = pd.read_csv(lit_dir / "papers.csv")
    codes = pd.read_csv(lit_dir / "codes_long.csv")
    texts = build_text(papers)

    tasks: Dict[str, pd.Series] = derive_targets(papers)
    code_mat = code_target_matrix(codes, papers, min_papers=min_papers)
    for col in code_mat.columns:
        y = pd.Series(code_mat[col].to_numpy(), index=papers.index).map({0: "no", 1: "yes"})
        tasks[f"code:{col}"] = y

    all_rows: List[pd.DataFrame] = []
    fitted: Dict[str, Pipeline] = {}
    skipped: List[str] = []
    for task, y in tasks.items():
        try:
            res = evaluate_task(texts, y, task=task, cv=cv, random_seed=random_seed)
        except ValueError as exc:
            skipped.append(f"{task}: {exc}")
            continue
        all_rows.append(res)
        best_name = str(res.iloc[0]["model"])
        pipe = make_text_models(random_seed)[best_name]
        mask = y.notna()
        pipe.fit(texts[mask].to_numpy(), y[mask].astype(str).to_numpy())
        fitted[task] = pipe

    results = pd.concat(all_rows, ignore_index=True)
    best = (results.sort_values(["f1_macro", "accuracy"], ascending=False)
            .groupby("task", as_index=False).first()
            .sort_values("f1_macro", ascending=False).reset_index(drop=True))

    cmp_path = results_dir / "lit_coding_model_comparison.csv"
    best_path = results_dir / "lit_coding_best_models.csv"
    results.to_csv(cmp_path, index=False)
    best.to_csv(best_path, index=False)

    bundle_path = models_dir / "literature_coder.pkl"
    with open(bundle_path, "wb") as f:
        pickle.dump({
            "models": fitted,
            "best": best,
            "min_papers": min_papers,
            "random_seed": random_seed,
            "source_dois": ["10.5281/zenodo.20743706", "10.5281/zenodo.20744025"],
            "note": "TF-IDF text coders trained on the manually coded D1.2 corpus; "
                    "screening aid, not a replacement for manual coding.",
        }, f)

    figures: List[str] = []
    if make_plots:
        try:
            figures = _coding_plots(best, texts, tasks, results_dir,
                                    cv=cv, random_seed=random_seed)
        except Exception as exc:
            print(f"⚠️ Skipped coding plots: {exc}")

    if log:
        try:
            save_run_log("literature_coding", {
                "tasks": int(len(fitted)),
                "skipped": skipped,
                "best_by_task": best[["task", "model", "f1_macro", "n"]]
                    .to_dict(orient="records"),
                "outputs": {"comparison": str(cmp_path), "best": str(best_path),
                            "bundle": str(bundle_path)},
                "figures": figures,
            }, repo_root=find_repo_root())
        except Exception as exc:
            print(f"⚠️ Could not write run log: {exc}")

    return CodingResult(results=results, best=best, models=fitted)


def _coding_plots(best, texts, tasks, results_dir: Path, *, cv: int, random_seed: int) -> List[str]:
    from sklearn.metrics import confusion_matrix
    from .plots import _plt
    plt = _plt()
    saved: List[str] = []

    # Macro-F1 per task (best model), most learnable on top
    b = best.sort_values("f1_macro").reset_index(drop=True)
    fig = plt.figure(figsize=(7, max(3.5, 0.35 * len(b))))
    plt.barh(b["task"], b["f1_macro"])
    plt.axvline(0.5, ls="--", c="k", lw=0.8)
    plt.title("ML-assisted coding: macro-F1 by task (best model, CV)")
    plt.xlabel("macro-F1")
    p = results_dir / "lit_coding_f1_by_task.png"
    fig.savefig(p, dpi=200, bbox_inches="tight"); plt.close(fig); saved.append(str(p))

    # Confusion matrix for the sector task (out-of-fold predictions)
    y = tasks.get("sector")
    if y is not None and y.notna().sum() > 0:
        row = best[best["task"] == "sector"]
        if not row.empty:
            pipe = make_text_models(random_seed)[str(row.iloc[0]["model"])]
            mask = y.notna()
            X, yy = texts[mask].to_numpy(), y[mask].astype(str).to_numpy()
            folds = int(row.iloc[0]["cv_folds"])
            skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=random_seed)
            pred = cross_val_predict(pipe, X, yy, cv=skf)
            labels = sorted(set(yy))
            cm = confusion_matrix(yy, pred, labels=labels)
            fig = plt.figure(figsize=(4.5, 4))
            plt.imshow(cm)
            plt.xticks(range(len(labels)), labels); plt.yticks(range(len(labels)), labels)
            for i in range(len(labels)):
                for j in range(len(labels)):
                    plt.text(j, i, cm[i, j], ha="center", va="center", color="w")
            plt.title("Sector task: out-of-fold confusion matrix")
            plt.xlabel("predicted"); plt.ylabel("true")
            p = results_dir / "lit_coding_sector_confusion.png"
            fig.savefig(p, dpi=200, bbox_inches="tight"); plt.close(fig); saved.append(str(p))

    return saved


def predict_codes(bundle_path: Path | str, papers: pd.DataFrame) -> pd.DataFrame:
    """Apply a saved coder bundle to new papers → one prediction column per task.

    ``papers`` needs ``title`` (and ideally ``abstract``) columns. Returns a
    frame indexed like ``papers`` with a ``pred_<task>`` column per task.
    """
    with open(bundle_path, "rb") as f:
        bundle = pickle.load(f)
    texts = build_text(papers).to_numpy()
    out = pd.DataFrame(index=papers.index)
    for task, pipe in bundle["models"].items():
        out[f"pred_{task}"] = pipe.predict(texts)
    return out
