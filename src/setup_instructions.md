# 🛠️ Setup Instructions for GreenInformationFactory (Anaconda Cloud)

This guide describes how to set up and run this project on **Anaconda Cloud (notebooks.anaconda.org)** using the `environment.yml`.

---

## ✅ Prerequisites

- You have an account on [Anaconda.org](https://anaconda.org/)
- You are working inside the **Anaconda Cloud / Notebooks** environment: https://notebooks.anaconda.org/
- You have forked or uploaded this project to your **personal workspace**

---

## 📁 Files Required in Your Project

Make sure your uploaded files include:
.
├── environment.yml
├── README.md
├── setup_instructions.md
├── notebooks/
│ └── preprocessing.ipynb
├── src/
│ └── zenodo_utils.py
└── data/ (optional; not tracked by Git)


---

## 🚀 Step-by-Step Setup

### 1. Create a New Session in Anaconda Cloud

1. Go to your project on [notebooks.anaconda.org](https://notebooks.anaconda.org/)
2. Click **"New Session"**
3. Under **Environment**, choose:
   - 📄 **Import from file**
   - Select: `environment.yml`
4. Start the session. (This may take a few minutes to build the environment.)

---

### 2. Launch JupyterLab (Recommended)

Once the environment is ready:

1. Click **"Launch JupyterLab"** (or use classic Notebook if preferred)
2. Navigate to the `notebooks/` folder
3. Open `preprocessing.ipynb`

---

### 3. Select the Correct Kernel

In JupyterLab:

- Go to **Kernel > Change Kernel**
- Select the kernel corresponding to your environment (e.g. `Python (greeninfo)`)

---

## 📡 Notes on Zenodo Integration

The notebook will download raw data directly from Zenodo using this DOI:

- **DOI**: [10.5281/zenodo.16256961](https://doi.org/10.5281/zenodo.16256961)

Make sure you are connected to the internet to fetch the file.

---

## 📦 Optional: Upload Preprocessed Data to Zenodo

To upload cleaned datasets or models back to Zenodo, we recommend doing this **manually via Zenodo.org**, or using the [Zenodo REST API](https://developers.zenodo.org/), which can be integrated later.

---

## 🤝 Questions or Issues?

Please open a GitHub issue or contact the project maintainers through the Anaconda Cloud UI.

