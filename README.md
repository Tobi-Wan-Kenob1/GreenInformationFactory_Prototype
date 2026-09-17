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

**Scope:** the **agriculture and mining** sectors at **EU level**, matching the
BioFairNet WP1/D1.2 literature review. National and regional instruments are a
planned extension — every document already carries a `level` field so the other
levels can slot in beside the EU ones. Other sectors are out of scope.

A five-stage, browser-only tool (`docs/finder/`) that runs straight from
GitHub Pages:

1. **Keywords** — enter search terms. Search is **inclusive by default**: a
   thesaurus (`docs/finder/data/keyword_thesaurus.json`, 53 groups) bridges
   everyday and EU/academic wording in both directions, so “muck” finds
   *organic fertiliser* and *digestate*, “global warming” finds *greenhouse gas
   emissions*, “digging” finds *extractive industries*. The page shows exactly
   what each keyword expanded into, and the expansion can be switched off.
   Optionally set a **time window**: restrict the search to a past period
   (presets for the Horizon 2020 and FP7 eras) to benchmark an earlier setting
   against current research and market insights.
2. **Search** — EU policies via the EUR-Lex/CELLAR SPARQL endpoint and Horizon
   Europe call topics via the EU Funding & Tenders search API, queried live
   from the browser with automatic fallback to JSON snapshots. The source pills
   state plainly whether results are live, a cached snapshot, or bundled demo
   data.
3. **Topic analysis** — client-side document-frequency analytics. Topics can be
   drawn from both corpora ("bridge topics"), or from the policy or grant
   corpus alone. A **WP1 codebook coverage** panel matches the literature
   review's own barrier/driver/stakeholder codes against the found documents,
   showing which codes are addressed by policy *and* funding and which are
   blind spots — a purely lexical match, so every hit is verifiable in the
   source text. Regenerate the vocabulary with `gif finder-codebook`.
4. **Scenarios** — combine policies and grants under selected topics, or build
   **policy-only / grant-only** scenarios (persisted in the browser's
   localStorage, tagged with the time window they were built from).
5. **Metrics** — potential funding (25–100 % of summed call budgets),
   indicative cost savings (avoided ETS/carbon costs, fines, waste, energy and
   input costs), a relative CO₂ mitigation index, and **indicative
   abatement**: the scenario's own funding scaled by typical European
   abatement costs (€/tCO₂e) and a deployment factor, so the figure changes
   with the portfolio instead of restating a global sectoral total. A one-way
   **sensitivity** panel shows which assumptions drive each result and how far
   it swings across the input bands. Every scenario gets a data-completeness
   confidence rating (capped at 75/100 — it is a keyword screening, not a
   verified analysis) and a "how to proceed" recommendation with exemplary
   operational first steps per sector. CSV/JSON export.

All assumptions are transparent and editable in
`docs/finder/data/co2_assumptions.json` (CO₂ ranges after IPCC AR6 WGIII
SPM.7). Design notes: `docs/finder/PLAN.md`.

**Data sources and coverage.** The offline snapshot is refreshed weekly by the
`finder-data` workflow (`gif finder-data`); keywords live in
`docs/finder/data/snapshot_config.json`. Note two properties of the upstream
sources:

- *EUR-Lex/CELLAR* exposes no abstract, so each act's **EuroVoc descriptors**
  (`cdm:work_is_about_concept_eurovoc`) are pulled in as its summary — that is
  what the topic analytics run on, and what a keyword is matched against
  besides the title. Keywords are expanded in two separate layers —
  orthographic (`bioeconomy` also matches `bio-economy` / `bio economy`, since
  CELLAR matching is a raw substring test) and the plain-language thesaurus —
  so the two can be reasoned about and switched independently. Local matching
  and ranking use whole-word boundaries, so a short thesaurus term like
  `ground` does not fire on `background`. The SPARQL filter is capped at 40
  terms, since every `CONTAINS` is a scan. Cached policies reach back to 2000,
  so historical windows work offline. **CELLAR sends no CORS headers**, so a
  browser cannot call it directly: in practice policies always come from the
  snapshot, and the live tier only ever contributes grants.
- *EU Funding & Tenders (SEDIA)* caps a query's result set at 100 MB, so the
  fetcher queries **one keyword per request** rather than a combined `OR`, and
  filters out support FAQs and tenders that the API returns despite the type
  filter. The portal indexes Horizon 2020 onwards, so grant results do not
  reach back into FP7; historical grant benchmarking is limited by the source,
  not by the tool. Unlike CELLAR it does send CORS headers, so the browser's
  live tier does reach it.

Generate a snapshot for a specific past period with
`gif finder-data --since 2007-01-01 --until 2013-12-31 --out <dir>`.

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
top barrier codes ≈ 0.80–0.89, relevance ≈ 0.64 (screening aid, not a
replacement for manual coding). The bundle must be retrained whenever
scikit-learn moves a major version — a pickle written by an older version
cannot be loaded and `predict_codes` fails with an incompatible-dtype error. The staged release links `isDerivedFrom` to both source
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
pytest -q                      # Python: gif package, helpers, finder fetchers
node tests/browser/run.js      # browser: the Policy & Grant Finder UI
```

The finder is ~1,300 lines of browser JavaScript with no Python behind it, so
it has its own suite (`tests/browser/`) driving a real headless Chromium —
ranking, localStorage scenarios and the SVG charts only exist once a page has
run. Four specs cover search and the time window, the plain-language
thesaurus, topic analytics with WP1 codebook coverage, and the Stage-5
metrics. Run one with `node tests/browser/run.js synonyms`.

The suite serves `docs/` with **frozen fixtures** in place of
`docs/finder/data/{policies,grants}.json`: those are refreshed weekly by the
`finder-data` workflow, so asserting against them would fail CI every time the
EU corpus moved. Every assertion is therefore about the app's behaviour rather
than the state of the EU. First run needs `cd tests/browser && npm install`;
set `FINDER_TEST_CHROMIUM` to use a specific browser binary.

GitHub Actions (`.github/workflows/ci.yml`) runs the Python suite on Python
3.10–3.12 and the browser suite on every push and pull request. The Python
span matters: 3.10 resolves to pandas 2.x and 3.11+ to pandas 3.x, so the
matrix catches incompatibilities between the two major pandas lines.

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
