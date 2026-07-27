import { apiRequest, ApiError } from "./client.js";

/**
 * GET /alerts/active/{machineId} — the machine's currently open alert, or
 * `null` if none (the backend 404s when there's nothing active; that's a
 * normal state here, not an error worth surfacing to the caller).
 */
export async function getActiveAlert(machineId) {
  try {
    return await apiRequest(`/alerts/active/${encodeURIComponent(machineId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** GET /alerts/{alertId}/checklist — latest checklist generated for an alert. */
export async function getAlertChecklist(alertId) {
  try {
    return await apiRequest(`/alerts/${encodeURIComponent(alertId)}/checklist`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
