# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
`.gitignore` lists it under "Claude Code 전용 파일 (프로젝트 산출물 아님)", but it was already committed
before that rule was added, so git still tracks it (see "Gitignore notes" below) — edits here will show
up in `git status` until someone explicitly untracks it.

## Project overview

**middle-project** ("산업 설비 안전 위험 통보 및 대응 시스템") is a closed-loop, multi-agent industrial
safety system: factory sensor readings flow through an ML risk model, a deterministic risk/emergency
policy, and a LangGraph pipeline that retrieves grounded SOP/legal guidance (RAG), drafts a worker
checklist, validates it against the source documents, and pauses for a human worker to respond —
optionally triggering an immediate re-measurement and/or a maintenance-request approval flow.

This branch (`feature/agent-contract-integration`) is well past the original "tabular-ML only" stage
described in older docs (`프로젝트_요약.md`, and the git history's early `data`/`rag` branches) — the
full FastAPI + LangGraph backend in `app/` is implemented, tested, and runnable. Treat `프로젝트_요약.md`
as a historical snapshot of the ML-only stage, not current state.

`main.py` is the real FastAPI entrypoint (not a placeholder): it builds the DB tables and compiles the
LangGraph safety graph once at startup (`lifespan`), then mounts the sensor/alert/worker/maintenance
routers plus the `/demo` static HTML.

## Environment & commands

Dependency/env management is via **uv** (`uv.lock` present, `requires-python = ">=3.13"`).

```
uv sync                                   # install/sync all dependencies into .venv
uv run uvicorn main:app --reload          # run the FastAPI app (http://127.0.0.1:8000)
uv run pytest                             # run the full test suite (tests/unit + tests/integration)
uv run python -m scripts.index_documents  # index data/sop + data/laws into Chroma (see RAG section)
uv run jupyter lab                        # open the legacy ML notebooks
```

Copy `.env.example` to `.env` to override defaults (SQLite DB path works out of the box with no setup).
Secrets/config are read only from environment variables (`app/core/config.py`) — never hardcode paths
or API keys.

pytest config lives in `pyproject.toml` (`testpaths = ["tests"]`, `asyncio_mode = "auto"`). There is no
configured linter/formatter (no ruff/mypy config) — don't assume one runs in CI.

## Architecture — LangGraph closed-loop safety pipeline

The graph is assembled in `app/graph/builder.py::build_safety_graph`, with per-role node
implementations injected via a `GraphDependencies` dataclass (`default_graph_dependencies()` wires the
real implementations; tests can swap in fakes). Shared state is the `SafetyState` `TypedDict`
(`app/graph/state.py`) — every node reads/writes a subset of it and returns only the fields it changed.

Flow:

```
START -> predictive_agent -> risk_policy
                                 |-- NORMAL -----------------------------------> recovery_node -> END
                                 '-- CAUTION/WARNING/EMERGENCY -> alert_lifecycle_node
                                                                       |-- always: rag_agent -\
                                                                       |-- always: memory_agent -+-> context_guard
                                                                       '-- EMERGENCY only: send_immediate_alert -> worker_interrupt
                                 context_guard -> action_draft_node -> validator_agent
                                                       ^                    |-- PASSED -> worker_interrupt -> request_immediate_recheck -> END
                                                       '------ REVISE ------|  (max 2 attempts, then -> checklist_validation_failure -> END)
                                                                            '-- error -> checklist_validation_failure -> END
```

Key mechanics:
- **Fan-out/fan-in**: `alert_lifecycle_node` fans out to `rag_agent` + `memory_agent` (and, for
  EMERGENCY, also `send_immediate_alert` in parallel — the pre-notification never waits on the
  checklist). `context_guard` is the fan-in barrier that fails fast if either branch didn't produce
  usable output before `action_draft_node` runs.
- **Revision loop**: `validator_agent` never edits worker-facing text itself — it either passes the
  draft through (`PASSED`) or returns structured `validation_feedback` for `action_draft_node` to
  revise (`REVISE`, capped at `MAX_VALIDATION_ATTEMPTS = 2` before hard-failing).
- **Human-in-the-loop**: `worker_interrupt` (`app/nodes/worker_interrupt.py`) calls LangGraph's
  `interrupt()` and pauses the run. `POST /worker/checklists/{id}/respond` resumes it with
  `Command(resume=...)`, using `thread_id = f"{machine_id}:{alert_id}"` (`app/core/ids.py`) to find the
  paused run via the checkpointer (`InMemorySaver` by default — state is lost on process restart).
- **Error handling convention**: nodes generally catch their own exceptions and return
  `{"error_code": ..., "error_message": ..., "failed_node": ...}` rather than raising, so routing
  functions (`_route_after_*` in `builder.py`) can short-circuit to `END`. `action_draft`, `validator`,
  and `memory_agent` are exceptions — they `raise` typed `ApplicationError` subclasses instead, and the
  API layer (or a wrapping closure, see `_default_memory_agent`'s `use_database_memory` path) converts
  those to the same error-field shape.
- Every reading — normal or not — arrives at `POST /sensors/ingest` (`app/api/sensor_routes.py`);
  there's no real IoT hardware, `measurement_mode` (`PERIODIC` vs `IMMEDIATE_RECHECK`) distinguishes a
  fresh periodic reading from a worker-triggered recheck.

## Agents & nodes

- **`app/agents/predictive.py`** — wraps `MLService`/`ml_service.predict_risk_score` to produce
  `ml_risk_score`, `model_version`, `prediction_thresholds` from a persisted model artifact.
- **`app/nodes/risk_policy.py`** — deterministic, no LLM. Combines the ML score against
  `caution`/`warning` thresholds with **per-machine-type hardcoded emergency rules**
  (`EMERGENCY_RULES`, e.g. reactor `temperature >= 42`, compressor `vibration >= 4.8`) that always
  override the ML-derived level. `POLICY_VERSION = "demo-risk-policy-v1"`.
- **`app/nodes/alert_lifecycle.py`** — owns `alert_status`/`repeat_count` transitions for
  abnormal/emergency readings (the 7-state lifecycle in `AlertStatus`); `ESCALATED` never auto-clears,
  only a manager decision does. Does **not** yet consider `memory_context` for escalation — noted as a
  known gap in its own docstring.
- **`app/nodes/recovery.py`** — the NORMAL-route counterpart: walks an active alert through
  `MONITORING` (2 consecutive normal readings) to `RESOLVED` without sending any notification.
- **`app/agents/rag.py`** (`rag_agent`) — builds a query from machine/risk/sensor context, retrieves
  from the Chroma vector store (`app/services/rag_service.py`, `vector_store_factory.py`), and requires
  at least one `document_type == "sop"` hit or fails with `RAG_RETRIEVAL_FAILED`. Falls back to reading
  `data/sop/{manual_id}.md` + up to 2 `data/laws/*.md` files directly off disk if the vector store call
  raises — this keeps the local demo runnable without a pre-built Chroma index.
- **`app/agents/memory/agent.py`** (`MemoryAgent`) — queries 4 repositories (alert/checklist/worker
  response/maintenance) for one `machine_id` and returns `memory_context` (unresolved count, previous
  risk level, repeat count, `is_risk_escalated`, `is_repeat_limit_exceeded` at `REPEAT_LIMIT_THRESHOLD =
  3`, etc.). Raises `MemoryLookupError` on failure — callers must catch it, it never returns an error
  dict itself. Note: `default_graph_dependencies()` only wires the real DB-backed
  `backend_memory_agent` when `use_database_memory=True`; otherwise it substitutes an empty stub
  context (`_default_memory_agent`).
- **`app/agents/action_draft/`** (`ActionDraftAgent`) — turns RAG documents + memory context into a
  `final_checklist`-shaped `action_draft`. `phase_selector.py` picks `INITIAL`/`FOLLOW_UP`/`EMERGENCY`
  by pure rule (no LLM); `draft_composer.py` calls an LLM (`llm_client.py`) to compose grounded items
  and falls back to a deterministic SOP-derived checklist if the LLM is unavailable — the graph's
  default dependency injects a client that always fails (`_FallbackLLMClient`) so the demo works
  without an API key. `maintenance_policy.py` decides `requires_maintenance_request`. On a revision
  pass it consumes `validation_feedback` + the previous draft to produce a new `version`.
- **`app/agents/validator/`** (`ValidatorAgent`) — never rewrites instructions. Runs deterministic
  checks (`source_grounding.py` filters ungrounded items, `deduplicator.py` merges duplicates,
  `expression_filter.py` blocks disallowed legal-conclusion phrasing) and only passes if all clear; LLM
  `safety_judge.py` output is attached as `safety_review` but is **advisory only** — it doesn't gate
  pass/fail.
- **`app/nodes/notification.py`** (`send_immediate_alert`) — EMERGENCY-only pre-notification via Slack
  webhook (`SLACK_ALERT_WEBHOOK_URL`), sent in parallel with RAG/Memory, before any checklist exists.
  Failure is swallowed to `notification_status=FAILED` — it must never block the RAG/Memory/checklist
  path.
- **`app/nodes/worker_interrupt.py`** — human-in-the-loop pause; validates the resumed payload against
  `WorkerResumePayload` and cross-checks `alert_id`/`checklist_id`/item IDs against the exact
  `final_checklist` that was shown, rejecting mismatches as `WorkerResponseValidationError`. Also
  normalizes the UI's compact `item_statuses` map into the canonical `item_results` shape.
- **`app/nodes/immediate_recheck.py`** — after a worker responds, moves the alert to
  `WAITING_RECHECK` and asks `app/services/iot_service.py` to request a new reading; the actual new
  reading arrives later as a normal `POST /sensors/ingest` call with `measurement_mode=IMMEDIATE_RECHECK`.

## API surface (`app/api/`)

- `POST /sensors/ingest` — ingest one reading, resume/open the machine's alert, run the graph.
- `GET /alerts/active/{machine_id}`, `GET /alerts/{alert_id}/checklist` — alert/checklist lookup.
- `POST /worker/checklists/{checklist_id}/respond` — resume a paused graph run with a worker response.
- `GET /maintenance-requests/pending`, `POST /maintenance-requests/{id}/decision` — manager
  approve/reject/defer flow for FR-14 (added 2026-07-24, not in the original 12-role contract; DB rows
  use camelCase on the wire via `alias_generator=to_camel`, snake_case internally).
- `/demo` — serves `demo/worker-manager-flow.html`, a static mock UI wired to call these APIs directly
  (CORS is opened for `localhost:8000`/`127.0.0.1:8000`/`file://` for this reason).

## Data & persistence

- **DB**: SQLAlchemy async models are the source of truth (`app/models/orm_models.py`); `db/schema.sql`
  is a hand-maintained mirror for reference only — if the two disagree, `orm_models.py` wins. No
  Alembic migrations yet (MVP stage) — tables are created via `Base.metadata.create_all()` at startup.
  Tables: `sensor_readings` (every reading, not just abnormal), `alerts`, `checklists`,
  `maintenance_requests`.
- **`data/machine_profiles.json`** — the 4 fixed demo machines (`M-0101` REACTOR, `M-0102` COMPRESSOR,
  `M-0103` STORAGE_TANK, `M-0104` PUMP), each with its `manual_id`/`manual_path`, hazards, emergency
  rule descriptions, and applicable Korean safety-law references. `SensorReading` validates
  `machine_id`↔`machine_type` against this same fixed mapping (`app/models/sensor.py::MACHINE_ID_TYPE_MAP`).
- **RAG documents**: `data/sop/*.md` (per-machine-type safety manuals) and `data/laws/*.md` (산업안전보건
  기준에 관한 규칙 조문). Indexed into Chroma via `scripts/index_documents.py` with 3 comparable chunking
  strategies (`section` / `fixed_512_50` / `fixed_1024_100`), each into its own collection
  (`safety_documents__<strategy>`); evaluation methodology and current numbers are in
  `docs/rag_evaluation.md` — that doc flags its numbers as **stale** (pre-dates splitting the SOP/law
  retrieval budget) and says to rerun `scripts/compare_chunking.py` before citing them.

## ML pipeline (legacy notebooks, still the source of the model artifacts)

`industrial_fire_custom_accident_ml.ipynb` trains the risk model from
`data/industrial_fire_risk_data.csv` (~100k synthetic factory readings; original `Accident`/`Risk`/`Alarm`
columns are treated as leakage and never used as features) and persists
`models/industrial_fire_accident_pipeline.joblib` + `models/industrial_fire_accident_metadata.json`
(feature list, `caution`/`warning` thresholds chosen by max F2 on the validation set, `manual_id` per
machine type). These are consumed by `app/services/ml_service.py` (`predictive_agent`'s dependency) —
regenerate by rerunning the notebook, don't hand-edit the artifacts. `mock_safety_alert_demo.ipynb` is
an older read-only demo of the same scoring logic, now superseded by the live `predictive_agent` +
`risk_policy` nodes.

## Testing

`tests/unit/` covers individual nodes/agents/repositories in isolation; `tests/unit/test_common_contracts.py`
freezes shared enum values and error codes that other components depend on — treat changes there as
breaking. `tests/integration/` exercises multi-node flows (`test_safety_graph.py`,
`test_worker_interrupt_flow.py`, `test_action_draft_validator_contract.py`, etc.) end-to-end through the
compiled graph. Several commit messages and docstrings refer to a "shared contract" (numbered sections,
e.g. "계약 8절", "계약 10절") — this is the team's cross-role interface agreement; when a docstring cites
a section number, treat it as intentional and don't casually change that field's shape without checking
what else depends on it.

## Gitignore notes worth knowing

- `docs/`, `CLAUDE.md`, and `_debrief/` are listed as local/Claude-Code-only material, not project
  deliverables. `docs/` and `_debrief/` were never committed, so they're genuinely absent from a fresh
  clone. `CLAUDE.md` is the exception — it was committed once before this rule existed, so it's still
  git-tracked; the ignore rule only stops *new* untracked copies from being added elsewhere, it doesn't
  retroactively hide this file from `git status`/`git diff`.
- `chroma_db/` (vector store data) and `models/*_metadata.json` (except the checked-in
  `industrial_fire_accident_metadata.json`) are regenerated artifacts.
- `dd.ipynb` and `중간프로젝트_지침서.docx` are personal/assignment files, intentionally excluded.
- `*.db`/`*.sqlite*` are gitignored — the default SQLite DB file is local-only and rebuilt from schema
  on each fresh `uv run uvicorn ...` startup.
