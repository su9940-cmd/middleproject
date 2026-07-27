import { apiRequest } from "./client.js";

/** GET /maintenance-requests/pending — every draft awaiting a manager decision. */
export function listPendingMaintenanceRequests() {
  return apiRequest("/maintenance-requests/pending");
}

/** POST /maintenance-requests/{id}/decision — approve/reject/defer a draft (FR-14). */
export function decideMaintenanceRequest(maintenanceRequestId, { decision, decidedBy, comment }) {
  return apiRequest(`/maintenance-requests/${encodeURIComponent(maintenanceRequestId)}/decision`, {
    method: "POST",
    body: JSON.stringify({
      maintenanceDecision: decision,
      decidedBy: decidedBy || null,
      comment: comment || null,
    }),
  });
}
