const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(message, { status, errorCode, details } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = errorCode;
    this.details = details;
  }
}

/** Thin fetch wrapper matching the backend's shared error-code JSON contract. */
export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(body.message || body.detail || `HTTP ${response.status}`, {
      status: response.status,
      errorCode: body.error_code,
      details: body.details,
    });
  }
  return body;
}
