import { apiRequest } from "./client.js";

/**
 * POST /worker/checklists/{checklistId}/respond — resume the paused graph run.
 *
 * Sends the canonical `WorkerResumePayload` shape directly (`app/models/worker.py`)
 * instead of the compact `item_statuses` shortcut: `item_results[].worker_note`
 * is a per-item note, matching the team's ChecklistScreen.jsx design (notes are
 * per checklist item, not one note for the whole submission). The compact
 * shape's normalizer (`worker_interrupt._normalize_worker_response`) copies a
 * single note onto every item, which can't express per-item notes - sending
 * `item_results` directly bypasses that normalization entirely.
 */
export function submitChecklistResponse(checklistId, { alertId, workerId = "ui-worker", items }) {
  const payload = {
    response_id: `RP-${alertId}-${Date.now()}`,
    alert_id: alertId,
    checklist_id: checklistId,
    worker_id: workerId,
    submitted_at: new Date().toISOString(),
    item_results: items.map((item) => ({
      checklist_item_id: item.checklistItemId,
      status: item.status,
      worker_note: item.note ? item.note.trim() : null,
    })),
  };
  return apiRequest(`/worker/checklists/${encodeURIComponent(checklistId)}/respond`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
