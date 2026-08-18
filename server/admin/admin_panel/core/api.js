export const ENDPOINTS = {
  token: "/admin/api/token", logout: "/admin/logout", health: "/health", healthAdapters: "/health/adapters",
  register: "/auth/register", users: "/auth/users", roles: "/auth/roles", changePassword: "/auth/change-password",
  blacklist: "/auth/blacklist",
  resetPassword: "/auth/reset-password", apiKeys: "/admin/api-keys", prompts: "/admin/prompts",
  adapterCapabilities: "/admin/adapters/capabilities", jobs: "/admin/jobs", logsTail: "/admin/logs/tail",
  logsFiles: "/admin/logs/files", renderMarkdown: "/admin/render-markdown", reloadAdapters: "/admin/reload-adapters",
  reloadTemplates: "/admin/reload-templates", restart: "/admin/restart", shutdown: "/admin/shutdown", pause: "/admin/pause",
  resume: "/admin/resume", adminExport: "/admin/export", login: "/admin/login", configSections: "/admin/config/sections",
  mcpServers: "/admin/mcp/servers", mcpTools: "/admin/mcp/tools", mcpDefaults: "/admin/mcp/defaults", mcpReload: "/admin/mcp/reload",
  adapterConfigs: "/admin/adapters/config", adapterSpecs: "/admin/adapters/specs", adapterCreate: "/admin/adapters",
  adapterPreview: "/admin/adapters/preview", adapterImport: "/admin/adapters/import",
  adapterAnswerOptions: "/admin/adapters/answer-options",
  adapterImportFormat: "/admin/adapters/import/format",
  auditEvents: "/admin/audit/events", costsUsage: "/admin/observability/usage",
  feedbackAnalytics: "/admin/api/feedback-analytics", serverInfo: "/admin/info",
};

export function createApi({ getAuthToken, onUnauthorized }) {
  return async function api(method, path, body) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    const opts = { method, headers: { "Content-Type": "application/json" }, signal: controller.signal };
    const token = getAuthToken();
    if (token) opts.headers.Authorization = "Bearer " + token;
    if (body !== undefined) opts.body = JSON.stringify(body);
    let resp;
    try { resp = await fetch(path, opts); }
    catch (err) { clearTimeout(timeoutId); if (err.name === "AbortError") throw new Error("Request timed out"); throw err; }
    clearTimeout(timeoutId);
    if (resp.status === 401) { onUnauthorized(); throw new Error("Session expired"); }
    const text = await resp.text();
    let data;
    try { data = JSON.parse(text); } catch (_) { data = text; }
    if (!resp.ok) {
      let message = text || resp.statusText;
      if (data && typeof data === "object") {
        if (Array.isArray(data.detail)) message = data.detail.map((item) => item && typeof item === "object" ? (item.msg || JSON.stringify(item)) : String(item)).join("; ");
        else if (data.detail && typeof data.detail === "object") message = data.detail.msg || JSON.stringify(data.detail);
        else if (data.detail) message = String(data.detail);
        else if (data.message) message = String(data.message);
        else message = JSON.stringify(data);
      }
      throw new Error(message);
    }
    return data;
  };
}
