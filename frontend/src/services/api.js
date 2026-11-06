const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(endpoint, options = {}) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

  const contentType = response.headers.get("content-type") || "";

  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message =
      typeof data === "object" && data !== null
        ? data.detail || data.message
        : data;

    throw new Error(message || `Request failed: ${response.status}`);
  }

  return data;
}

export const api = {
  health: () => request("/health"),

  createInvestigation: (payload) =>
    request("/investigations/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),

  getInvestigations: () =>
    request("/investigations/"),

  getInvestigation: (id) =>
    request(`/investigations/${id}`),

  getAnalysisRuns: (investigationId) =>
    request(`/investigations/${investigationId}/analysis-runs`),

  getAnalysisRun: (investigationId, runId) =>
    request(`/investigations/${investigationId}/analysis-runs/${runId}`),

  uploadDocument: (investigationId, file, forceOcr = false) => {
    const formData = new FormData();
    formData.append("file", file);

    return request(
      `/investigations/${investigationId}/documents?force_ocr=${forceOcr}`,
      {
        method: "POST",
        body: formData,
      }
    );
  },

  analyzeInvestigation: (id) =>
    request(`/investigations/${id}/analyze`, {
      method: "POST",
    }),

  generateReport: (id) =>
    request(`/reports/${id}/generate`, {
      method: "POST",
    }),

  getReports: (investigationId) =>
    request(`/reports/investigation/${investigationId}`),

  getReportDownloadUrl: (reportId) =>
    `${API_BASE_URL}/reports/${reportId}/download`,

  analyzeDocument: (file, forceOcr = false) => {
    const formData = new FormData();
    formData.append("file", file);

    return request(
      `/documents/analyze?force_ocr=${forceOcr}`,
      {
        method: "POST",
        body: formData,
      }
    );
  },
};

export default api;