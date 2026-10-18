---
paths:
  - "notebooks/**"
  - "data_prep/**"
  - "evaluation/**"
---

# Rules for notebooks, data and evaluation

- Notebooks are thin: they clone the repo and import functions from `data_prep/`, `evaluation/` and `src/`. Logic does not live in cells.
- The MEDDOCAN corpus is downloaded by script (Zenodo, version 1.0, md5 verified). It is never versioned: `data/` is in `.gitignore`.
- Model weights are never versioned in git; they go to the Hugging Face Hub.
- Fix seeds (`transformers.set_seed`) and log hyperparameters and metrics for every run (at most 3).
- Save checkpoints to Drive or the Hub every epoch: free Colab sessions can be cut off.
- The cascade threshold is chosen on **dev**. The **test** set is used only once, for the final report.
- Cite MEDDOCAN (CC BY 4.0) in any published output.
