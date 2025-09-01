use futures_util::{Stream, StreamExt, TryStreamExt};
use reqwest::{header::HeaderMap, Client};
use serde::{Deserialize, Serialize};
use std::pin::Pin;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamResponse {
    pub text: String,
    pub done: bool,
}

#[derive(Debug, Clone)]
pub struct ApiClient {
    api_url: String,
    api_key: Option<String>,
    session_id: Option<String>,
    http: Client,
}

#[derive(Serialize)]
struct Msg<'a> { role: &'a str, content: &'a str }

#[derive(Serialize)]
struct ChatRequest<'a> {
    messages: Vec<Msg<'a>>,
    stream: bool,
}

impl ApiClient {
    pub fn new<S: Into<String>>(api_url: S, api_key: Option<String>, session_id: Option<String>) -> Result<Self, reqwest::Error> {
        let http = Client::builder().tcp_keepalive(std::time::Duration::from_secs(60)).build()?;
        Ok(Self { api_url: api_url.into(), api_key, session_id, http })
    }

    fn headers(&self) -> HeaderMap {
        let mut h = HeaderMap::new();
        if let Some(k) = &self.api_key { h.insert("X-API-Key", k.parse().unwrap_or_default()); }
        if let Some(s) = &self.session_id { h.insert("X-Session-ID", s.parse().unwrap_or_default()); }
        h
    }

    fn endpoint(&self) -> String {
        if self.api_url.ends_with("/v1/chat") { self.api_url.clone() } else { format!("{}/v1/chat", self.api_url.trim_end_matches('/')) }
    }

    pub async fn stream_chat<'a>(&'a self, message: &'a str, stream: bool) -> Result<Pin<Box<dyn Stream<Item = Result<StreamResponse, reqwest::Error>> + Send + 'a>>, reqwest::Error> {
        let req_body = ChatRequest { messages: vec![Msg { role: "user", content: message }], stream };
        let mut req = self.http.post(self.endpoint())
            .headers(self.headers())
            .header("Content-Type", "application/json");
        if stream { req = req.header("Accept", "text/event-stream"); } else { req = req.header("Accept", "application/json"); }
        let resp = req.json(&req_body).send().await?;

        if !stream {
            // Non-streaming: parse JSON { response: string }
            let v: serde_json::Value = resp.json().await?;
            let text = v.get("response").and_then(|x| x.as_str()).unwrap_or_default().to_string();
            let s = futures_util::stream::once(async move { Ok(StreamResponse { text, done: true }) });
            return Ok(Box::pin(s));
        }

        let bytes_stream = resp.bytes_stream();
        let mut buf = String::new();
        let s = bytes_stream.map_ok(|chunk| String::from_utf8_lossy(&chunk).to_string())
            .map_ok(move |chunk| {
                let mut out: Vec<StreamResponse> = Vec::new();
                buf.push_str(&chunk);
                let mut start = 0usize;
                while let Some(idx) = buf[start..].find('\n') {
                    let line = buf[start..start + idx].trim().to_string();
                    start += idx + 1;
                    if line.is_empty() { continue; }
                    if line.starts_with("data: ") {
                        let data = line[6..].trim();
                        if data.is_empty() || data == "[DONE]" { out.push(StreamResponse { text: String::new(), done: true }); continue; }
                        if let Ok(v) = serde_json::from_str::<serde_json::Value>(data) {
                            let done = v.get("done").and_then(|x| x.as_bool()).unwrap_or(false);
                            if let Some(t) = v.get("response").and_then(|x| x.as_str()) {
                                out.push(StreamResponse { text: t.to_string(), done });
                            }
                            if done { out.push(StreamResponse { text: String::new(), done: true }); }
                        }
                    } else {
                        out.push(StreamResponse { text: line, done: false });
                    }
                }
                // retain the remainder
                let rem = buf[start..].to_string();
                buf.clear();
                buf.push_str(&rem);
                out
            })
            .map_ok(|v| futures_util::stream::iter(v.into_iter().map(Ok::<_, reqwest::Error>)))
            .try_flatten();

        Ok(Box::pin(s))
    }
}

