"""Command-line entrypoint for the GreenInformationFactory pipeline.

Enables fully non-interactive, reproducible runs (CI, servers, batch jobs)::

    python -m gif.cli prepare
    python -m gif.cli train
    python -m gif.cli scenario --grid-points 41
    python -m gif.cli all
    python -m gif.cli validate      # validate raw input only
    python -m gif.cli models        # list available models in this env

Run from anywhere inside the repo; the repo root is auto-detected.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .config import load_config, resolve_paths
from .data import load_raw, validate_raw
from .models import available_models
from . import pipeline


def _cmd_validate(args) -> int:
    cfg = load_config()
    paths = resolve_paths(cfg)
    raw_path = paths.raw_dir / cfg["dataset"]["raw_filename"]
    df = load_raw(raw_path, sep=cfg["dataset"].get("separator", ";"),
                  encoding=cfg["dataset"].get("encoding", "utf-8"))
    problems = validate_raw(df, min_rows=1)
    if problems:
        print("❌ Raw data validation problems:")
        for p in problems:
            print("  -", p)
        return 1
    print(f"✅ Raw data OK: {df.shape[0]} rows × {df.shape[1]} cols at {raw_path}")
    return 0


def _cmd_models(args) -> int:
    print("Available models in this environment:")
    for m in available_models():
        print("  -", m)
    return 0


def _cmd_prepare(args) -> int:
    prepared = pipeline.run_prepare(strict=not args.lenient)
    print(f"✅ prepare: {prepared.report['rows_after_clean']} rows, "
          f"splits={prepared.report['splits']}")
    return 0


def _cmd_train(args) -> int:
    result = pipeline.run_train()
    print(f"✅ train: best model = {result.best_name}")
    print(result.results.to_string(index=False))
    return 0


def _cmd_scenario(args) -> int:
    out = pipeline.run_scenario(grid_points=args.grid_points, baseline_idx=args.baseline_idx)
    print(f"✅ scenario: {len(out)} rows across vars {sorted(out['_var'].unique())}")
    return 0


def _cmd_all(args) -> int:
    res = pipeline.run_all(grid_points=args.grid_points)
    print(f"✅ pipeline complete. best model = {res['trained'].best_name}")
    return 0


def _cmd_zenodo_list(args) -> int:
    from .zenodo import list_community_records
    records = list_community_records(args.community)
    print(f"📚 {len(records)} record(s) in community '{args.community}':")
    for r in records:
        print(f"  {r['publication_date']}  {r['doi']}  [{r['resource_type']}]")
        print(f"      {r['title']}")
    return 0


def _cmd_zenodo_pull(args) -> int:
    from .zenodo import download_record
    files = download_record(args.doi, args.dest, overwrite=args.overwrite)
    print(f"✅ {len(files)} file(s) in {args.dest}:")
    for f in files:
        print("  -", f.name)
    return 0


def _cmd_literature_prepare(args) -> int:
    from .literature import prepare_literature
    report = prepare_literature(args.full_list, args.codebook, args.out)
    j = report["join"]
    print(f"✅ literature prepared: {j['papers']} papers, "
          f"{report['codes_assigned']} codes, {j['title_mismatches']} title mismatch(es)")
    for name, path in report["outputs"].items():
        print(f"  - {name}: {path}")
    return 0


def _cmd_literature_fetch(args) -> int:
    """Download both D1.2 uploads from Zenodo, then prepare them."""
    from .literature import prepare_literature, D12_FULL_LIST_DOI, D12_CODEBOOK_DOI
    from .zenodo import download_record
    full = download_record(D12_FULL_LIST_DOI, args.dest)
    coded = download_record(D12_CODEBOOK_DOI, args.dest)
    report = prepare_literature(full[0], coded[0], args.out)
    j = report["join"]
    print(f"✅ fetched + prepared: {j['papers']} papers, "
          f"{report['codes_assigned']} codes, {j['title_mismatches']} title mismatch(es)")
    return 0


def _cmd_literature_analyze(args) -> int:
    from .lit_analytics import run_literature_analytics
    report = run_literature_analytics(args.lit_dir, args.results_dir)
    print(f"✅ analytics: {report['papers']} papers, {report['codes']} codes")
    print(f"  tables : {len(report['tables'])} CSV(s)")
    print(f"  figures: {len(report['figures'])} PNG(s) in {args.results_dir}")
    return 0


def _cmd_literature_train_coder(args) -> int:
    from .lit_ml import run_literature_coding
    result = run_literature_coding(
        args.lit_dir, args.results_dir, args.models_dir,
        min_papers=args.min_papers, cv=args.cv,
    )
    print(f"✅ trained {len(result.models)} coding task(s). Best models (CV macro-F1):")
    print(result.best[["task", "model", "f1_macro", "accuracy", "n"]]
          .to_string(index=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gif", description="GreenInformationFactory pipeline CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="Validate the raw input file").set_defaults(func=_cmd_validate)
    sub.add_parser("models", help="List available models").set_defaults(func=_cmd_models)

    prep = sub.add_parser("prepare", help="Clean & split raw data")
    prep.add_argument("--lenient", action="store_true", help="Warn instead of failing on validation problems")
    prep.set_defaults(func=_cmd_prepare)

    sub.add_parser("train", help="Train & grid-search models").set_defaults(func=_cmd_train)

    sc = sub.add_parser("scenario", help="One-way scenario analysis")
    sc.add_argument("--grid-points", type=int, default=25)
    sc.add_argument("--baseline-idx", type=int, default=0)
    sc.set_defaults(func=_cmd_scenario)

    al = sub.add_parser("all", help="Run prepare → train → scenario")
    al.add_argument("--grid-points", type=int, default=25)
    al.set_defaults(func=_cmd_all)

    # --- Zenodo ingestion (Phase 0) ---
    z = sub.add_parser("zenodo", help="Discover & download Zenodo records")
    zsub = z.add_subparsers(dest="zenodo_command", required=True)
    zl = zsub.add_parser("list", help="List records of a Zenodo community")
    zl.add_argument("--community", default="biofairnet")
    zl.set_defaults(func=_cmd_zenodo_list)
    zp = zsub.add_parser("pull", help="Download all files of a record by DOI/id")
    zp.add_argument("doi", help="DOI, record URL, or numeric record id")
    zp.add_argument("--dest", default="data/external")
    zp.add_argument("--overwrite", action="store_true")
    zp.set_defaults(func=_cmd_zenodo_pull)

    # --- Literature ingestion (Phase 1) ---
    lit = sub.add_parser("literature", help="Ingest the WP1/D1.2 literature datasets")
    lsub = lit.add_subparsers(dest="literature_command", required=True)
    lp = lsub.add_parser("prepare", help="Tidy local xlsx files into CSVs")
    lp.add_argument("--full-list", required=True, help="Path to the FULL LIST xlsx")
    lp.add_argument("--codebook", required=True, help="Path to the Coded File xlsx")
    lp.add_argument("--out", default="data/processed/literature")
    lp.set_defaults(func=_cmd_literature_prepare)
    lf = lsub.add_parser("fetch", help="Download both D1.2 records from Zenodo and prepare them")
    lf.add_argument("--dest", default="data/external")
    lf.add_argument("--out", default="data/processed/literature")
    lf.set_defaults(func=_cmd_literature_fetch)
    la = lsub.add_parser("analyze", help="Descriptive hotspot analytics (tables + figures)")
    la.add_argument("--lit-dir", default="data/processed/literature")
    la.add_argument("--results-dir", default="data/results/literature")
    la.set_defaults(func=_cmd_literature_analyze)
    lt = lsub.add_parser("train-coder", help="Train ML-assisted literature coding models")
    lt.add_argument("--lit-dir", default="data/processed/literature")
    lt.add_argument("--results-dir", default="data/results/literature")
    lt.add_argument("--models-dir", default="notebooks/models")
    lt.add_argument("--min-papers", type=int, default=15,
                    help="Minimum papers per code to train a per-code classifier")
    lt.add_argument("--cv", type=int, default=5)
    lt.set_defaults(func=_cmd_literature_train_coder)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
