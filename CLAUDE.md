# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a bootcamp/course "mid-term project" (중간프로젝트) predicting industrial accident risk from
factory sensor telemetry, with the eventual goal of pairing the ML risk score with a LangChain/RAG
agent that retrieves per-machine safety manuals. `pyproject.toml` already pulls in the full RAG stack
(LangChain, Chroma/Pinecone/pgvector, HuggingFace + OpenAI + Ollama model integrations, `ragas` for
eval), but as of this writing that agent code has not been written yet — the repo is still at the
tabular-ML stage.

`main.py` is currently just a placeholder (`print("Hello from middle-project!")`) and is not part of
the real pipeline.

## Important: local branch is behind `origin/data`

The checked-out branch is `data`. The actual ML pipeline (notebooks + derived data) lives one commit
ahead on `origin/data` and has **not been merged/pulled into this local branch**. If the notebooks or
`data/processed_industrial_fire_ml.csv` referenced below are missing on disk, run:

```
git fetch origin
git log --oneline data..origin/data   # inspect what's missing
git merge origin/data                 # or rebase, per user preference — confirm before doing this
```

Do not assume the working tree matches `origin/data` without checking — always verify a file exists
before editing or referencing it.

## Environment & commands

Dependency/env management is via **uv** (`uv.lock` present, `requires-python = ">=3.13"`,
`.python-version` pins 3.13).

```
uv sync                 # install/sync all dependencies into .venv
uv run python main.py   # run the placeholder entrypoint
uv run jupyter lab      # open the notebooks (see Architecture below)
```

There is no test suite, linter, or formatter configured in this repo (no pytest/ruff/mypy config) —
don't assume one exists.

Secrets (API keys for OpenAI/Pinecone/etc.) belong in `.env`, which is gitignored; there is no
`.env.example` committed yet.

## Data & ML architecture

Once `origin/data` is merged, the pipeline is two notebooks plus a raw data file:

- **`data/industrial_fire_risk_data.csv`** — raw source data (~100k rows, 15-min interval readings):
  `Date, Time, Factory, Region, Shift, Workers, Exp, Training, Temp, Pressure, Humidity, Vibration,
  Speed, Age, Service_Days, Gas, Sparks, Alarm, Risk, Accident`. The original `Accident`/`Risk`/`Alarm`
  columns are the dataset's built-in labels and are treated as **leakage columns** — never used as
  model features.

- **`industrial_fire_custom_accident_ml.ipynb`** (on `origin/data`) — the one-time training notebook:
  1. Splits the raw factories into 4 synthetic machines (`M-0101` REACTOR, `M-0102` COMPRESSOR,
     `M-0103` STORAGE_TANK, `M-0104` PUMP) via `machine_type_map`, and perturbs sensor columns per
     machine type to give each a distinct failure signature.
  2. Generates a synthetic label `custom_accident` from a per-machine-type logistic risk score
     (different sensors/interactions matter for a reactor vs. a pump), **not** derived from the
     original `Accident` column.
  3. Time-orders the data and splits 70/15/15 into train/validation/test (no shuffling — this is a
     temporal split, preserve that when touching it).
  4. Trains Logistic Regression vs. Random Forest, picks the model by validation PR-AUC.
  5. Chooses an alert **threshold** on the validation set by maximizing F2 (recall-weighted, since
     missed accidents are costlier than false alarms) — the test set is never used for threshold
     selection, only final reporting.
  6. Persists three artifacts consumed by the demo notebook: `data/processed_industrial_fire_ml.csv`,
     `models/industrial_fire_accident_pipeline.joblib`, and
     `models/industrial_fire_accident_metadata.json` (feature list, thresholds, test metrics,
     `manual_id` per machine type for future RAG lookup). These are gitignored — they are build
     outputs, regenerate by rerunning this notebook rather than trying to hand-edit them.

- **`mock_safety_alert_demo.ipynb`** (on `origin/data`) — a read-only downstream demo. It loads the
  three saved artifacts (fails fast with `FileNotFoundError` if they're missing — rerun the training
  notebook first), scores 12 hand-written mock IoT events, and classifies each into
  `정상/주의/경고/긴급` (normal/caution/warning/emergency):
  - `정상`/`주의`/`경고` come from comparing the ML probability to `caution_threshold` /
    `warning_threshold` from the metadata file.
  - `긴급` is decided by hardcoded **per-machine-type emergency rules** (e.g. reactor temp ≥ 42,
    compressor vibration ≥ 4.8) in `emergency_reason()` — these override the ML score entirely and
    always win over a lower ML-based status.
  - Each abnormal status maps to a fixed Korean checklist per machine type (`actions` dict), plus a
    `manual_id` (e.g. `reactor_safety_manual`) intended as the key for a future RAG manual lookup —
    no actual document retrieval is implemented yet.

## Gitignore notes worth knowing

- `dd.ipynb` and `중간프로젝트_지침서.docx` (the assignment brief) are intentionally gitignored as
  personal/local files — don't try to recreate or commit them.
- `data/*.parquet` and everything under `models/` are regenerated artifacts, not source — treat the
  training notebook as their single source of truth.
