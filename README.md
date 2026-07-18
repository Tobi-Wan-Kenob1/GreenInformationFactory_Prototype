# 🌱 GreenInformationFactory – Open ML Pipeline for FAIR Sustainability Data

This repository provides an open, FAIR, and reproducible machine-learning pipeline for sustainability assessment in circular and bioeconomy contexts.
It was developed within the BioFairNet (Horizon Europe) project and supports transparent data-to-model workflows using Zenodo, GitHub, and open-source Python tools.

The pipeline is designed for:

researchers new to machine learning,

interdisciplinary sustainability teams,

lightweight execution (laptops / cloud / low-resource devices),

reproducible scientific publication of data, models, and results.

🎯 Key Features

✅ Modular notebook-based workflow (step-by-step learning & execution)

✅ FAIR data handling (Zenodo integration, metadata, reproducibility)

✅ Multiple ML models with hyperparameter optimization

✅ Sustainability proxy metrics (v1, PCA-based, assumption-based)

✅ Scenario & sensitivity analysis

✅ Automated Zenodo release publication (sandbox or production)

✅ Fully open-source (MIT license)

🧩 Pipeline Structure (Notebooks)

Each major task is implemented as a dedicated notebook:

Notebook	Purpose
01_download_store.ipynb	Download dataset (Zenodo or dummy data) and store locally
02_prepare_data.ipynb	Clean, normalize, and split data into Train/Test/Validation
03_train_optimize.ipynb	Train and optimize ML models (GridSearchCV)
04_sustainability_evaluation.ipynb	Compute sustainability proxy metrics
05_scenario_analysis.ipynb	Sensitivity & scenario analysis using best model
06_release_zenodo.ipynb	Collect outputs and publish release payload to Zenodo

This structure ensures clarity and accessibility for users unfamiliar with ML pipelines.

> ℹ️ Notebooks 02–05 are now **thin drivers** over the importable `gif` package
> (`src/gif/`): each one calls a single `gif.pipeline.run_*` function so the same
> logic runs identically from a notebook, the `gif` CLI, or CI. Column selection
> is config-driven (`metadata/pipeline_config.json`) rather than interactive, so
> runs are fully reproducible. See **Scripted / Non-Interactive Usage** below.

🧠 Machine Learning Models

By default, the pipeline trains and evaluates:

Linear Regression

Random Forest

Gradient Boosting

Support Vector Regression (SVR)

Neural Network (MLP)

Data is split as follows:

80% Training / 20% Validation

Training further split into Train/Test (80/20)

Optimization via GridSearchCV

Metrics: RMSE and R²

🌍 Sustainability Evaluation

Three proxy approaches are implemented:

v1 Linear Proxy

Simple weighted combination of process drivers

PCA-based Energy Index

Data-driven sustainability indicator using principal components

Assumption-based Proxy

Based on configurable JSON assumptions (metadata/sustainability_assumptions_v1.json)

Outputs include:

sustainability scores for test & validation sets

comparison plots

trade-off analysis (model performance vs sustainability)

🔬 Scenario & Sensitivity Analysis

The best-performing model is used to:

vary input parameters

analyze response sensitivity

explore transition scenarios

support decision-making and policy insights

This supports research questions such as:

Is the data lake sufficient in size and quality?
How stable are predictions across scenarios?

📦 Zenodo Integration (FAIR Release)

The pipeline supports automated publication of:

processed datasets

trained models

evaluation figures

sustainability metrics

scenario analysis outputs

All artifacts are collected into:

notebooks/release_payload/


and published via GitHub Actions to Zenodo using metadata from:

metadata/zenodo_params.json


Supports:

Zenodo Sandbox (testing)

Zenodo Production (official DOI release)

📁 Repository Structure
GreenInformationFactory_Prototype/
│
├── notebooks/
│   ├── 01_download_store.ipynb
│   ├── 02_prepare_data.ipynb
│   ├── 03_train_optimize.ipynb
│   ├── 04_sustainability_evaluation.ipynb
│   ├── 05_scenario_analysis.ipynb
│   └── 06_release_zenodo.ipynb
│
├── helper/
│   ├── sustainability_metrics.py
│   ├── upload_collector.py
│   └── utils.py
│
├── metadata/
│   ├── zenodo_params.json
│   └── sustainability_assumptions_v1.json
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── results/
│
└── .github/workflows/
    ├── zenodo-download.yml
    └── zenodo-upload.yml

