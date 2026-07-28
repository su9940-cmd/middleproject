import { apiRequest, ApiError } from "./client.js";

/** GET /sensors/latest/{machineId} — latest persisted reading for the dashboard. */
export async function getLatestSensorReading(machineId) {
  try {
    return await apiRequest(`/sensors/latest/${encodeURIComponent(machineId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** POST /sensors/ingest — submit one periodic or immediate-recheck reading. */
export function ingestSensorReading(payload) {
  return apiRequest("/sensors/ingest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
