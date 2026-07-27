import { apiRequest } from "./client.js";

/** POST /sensors/ingest — submit one periodic or immediate-recheck reading. */
export function ingestSensorReading(payload) {
  return apiRequest("/sensors/ingest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