⚙️ Requirements

Python ≥ 3.10

pandas, numpy, scikit-learn, matplotlib, seaborn

jq (for GitHub Actions)

Zenodo API token (sandbox or production)

🔐 Ethics & Governance

All published data and models are released under MIT license

No personal or sensitive data is included

Designed for transparency, reproducibility, and just transition research

Lightweight execution supports accessibility (smartphones / low hardware)

🌐 Scientific Context

Developed within the BioFairNet (Horizon Europe) project:

Supporting fair and inclusive green transitions in carbon-intensive regions through digital platforms, stakeholder co-creation, and sustainability assessment tools.

Planned dissemination:

IAERE Conference 2026 (Special Session on BioFairNet)

Open FAIR machine-learning pipelines for sustainability assessment

📖 How to Use (Quick Start)

Clone repository

Run notebooks sequentially:

01 → 02 → 03 → 04 → 05 → 06


Configure:

metadata/zenodo_params.json

metadata/sustainability_assumptions_v1.json

Publish results to Zenodo via notebook 06 or GitHub Actions

🧑‍💻 Scripted / Non-Interactive Usage (`gif` package + CLI)

In addition to the notebooks, the pipeline logic is available as an importable
package under `src/gif/`, so the whole workflow can be run unattended (CI,
servers, batch jobs) — no `input()` prompts.

Install (editable) — this also installs the `helper` package and the `gif` CLI:

```bash
pip install -e ".[dev]"      # dev extras add pytest; add ".[xgboost]" for XGBoost
```

Run stages from anywhere inside the repo (repo root is auto-detected):

```bash
gif validate                 # sanity-check the raw input file
gif models                   # list models available in this environment
gif prepare                  # clean + split raw data (writes data/processed + metadata)
gif train                    # train & grid-search models, save bundle + comparison
gif scenario --grid-points 41
gif all                      # prepare → train → scenario, end to end
```

Or from Python:

```python
from gif import run_all           # or: from gif.pipeline import run_prepare, run_train
result = run_all()
print(result["trained"].best_name)
```

**Models.** The zoo now includes `linreg, enet, rf, extratrees, gbr, svr, mlp`
plus optional `xgb` (registered automatically only if `xgboost` is installed).

**Sustainability.** A new composable eco-efficiency proxy
(`helper.sustainability_metrics.sustainability_eco_efficiency`, output per unit
environmental burden, ISO 14045 flavour) sits alongside the v1 / PCA /
assumption-based proxies.

📥 Zenodo Ingestion & WP1/D1.2 Literature Data

`gif.zenodo` talks to the Zenodo REST API directly — no GitHub-Actions detour —
with MD5 verification and provenance run-logs:

```bash
gif zenodo list --community biofairnet          # discover community records
gif zenodo pull 10.5281/zenodo.20743706         # download any record by DOI
```

