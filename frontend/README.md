# frontend

React + Vite UI for the industrial safety system, built directly against the FastAPI backend in `../app`.

## Run

```
cd frontend
npm install
cp .env.example .env   # defaults to http://127.0.0.1:8000, edit if the backend runs elsewhere
npm run dev             # http://localhost:5173
```

The backend must be running separately (`uv run uvicorn main:app --reload` from the repo root) — this
app has no build-time knowledge of the API, it only calls it over HTTP. `main.py`'s CORS config already
allows `http://localhost:5173`.

## Pages

- **`/`** — Dashboard. The 4 fixed demo machines (`M-0101`..`M-0104`, see `src/constants/machines.js`),
  each showing its current alert status (`GET /alerts/active/{machineId}`) plus an inline sensor-reading
  form (`POST /sensors/ingest`) that stands in for real IoT hardware — "정상 값 채우기"/"긴급 값
  채우기" presets are tuned against the actual thresholds in `app/nodes/risk_policy.py`.
- **`/machines/:machineId/worker`** — the human-in-the-loop checklist screen. Loads the active alert's
  latest checklist and resumes the paused LangGraph run via `POST /worker/checklists/{id}/respond` once
  every item has a terminal status.
- **`/machines/:machineId/manager`** — read-only checklist review plus the FR-14 maintenance-request
  approve/reject/defer decision, if one was drafted for that alert.
- **`/maintenance`** — every pending maintenance-request draft across all machines in one table
  (`GET /maintenance-requests/pending`).

## Notes

- There is no endpoint to list *all* alerts/readings — the dashboard only knows about the 4 fixed
  machine IDs and asks for each one's active alert individually. If the backend ever adds a machine
  registry endpoint, `src/constants/machines.js` is the one place to replace with a real fetch.
- `src/api/*.js` mirrors the backend's response shapes exactly: `/alerts/*` responses are the raw
  SQLAlchemy ORM dump (snake_case), while `/maintenance-requests/*` uses an explicit camelCase
  `response_model` — that inconsistency is in the backend, not a frontend bug.
