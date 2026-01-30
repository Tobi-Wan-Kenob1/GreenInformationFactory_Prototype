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

📜 License

MIT License
Open for reuse, extension, and replication.

🤝 Acknowledgements

Developed within:

BioFairNet GA (Horizon Europe)

To cite a specific release, use the version DOI (see GitHub releases).


[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16258165.svg)](https://doi.org/10.5281/zenodo.16258165)
