import { apiRequest } from "./client.js";

/** POST /demo/reset — clear demo data and seed normal readings. */
export function resetDemoState() {
  return apiRequest("/demo/reset", { method: "POST" });
}
