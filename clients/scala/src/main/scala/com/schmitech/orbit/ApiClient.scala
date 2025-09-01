package com.schmitech.orbit

import java.net.URI
import java.net.http.{HttpClient, HttpRequest, HttpResponse}
import java.nio.charset.StandardCharsets

case class StreamResponse(text: String, done: Boolean)

class ApiClient(apiUrl: String, apiKey: String = null, private var sessionId: String = null) {
  private val http = HttpClient.newBuilder().build()

  private def endpoint: String = if (apiUrl.endsWith("/v1/chat")) apiUrl else apiUrl.stripSuffix("/") + "/v1/chat"
  def setSessionId(id: String): Unit = sessionId = id

  private def jsonEscape(s: String): String =
    s.flatMap {
      case '"' => "\\\""
      case '\\' => "\\\\"
      case '\n' => "\\n"
      case '\r' => "\\r"
      case '\t' => "\\t"
      case c => c.toString
    }

  def streamChat(message: String, stream: Boolean = true)(onChunk: StreamResponse => Unit): Unit = {
    val body = s"{" + s"\"messages\":[{\"role\":\"user\",\"content\":\"${jsonEscape(message)}\"}]," + s"\"stream\":$stream}"
    val builder = HttpRequest.newBuilder()
      .uri(URI.create(endpoint))
      .header("Content-Type", "application/json")
      .header("Accept", if (stream) "text/event-stream" else "application/json")
      .header("X-Request-ID", java.lang.Long.toString(System.currentTimeMillis()))
      .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
    if (apiKey != null && !apiKey.isEmpty) builder.header("X-API-Key", apiKey)
    if (sessionId != null && !sessionId.isEmpty) builder.header("X-Session-ID", sessionId)

    val resp = http.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream())
    if (resp.statusCode() < 200 || resp.statusCode() >= 300) {
      val err = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8)
      throw new RuntimeException(s"HTTP ${'$'}{resp.statusCode()} ${'$'}err")
    }
    if (!stream) {
      val text = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8)
      val idx = text.indexOf("\"response\":\"")
      if (idx >= 0) {
        val s = text.indexOf('"', idx + 12); val e = if (s >= 0) text.indexOf('"', s + 1) else -1
        val t = if (s >= 0 && e > s) text.substring(s + 1, e) else text
        onChunk(StreamResponse(t, true))
      } else onChunk(StreamResponse(text, true))
      return
    }
    val reader = new java.io.BufferedReader(new java.io.InputStreamReader(resp.body(), StandardCharsets.UTF_8))
    var line: String = null
    while ({ line = reader.readLine(); line != null }) {
      val trimmed = line.trim
      if (trimmed.isEmpty) ()
      else if (trimmed.startsWith("data: ")) {
        val jsonText = trimmed.substring(6).trim
        if (jsonText.isEmpty || jsonText == "[DONE]") { onChunk(StreamResponse("", true)); return }
        val idx = jsonText.indexOf("\"response\":\"")
        if (idx >= 0) {
          val s = jsonText.indexOf('"', idx + 12); val e = if (s >= 0) jsonText.indexOf('"', s + 1) else -1
          if (s >= 0 && e > s) onChunk(StreamResponse(jsonText.substring(s + 1, e), jsonText.contains("\"done\":true")))
        } else onChunk(StreamResponse(jsonText, false))
      } else onChunk(StreamResponse(trimmed, false))
    }
  }
}