`gif.literature` (+ notebook `07_literature_ingest.ipynb`) ingests the two
June-2026 WP1/D1.2 uploads — the literature **full list**
([10.5281/zenodo.20743706](https://doi.org/10.5281/zenodo.20743706)) and the
manually coded **codebook**
([10.5281/zenodo.20744025](https://doi.org/10.5281/zenodo.20744025), both
CC-BY-4.0 by Guerreschi, Lomuscio & Albanese) — into tidy, validated CSVs under
`data/processed/literature/`:

```bash
gif literature fetch      # download both records + prepare in one step
```

Outputs: `papers.csv` (366 papers, English snake_case columns),
`codes_long.csv` (tidy paper × dimension × source × code), and
`papers_coded.csv` (papers joined with the manual codes). The join is
title-based and validated — the codebook's positional ids drift after blank
spreadsheet rows, so mismatches are reported rather than silently misassigned.

**Hotspot analytics** (`gif literature analyze`, notebook
`08_literature_analytics.ipynb`): code frequencies by sector, country
mentions, geographic levels, publication years, and barrier×driver
co-occurrence → tables + figures under `data/results/literature/`.

**ML-assisted coding** (`gif literature train-coder`, notebook
`09_literature_coding_ml.ipynb`): TF-IDF text classifiers trained on the
manual codes so future literature batches can be pre-coded and only reviewed
by hand. Cross-validated macro-F1 on the current corpus: sector (AGRI vs
MINING) ≈ 0.93, region (EU vs non-EU) ≈ 1.0 — legitimately easy, non-EU
papers name Kenya/Canada in their abstracts — top barrier codes ≈ 0.80,
relevance ≈ 0.57 (only ~101 labeled papers; screening aid, not a replacement
for manual coding). Best model per task is bundled in
`notebooks/models/literature_coder.pkl`; apply it to new papers with
`gif.lit_ml.predict_codes`.

**FAIR release** (`gif literature stage-release`, notebook
`10_literature_release.ipynb`): stages the derived corpus + analytics +
coder bundle into `notebooks/release_payload/` and writes
`metadata/zenodo_params.json` with `isDerivedFrom` links to both source DOIs
and **CC-BY-4.0** (required — the payload derives from CC-BY data).
Staging never uploads: trigger the upload workflow afterwards **via a
`zenodo-ul-*` tag** (not the Actions UI form, whose defaults override the
params file). `use_sandbox: true` is the staged default — verify the sandbox
record, then flip it to `false` for the production DOI. The upload workflow
now reads `related_dois` and `upload_type` from the params file.

🎬 Guided Demo Tour (Dissemination)

Two animated, self-contained walkthroughs live at
**https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/**:

- **Guided tour** ([`docs/index.html`](docs/index.html)) — what the factory
  does, for conference and policy audiences: pipeline diagram with flowing
  data, 9 stations with the real result figures, auto-play mode for booth
  screens.
- **Researcher how-to** ([`docs/howto.html`](docs/howto.html)) — how to run it
  on your own data, step by step: publish your dataset on Zenodo → configure →
  `gif prepare/train/scenario` → publish your results back to Zenodo. With
  copy-paste command blocks.

A flipbook GIF for project reporting (`docs/assets/biofairnet_tour.gif`) is
regenerated with `python docs/make_tour_gif.py`.

🔎 Policy & Grant Finder (GitHub Pages, zero install)

**https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/finder/**

A five-stage, browser-only tool ([`docs/finder/`](docs/finder/)) that runs
straight from GitHub Pages — no installation, no server:

1. **Keywords** — enter search terms (with BioFairNet suggestions).
2. **Search** — EU policies via the EUR-Lex/CELLAR SPARQL endpoint and
   Horizon Europe call topics via the EU Funding & Tenders search API,
   queried live from the browser with automatic fallback to JSON snapshots
   under `docs/finder/data/`.
3. **Topic analysis** — client-side document-frequency analytics across all
   matched documents, incl. “bridge topics” present in both corpora.
4. **Scenarios** — combine policies and grants under selected topics into
   named scenarios (persisted in the browser's localStorage).
5. **Metrics** — potential funding (25–100 % range of the summed call
   budgets), **indicative cost savings** (avoided ETS/carbon costs, fines,
   waste, energy and input costs), and an **assumption-based CO₂ mitigation
   index** — all driven by the transparent, editable
   [`docs/finder/data/co2_assumptions.json`](docs/finder/data/co2_assumptions.json)
   (ranges after IPCC AR6 WGIII SPM.7). Each scenario gets a
   data-completeness **confidence rating** and an actionable
   **“how to proceed” recommendation**; CSV/JSON export.

The offline snapshot is refreshed weekly by the `finder-data` workflow
(`gif finder-data`, keywords in `docs/finder/data/snapshot_config.json`);
see [`docs/finder/PLAN.md`](docs/finder/PLAN.md) for the design.

🧪 Tests & CI

A `pytest` suite under `tests/` covers data prep, the model registry, training,
scenario analysis and all sustainability proxies:

```bash
pytest -q
```

GitHub Actions (`.github/workflows/ci.yml`) runs the suite on Python 3.10–3.12
for every push and pull request.

📜 License

MIT License
Open for reuse, extension, and replication.

🤝 Acknowledgements

Developed within:

BioFairNet GA (Horizon Europe)

To cite a specific release, use the version DOI (see GitHub releases).


[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16258165.svg)](https://doi.org/10.5281/zenodo.16258165)
