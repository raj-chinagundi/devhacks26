const API_BASE = "/api";

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message = data?.detail || data?.message || "Request failed.";
    throw new Error(message);
  }

  return data;
}

export async function startRun(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    body: formData,
  });

  return parseResponse(response);
}

export async function fetchRun(runId) {
  const response = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
  return parseResponse(response);
}
