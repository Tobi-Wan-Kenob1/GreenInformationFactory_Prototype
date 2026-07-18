# GreenInformationFactory — Open ML Pipeline for FAIR Sustainability Data

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16258165.svg)](https://doi.org/10.5281/zenodo.16258165)

An open, FAIR, and reproducible machine-learning pipeline for sustainability
assessment in circular and bioeconomy contexts, developed within
[BioFairNet](https://cordis.europa.eu/project/id/101181568) (Horizon Europe,
grant agreement 101181568). It supports transparent data-to-model workflows
using Zenodo, GitHub, and open-source Python tools — designed for researchers
new to machine learning, interdisciplinary sustainability teams, and
lightweight execution on laptops or low-resource devices.

**Live tools (GitHub Pages, nothing to install):**

| Tool | What it does |
|------|--------------|
| [Guided tour](https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/) | Animated walkthrough of the pipeline for conference and policy audiences |
| [Researcher how-to](https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/howto.html) | Step-by-step guide to running the pipeline on your own data |
| [Policy & Grant Finder](https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/finder/) | Keyword search across EU policies and Horizon Europe grants, with topic analytics, scenario building and indicative metrics |

## Contents

- [Pipeline overview](#pipeline-overview)
- [Quick start (notebooks)](#quick-start-notebooks)
- [Scripted usage: the `gif` package and CLI](#scripted-usage-the-gif-package-and-cli)
- [Machine-learning models](#machine-learning-models)
- [Sustainability evaluation](#sustainability-evaluation)
- [Policy & Grant Finder](#policy--grant-finder)
- [Zenodo integration (FAIR releases)](#zenodo-integration-fair-releases)
- [Literature data (WP1/D1.2)](#literature-data-wp1d12)
- [Repository structure](#repository-structure)
- [Tests & CI](#tests--ci)
- [License & acknowledgements](#license--acknowledgements)

## Pipeline overview

Each major task is a dedicated notebook; notebooks 02–05 are thin drivers over
the importable `gif` package (`src/gif/`), so the same logic runs identically
from a notebook, the `gif` CLI, or CI. Column selection is config-driven
(`metadata/pipeline_config.json`), making runs fully reproducible.

| Notebook | Purpose |
|----------|---------|
| `01_download_store.ipynb` | Download dataset (Zenodo or dummy data), store locally |
| `02_prepare_data.ipynb` | Clean, normalize, split into Train/Test/Validation |
| `03_train_optimize.ipynb` | Train and optimize ML models (GridSearchCV) |
| `04_sustainability_evaluation.ipynb` | Compute sustainability proxy metrics |
| `05_scenario_analysis.ipynb` | Sensitivity & scenario analysis with the best model |
| `06_release_zenodo.ipynb` | Collect outputs, publish release payload to Zenodo |
| `07_literature_ingest.ipynb` | Ingest the WP1/D1.2 literature datasets |
| `08_literature_analytics.ipynb` | Literature hotspot analytics (tables + figures) |
| `09_literature_coding_ml.ipynb` | ML-assisted literature coding |
| `10_literature_release.ipynb` | Stage the derived literature payload for Zenodo |

## Quick start (notebooks)

1. Clone the repository.
2. Run the notebooks sequentially: `01 → 02 → 03 → 04 → 05 → 06`.
3. Configure `metadata/zenodo_params.json` and
   `metadata/sustainability_assumptions_v1.json`.
4. Publish results to Zenodo via notebook 06 or GitHub Actions.

Requirements: Python ≥ 3.10; pandas, numpy, scikit-learn, matplotlib, seaborn;
`jq` for the GitHub Actions workflows; a Zenodo API token (sandbox or
production) for releases.

## Scripted usage: the `gif` package and CLI

The whole workflow also runs unattended (CI, servers, batch jobs) — no
`input()` prompts:

```bash
pip install -e ".[dev]"      # dev extras add pytest; ".[xgboost]" adds XGBoost
```

```bash
gif validate                 # sanity-check the raw input file
gif models                   # list models available in this environment
gif prepare                  # clean + split raw data
gif train                    # train & grid-search models
gif scenario --grid-points 41
gif all                      # prepare → train → scenario, end to end
gif finder-data              # refresh the Policy & Grant Finder snapshot
```

Or from Python:

```python
from gif import run_all
result = run_all()
print(result["trained"].best_name)
```

## Machine-learning models

The model zoo includes `linreg, enet, rf, extratrees, gbr, svr, mlp`, plus
optional `xgb` (registered automatically if `xgboost` is installed). Data is
split 80/20 into training/validation, with the training part further split
80/20 into train/test. Optimization uses GridSearchCV; metrics are RMSE and R².

## Sustainability evaluation

Four proxy approaches are implemented in `helper/sustainability_metrics.py`:

1. **v1 linear proxy** — weighted combination of process drivers
2. **PCA-based energy index** — data-driven indicator from principal components
3. **Assumption-based proxy** — configurable via `metadata/sustainability_assumptions_v1.json`
4. **Eco-efficiency proxy** — output per unit environmental burden (ISO 14045 flavour)

Outputs include sustainability scores for test and validation sets, comparison
plots, and a trade-off analysis (model performance vs. sustainability). The
best model then drives scenario and sensitivity analysis: varying input
parameters, analyzing response stability, and exploring transition scenarios
for decision-making and policy insights.

## Policy & Grant Finder

**https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/finder/**

A five-stage, browser-only tool (`docs/finder/`) that runs straight from
GitHub Pages:

1. **Keywords** — enter search terms.
2. **Search** — EU policies via the EUR-Lex/CELLAR SPARQL endpoint and Horizon
   Europe call topics via the EU Funding & Tenders search API, queried live
   from the browser with automatic fallback to JSON snapshots.
3. **Topic analysis** — client-side document-frequency analytics, including
   "bridge topics" present in both corpora.
4. **Scenarios** — combine policies and grants under selected topics
   (persisted in the browser's localStorage).
5. **Metrics** — potential funding (25–100 % of summed call budgets),
   indicative cost savings (avoided ETS/carbon costs, fines, waste, energy and
   input costs), and an assumption-based CO₂ mitigation index, each with
   uncertainty ranges. Every scenario gets a data-completeness confidence
   rating (capped at 75/100 — it is a keyword screening, not a verified
   analysis) and a "how to proceed" recommendation with exemplary operational
   first steps per sector. CSV/JSON export.

All assumptions are transparent and editable in
`docs/finder/data/co2_assumptions.json` (CO₂ ranges after IPCC AR6 WGIII
SPM.7). The offline snapshot is refreshed weekly by the `finder-data`
workflow; keywords live in `docs/finder/data/snapshot_config.json`. Design
notes: `docs/finder/PLAN.md`.

## Zenodo integration (FAIR releases)

The pipeline publishes processed datasets, trained models, evaluation figures,
sustainability metrics and scenario outputs. Artifacts are collected into
`notebooks/release_payload/` and published via GitHub Actions using metadata
from `metadata/zenodo_params.json` — supporting both the Zenodo sandbox
(testing) and production (official DOI release). Trigger uploads **via a
`zenodo-ul-*` tag** (not the Actions UI form, whose defaults override the
params file).

`gif.zenodo` also talks to the Zenodo REST API directly, with MD5 verification
and provenance run-logs:

```bash
gif zenodo list --community biofairnet   # discover community records
gif zenodo pull 10.5281/zenodo.20743706  # download any record by DOI
```

## Literature data (WP1/D1.2)

`gif.literature` ingests the two June-2026 WP1/D1.2 uploads — the literature
[full list](https://doi.org/10.5281/zenodo.20743706) and the manually coded
[codebook](https://doi.org/10.5281/zenodo.20744025) (both CC-BY-4.0 by
Guerreschi, Lomuscio & Albanese) — into tidy, validated CSVs under
`data/processed/literature/`:

```bash
gif literature fetch          # download both records + prepare in one step
gif literature analyze        # hotspot analytics → data/results/literature/
gif literature train-coder    # ML-assisted coding (TF-IDF classifiers)
gif literature stage-release  # stage the derived FAIR release payload
```

Cross-validated macro-F1 on the current corpus: sector ≈ 0.93, region ≈ 1.0,
top barrier codes ≈ 0.80, relevance ≈ 0.57 (screening aid, not a replacement
for manual coding). The staged release links `isDerivedFrom` to both source
DOIs and is CC-BY-4.0 (required, as the payload derives from CC-BY data).

## Repository structure

```
GreenInformationFactory_Prototype/
├── notebooks/            # step-by-step workflow (01–10)
├── src/gif/              # importable pipeline package + CLI
├── helper/               # sustainability metrics, upload collector, utils
├── metadata/             # pipeline config, Zenodo params, assumptions
├── data/                 # raw / processed / results
├── docs/                 # GitHub Pages: tour, how-to, Policy & Grant Finder
├── tests/                # pytest suite
└── .github/workflows/    # CI, Zenodo up/download, finder data snapshot
```

## Tests & CI

```bash
pytest -q
```

GitHub Actions (`.github/workflows/ci.yml`) runs the suite on Python
3.10–3.12 for every push and pull request.

## License & acknowledgements

MIT License — open for reuse, extension, and replication. No personal or
sensitive data is included; the pipeline is designed for transparency,
reproducibility, and just-transition research.

Developed within [BioFairNet](https://cordis.europa.eu/project/id/101181568),
funded by the European Union's Horizon Europe programme (grant agreement
101181568): supporting fair and inclusive green transitions in carbon-intensive
regions through digital platforms, stakeholder co-creation, and sustainability
assessment tools. Planned dissemination: IAERE Conference 2026 (Special Session
on BioFairNet).

To cite a specific release, use the version DOI (see GitHub releases).
