# GreenInformationFactory_Prototype

**GreenInformationFactory** is an open, data-driven project for developing AI-based models to support ecodesign, sustainability assessments, and circular economy applications. It integrates reproducible workflows based on Jupyter Notebooks, FAIR data sharing (via Zenodo), and transparent model development hosted on GitHub.

---

## 📦 Project Structure

```bash
GreenInformationFactory/
│
├── notebooks/            # Jupyter notebooks for preprocessing, exploration, etc.
│
├── src/                  # Python scripts and training logic
│
├── data/                 # Processed or local raw data (DOI-linked)
│
├── models/               # Trained models (.pkl or .joblib)
│
├── environment.yml       # Conda environment definition
├── .gitignore
└── README.md             # You're here!

```

📂 Data Access
We rely on Zenodo for FAIR-compliant dataset storage:

Dataset	DOI	Description
Raw Experimental Data	10.5281/zenodo.XXXXXXX	Original input
Cleaned Dataset (v1)	10.5281/zenodo.YYYYYYY	Preprocessed for model training

🤖 Model Outputs
Trained models are stored in /models/ and linked to preprocessing versions.
Example:
```bash
models/
└── rf_model_v1.pkl
```

📜 License
This project is licensed under the MIT License – see the LICENSE file for details.

🔄 Versioning and DOI Integration
GitHub commits are tagged and optionally linked with Zenodo DOIs for citable releases.

To cite a specific release, use the version DOI (see GitHub releases).


[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.16258165.svg)](https://doi.org/10.5281/zenodo.16258165)
