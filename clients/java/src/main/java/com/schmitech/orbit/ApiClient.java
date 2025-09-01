package com.schmitech.orbit;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.function.Consumer;

public class ApiClient {
    private final String apiUrl;
    private final String apiKey; // nullable
    private String sessionId;    // nullable, mutable

    private final HttpClient http;

    public ApiClient(String apiUrl) {
        this(apiUrl, null, null);
    }

    public ApiClient(String apiUrl, String apiKey, String sessionId) {
        if (apiUrl == null || apiUrl.isEmpty()) {
            throw new IllegalArgumentException("API URL must be provided");
        }
        this.apiUrl = apiUrl;
        this.apiKey = apiKey;
        this.sessionId = sessionId;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    public void setSessionId(String sessionId) { this.sessionId = sessionId; }
    public String getSessionId() { return sessionId; }

    private Map<String, Object> createChatRequest(String message, boolean stream) {
        Map<String, Object> body = new HashMap<>();
        var messages = java.util.List.of(java.util.Map.of("role", "user", "content", message));
        body.put("messages", messages);
        body.put("stream", stream);
        return body;
    }

    private String toJson(Map<String, Object> map) {
        // Minimal JSON builder to avoid extra dependencies
        // Assumes only simple types and the known structure above
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"messages\":[{");
        sb.append("\"role\":\"user\",\"content\":");
        sb.append(escapeJsonString(((java.util.List<Map<String,String>>) map.get("messages")).get(0).get("content")));
        sb.append("}],");
        sb.append("\"stream\":").append(Boolean.TRUE.equals(map.get("stream")) ? "true" : "false");
        sb.append("}");
        return sb.toString();
    }

    private String escapeJsonString(String s) {
        StringBuilder sb = new StringBuilder();
        sb.append('"');
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 32) sb.append(String.format("\\u%04x", (int)c));
                    else sb.append(c);
                }
            }
        }
        sb.append('"');
        return sb.toString();
    }

    public void streamChat(String message, boolean stream, Consumer<StreamResponse> onChunk) throws IOException, InterruptedException {
        String url = apiUrl.endsWith("/v1/chat") ? apiUrl : apiUrl.replaceAll("/+$", "") + "/v1/chat";
        String requestId = Long.toString(System.currentTimeMillis(), 36) + UUID.randomUUID().toString().replace("-", "").substring(0,8);
        String body = toJson(createChatRequest(message, stream));

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(60))
                .header("Content-Type", "application/json")
                .header("Accept", stream ? "text/event-stream" : "application/json")
                .header("X-Request-ID", requestId)
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));

        if (apiKey != null && !apiKey.isEmpty()) builder.header("X-API-Key", apiKey);
        if (sessionId != null && !sessionId.isEmpty()) builder.header("X-Session-ID", sessionId);

        HttpResponse<java.io.InputStream> resp = http.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream());

        if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
            String err = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8);
            throw new IOException("Request failed: " + resp.statusCode() + " " + err);
        }

        if (!stream) {
            String text = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8);
            // naive parse for {"response":"..."}
            String responseText = extractJsonField(text, "response");
            onChunk.accept(new StreamResponse(responseText == null ? text : responseText, true));
            return;
        }

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(resp.body(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;
                if (line.startsWith("data: ")) {
                    String json = line.substring(6).trim();
                    if (json.isEmpty() || json.equals("[DONE]")) {
                        onChunk.accept(new StreamResponse("", true));
                        break;
                    }
                    String responseText = extractJsonField(json, "response");
                    String doneText = extractJsonField(json, "done");
                    boolean doneFlag = "true".equalsIgnoreCase(doneText);
                    if (responseText != null) {
                        onChunk.accept(new StreamResponse(responseText, doneFlag));
                    }
                    if (doneFlag) {
                        onChunk.accept(new StreamResponse("", true));
                        break;
                    }
                } else {
                    onChunk.accept(new StreamResponse(line, false));
                }
            }
        }
    }

    private String extractJsonField(String json, String field) {
        // Super-minimal JSON parsing; assumes simple flat fields with string or boolean
        String key = "\"" + field + "\"";
        int i = json.indexOf(key);
        if (i < 0) return null;
        int colon = json.indexOf(':', i + key.length());
        if (colon < 0) return null;
        int j = colon + 1;
        while (j < json.length() && Character.isWhitespace(json.charAt(j))) j++;
        if (j >= json.length()) return null;
        char c = json.charAt(j);
        if (c == '"') {
            int end = j + 1;
            boolean esc = false;
            StringBuilder out = new StringBuilder();
            for (; end < json.length(); end++) {
                char ch = json.charAt(end);
                if (esc) {
                    out.append(ch);
                    esc = false;
                } else if (ch == '\\') {
                    esc = true;
                } else if (ch == '"') {
                    break;
                } else {
                    out.append(ch);
                }
            }
            return out.toString();
        } else {
            // Assume boolean or number until comma or end brace
            int end = j;
            while (end < json.length() && ",}\n".indexOf(json.charAt(end)) == -1) end++;
            return json.substring(j, end).trim();
        }
    }
}

