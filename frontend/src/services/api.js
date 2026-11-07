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

  getDocumentPreview: async (investigationId, documentId) => {
    const response = await fetch(
      `${API_BASE_URL}/investigations/${investigationId}/documents/${documentId}/preview`
    )
    if (!response.ok) {
      const contentType = response.headers.get('content-type') || ''
      const data = contentType.includes('application/json')
        ? await response.json()
        : await response.text()
      const message = typeof data === 'object' && data !== null
        ? data.detail || data.message
        : data
      throw new Error(message || `Request failed: ${response.status}`)
    }
    return response.blob()
  },

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

  generatePdfReport: (id) =>
    request(`/reports/${id}/generate-pdf`, {
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

  getAIEnvironment: () =>
    request("/ai/environment"),

  getAIInvestigations: () =>
    request("/ai/investigations/"),

  createAIInvestigation: (payload) =>
    request("/ai/investigations/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),

  getAIInvestigation: (id) =>
    request(`/ai/investigations/${id}`),

  updateAIInvestigation: (id, payload) =>
    request(`/ai/investigations/${id}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),

  archiveAIInvestigation: (id) =>
    request(`/ai/investigations/${id}`, {
      method: "DELETE",
    }),

  getAIAuditLogs: (id) =>
    request(`/ai/investigations/${id}/audit-logs`),

  linkStandardInvestigation: (aiId, standardId) =>
    request(`/ai/investigations/${aiId}/sources/${standardId}`, {
      method: "POST",
    }),

  selectAIStandardDocuments: (aiId, documentIds) =>
    request(`/ai/investigations/${aiId}/documents`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ document_ids: documentIds }),
    }),

  uploadAIDocument: (aiId, file) => {
    const formData = new FormData();
    formData.append("file", file);
    return request(`/ai/investigations/${aiId}/documents/upload`, {
      method: "POST",
      body: formData,
    });
  },

  startAIAnalysis: (id, payload) =>
    request(`/ai/investigations/${id}/analysis-runs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),

  getAIAnalysisRuns: (id) =>
    request(`/ai/investigations/${id}/analysis-runs`),

  getAIAnalysisRun: (id, runId) =>
    request(`/ai/investigations/${id}/analysis-runs/${runId}`),

  cancelAIAnalysis: (id, runId) =>
    request(`/ai/investigations/${id}/analysis-runs/${runId}/cancel`, {
      method: "POST",
    }),

  getAIChatHistory: (id) =>
    request(`/ai/investigations/${id}/chat`),

  sendAIChatMessage: (id, message) =>
    request(`/ai/investigations/${id}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    }),

  reviewAIFinding: (id, findingId, payload) =>
    request(`/ai/investigations/${id}/findings/${findingId}/reviews`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),

  getAIFindingReviews: (id, findingId) =>
    request(`/ai/investigations/${id}/findings/${findingId}/reviews`),

  generateAIReport: (id, runId) =>
    request(`/ai/investigations/${id}/analysis-runs/${runId}/generate-pdf`, {
      method: "POST",
    }),

  getAIReports: (id) =>
    request(`/ai/investigations/${id}/reports`),

  getAIReportDownloadUrl: (downloadUrl) =>
    `${API_BASE_URL}${downloadUrl}`,
};

export default api;