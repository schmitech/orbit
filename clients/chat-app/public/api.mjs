var T = Object.defineProperty;
var x = (s, e, t) => e in s ? T(s, e, { enumerable: !0, configurable: !0, writable: !0, value: t }) : s[e] = t;
var f = (s, e, t) => x(s, typeof e != "symbol" ? e + "" : e, t);
let E = null, m = null;
typeof window > "u" && Promise.all([
  import("http").catch(() => null),
  import("https").catch(() => null)
]).then(([s, e]) => {
  var t, r;
  (t = s == null ? void 0 : s.default) != null && t.Agent ? E = new s.default.Agent({ keepAlive: !0 }) : s != null && s.Agent && (E = new s.Agent({ keepAlive: !0 })), (r = e == null ? void 0 : e.default) != null && r.Agent ? m = new e.default.Agent({ keepAlive: !0 }) : e != null && e.Agent && (m = new e.Agent({ keepAlive: !0 }));
}).catch((s) => {
  console.warn("Failed to initialize HTTP agents:", s.message);
});
class F {
  // Session ID can be mutable
  constructor(e) {
    f(this, "apiUrl");
    f(this, "apiKey");
    f(this, "sessionId");
    if (!e.apiUrl || typeof e.apiUrl != "string")
      throw new Error("API URL must be a valid string");
    if (e.apiKey !== void 0 && e.apiKey !== null && typeof e.apiKey != "string")
      throw new Error("API key must be a valid string or null");
    if (e.sessionId !== void 0 && e.sessionId !== null && typeof e.sessionId != "string")
      throw new Error("Session ID must be a valid string or null");
    this.apiUrl = e.apiUrl, this.apiKey = e.apiKey ?? null, this.sessionId = e.sessionId ?? null;
  }
  setSessionId(e) {
    if (e !== null && typeof e != "string")
      throw new Error("Session ID must be a valid string or null");
    this.sessionId = e;
  }
  getSessionId() {
    return this.sessionId;
  }
  // Helper to get fetch options with connection pooling if available
  getFetchOptions(e = {}) {
    const t = {};
    if (typeof window > "u") {
      const n = this.apiUrl.startsWith("https:") ? m : E;
      n && (t.agent = n);
    } else
      t.headers = { Connection: "keep-alive" };
    const r = {
      "X-Request-ID": Date.now().toString(36) + Math.random().toString(36).substring(2)
    };
    return t.headers && Object.assign(r, t.headers), e.headers && Object.assign(r, e.headers), this.apiKey && (r["X-API-Key"] = this.apiKey), this.sessionId && (r["X-Session-ID"] = this.sessionId), {
      ...e,
      ...t,
      headers: r
    };
  }
  // Create Chat request
  createChatRequest(e, t = !0, r) {
    const i = {
      messages: [
        { role: "user", content: e }
      ],
      stream: t
    };
    return r && r.length > 0 && (i.file_ids = r), i;
  }
  async *streamChat(e, t = !0, r) {
    var i;
    try {
      const n = new AbortController(), w = setTimeout(() => n.abort(), 6e4), c = await fetch(`${this.apiUrl}/v1/chat`, {
        ...this.getFetchOptions({
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: t ? "text/event-stream" : "application/json"
          },
          body: JSON.stringify(this.createChatRequest(e, t, r))
        }),
        signal: n.signal
      });
      if (clearTimeout(w), !c.ok) {
        const l = await c.text();
        throw new Error(`Network response was not ok: ${c.status} ${l}`);
      }
      if (!t) {
        const l = await c.json();
        l.response && (yield {
          text: l.response,
          done: !0
        });
        return;
      }
      const p = (i = c.body) == null ? void 0 : i.getReader();
      if (!p) throw new Error("No reader available");
      const k = new TextDecoder();
      let o = "", y = !1;
      try {
        for (; ; ) {
          const { done: l, value: A } = await p.read();
          if (l)
            break;
          const I = k.decode(A, { stream: !0 });
          o += I;
          let d = 0, g;
          for (; (g = o.indexOf(`
`, d)) !== -1; ) {
            const h = o.slice(d, g).trim();
            if (d = g + 1, h && h.startsWith("data: ")) {
              const u = h.slice(6).trim();
              if (!u || u === "[DONE]") {
                yield { text: "", done: !0 };
                return;
              }
              try {
                const a = JSON.parse(u);
                if (a.error)
                  throw new Error(`Server Error: ${a.error.message}`);
                if (a.response && (y = !0, yield { text: a.response, done: a.done || !1 }), a.done) {
                  yield { text: "", done: !0 };
                  return;
                }
              } catch (a) {
                console.warn("Error parsing JSON chunk:", a, "Chunk:", u);
              }
            } else h && (y = !0, yield { text: h, done: !1 });
          }
          o = o.slice(d), o.length > 1e6 && (console.warn("Buffer too large, truncating..."), o = o.slice(-5e5));
        }
        y && (yield { text: "", done: !0 });
      } finally {
        p.releaseLock();
      }
    } catch (n) {
      throw n.name === "AbortError" ? new Error("Connection timed out. Please check if the server is running.") : n.name === "TypeError" && n.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : n;
    }
  }
  async clearConversationHistory(e) {
    const t = e || this.sessionId;
    if (!t)
      throw new Error("No session ID provided and no current session available");
    if (!this.apiKey)
      throw new Error("API key is required for clearing conversation history");
    const r = {
      "Content-Type": "application/json",
      "X-Session-ID": t,
      "X-API-Key": this.apiKey
    };
    try {
      const i = await fetch(`${this.apiUrl}/admin/chat-history/${t}`, {
        ...this.getFetchOptions({
          method: "DELETE",
          headers: r
        })
      });
      if (!i.ok) {
        const w = await i.text();
        throw new Error(`Failed to clear conversation history: ${i.status} ${w}`);
      }
      return await i.json();
    } catch (i) {
      throw i.name === "TypeError" && i.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : i;
    }
  }
  /**
   * Upload a file for processing and indexing.
   * 
   * @param file - The file to upload
   * @returns Promise resolving to upload response with file_id
   * @throws Error if upload fails
   */
  async uploadFile(e) {
    if (!this.apiKey)
      throw new Error("API key is required for file upload");
    const t = new FormData();
    t.append("file", e);
    try {
      const r = await fetch(`${this.apiUrl}/api/files/upload`, {
        ...this.getFetchOptions({
          method: "POST",
          body: t
        })
      });
      if (!r.ok) {
        const i = await r.text();
        throw new Error(`Failed to upload file: ${r.status} ${i}`);
      }
      return await r.json();
    } catch (r) {
      throw r.name === "TypeError" && r.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : r;
    }
  }
  /**
   * List all files for the current API key.
   * 
   * @returns Promise resolving to list of file information
   * @throws Error if request fails
   */
  async listFiles() {
    if (!this.apiKey)
      throw new Error("API key is required for listing files");
    try {
      const e = await fetch(`${this.apiUrl}/api/files`, {
        ...this.getFetchOptions({
          method: "GET"
        })
      });
      if (!e.ok) {
        const t = await e.text();
        throw new Error(`Failed to list files: ${e.status} ${t}`);
      }
      return await e.json();
    } catch (e) {
      throw e.name === "TypeError" && e.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : e;
    }
  }
  /**
   * Get information about a specific file.
   * 
   * @param fileId - The file ID
   * @returns Promise resolving to file information
   * @throws Error if file not found or request fails
   */
  async getFileInfo(e) {
    if (!this.apiKey)
      throw new Error("API key is required for getting file info");
    try {
      const t = await fetch(`${this.apiUrl}/api/files/${e}`, {
        ...this.getFetchOptions({
          method: "GET"
        })
      });
      if (!t.ok) {
        const r = await t.text();
        throw new Error(`Failed to get file info: ${t.status} ${r}`);
      }
      return await t.json();
    } catch (t) {
      throw t.name === "TypeError" && t.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : t;
    }
  }
  /**
   * Query a specific file using semantic search.
   * 
   * @param fileId - The file ID
   * @param query - The search query
   * @param maxResults - Maximum number of results (default: 10)
   * @returns Promise resolving to query results
   * @throws Error if query fails
   */
  async queryFile(e, t, r = 10) {
    if (!this.apiKey)
      throw new Error("API key is required for querying files");
    try {
      const i = await fetch(`${this.apiUrl}/api/files/${e}/query`, {
        ...this.getFetchOptions({
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({ query: t, max_results: r })
        })
      });
      if (!i.ok) {
        const n = await i.text();
        throw new Error(`Failed to query file: ${i.status} ${n}`);
      }
      return await i.json();
    } catch (i) {
      throw i.name === "TypeError" && i.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : i;
    }
  }
  /**
   * Delete a specific file.
   * 
   * @param fileId - The file ID
   * @returns Promise resolving to deletion result
   * @throws Error if deletion fails
   */
  async deleteFile(e) {
    if (!this.apiKey)
      throw new Error("API key is required for deleting files");
    try {
      const t = await fetch(`${this.apiUrl}/api/files/${e}`, {
        ...this.getFetchOptions({
          method: "DELETE"
        })
      });
      if (!t.ok) {
        const r = await t.text();
        throw new Error(`Failed to delete file: ${t.status} ${r}`);
      }
      return await t.json();
    } catch (t) {
      throw t.name === "TypeError" && t.message.includes("Failed to fetch") ? new Error("Could not connect to the server. Please check if the server is running.") : t;
    }
  }
}
let v = null;
const $ = (s, e = null, t = null) => {
  v = new F({ apiUrl: s, apiKey: e, sessionId: t });
};
async function* C(s, e = !0, t) {
  if (!v)
    throw new Error("API not configured. Please call configureApi() with your server URL before using any API functions.");
  yield* v.streamChat(s, e, t);
}
export {
  F as ApiClient,
  $ as configureApi,
  C as streamChat
};
//# sourceMappingURL=api.mjs.map
