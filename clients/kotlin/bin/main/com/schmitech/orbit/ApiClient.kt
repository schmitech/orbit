package com.schmitech.orbit

import okhttp3.*
import okio.BufferedSource
import java.io.IOException

data class StreamResponse(val text: String, val done: Boolean)

class ApiClient(private val apiUrl: String, private val apiKey: String? = null, private var sessionId: String? = null) {
    private val client = OkHttpClient.Builder().build()

    private fun endpoint(): String = if (apiUrl.endsWith("/v1/chat")) apiUrl else apiUrl.trimEnd('/') + "/v1/chat"

    fun setSessionId(id: String?) { sessionId = id }

    private fun requestBody(message: String, stream: Boolean): RequestBody {
        val json = "{" +
                "\"messages\":[{\"role\":\"user\",\"content\":${escapeJson(message)}}]," +
                "\"stream\":$stream}"
        return json.toRequestBody("application/json".toMediaType())
    }

    private fun escapeJson(s: String): String {
        val sb = StringBuilder("\"")
        for (c in s) {
            when (c) {
                '\\' -> sb.append("\\\\")
                '"' -> sb.append("\\\"")
                '\n' -> sb.append("\\n")
                '\r' -> sb.append("\\r")
                '\t' -> sb.append("\\t")
                else -> sb.append(c)
            }
        }
        sb.append('"')
        return sb.toString()
    }

    fun streamChat(message: String, stream: Boolean = true, onChunk: (StreamResponse) -> Unit) {
        val reqBuilder = Request.Builder()
            .url(endpoint())
            .post(requestBody(message, stream))
            .addHeader("Content-Type", "application/json")
            .addHeader("Accept", if (stream) "text/event-stream" else "application/json")
            .addHeader("X-Request-ID", System.currentTimeMillis().toString())
        if (!apiKey.isNullOrEmpty()) reqBuilder.addHeader("X-API-Key", apiKey)
        if (!sessionId.isNullOrEmpty()) reqBuilder.addHeader("X-Session-ID", sessionId!!)

        client.newCall(reqBuilder.build()).enqueue(object: Callback {
            override fun onFailure(call: Call, e: IOException) {
                throw e
            }

            override fun onResponse(call: Call, response: Response) {
                response.use {
                    if (!response.isSuccessful) throw IOException("HTTP ${'$'}{response.code}")
                    val src: BufferedSource = response.body!!.source()
                    if (!stream) {
                        val text = response.body!!.string()
                        // naive parse for {"response":"..."}
                        val idx = text.indexOf("\"response\":\"")
                        if (idx >= 0) {
                            val start = text.indexOf('"', idx + 12)
                            val end = text.indexOf('"', start + 1)
                            val resp = if (start >= 0 && end > start) text.substring(start + 1, end) else text
                            onChunk(StreamResponse(resp, true))
                        } else onChunk(StreamResponse(text, true))
                        return
                    }
                    var buffer = StringBuilder()
                    while (!src.exhausted()) {
                        val line = src.readUtf8Line() ?: break
                        val trimmed = line.trim()
                        if (trimmed.isEmpty()) continue
                        if (trimmed.startsWith("data: ")) {
                            val jsonText = trimmed.substring(6).trim()
                            if (jsonText.isEmpty() || jsonText == "[DONE]") { onChunk(StreamResponse("", true)); return }
                            if (jsonText.contains("\"response\"")) {
                                val idx = jsonText.indexOf("\"response\":\"")
                                if (idx >= 0) {
                                    val s = jsonText.indexOf('"', idx + 12)
                                    val e = if (s >= 0) jsonText.indexOf('"', s + 1) else -1
                                    if (s >= 0 && e > s) onChunk(StreamResponse(jsonText.substring(s + 1, e), jsonText.contains("\"done\":true")))
                                }
                            } else {
                                onChunk(StreamResponse(jsonText, false))
                            }
                        } else {
                            onChunk(StreamResponse(trimmed, false))
                        }
                    }
                }
            }
        })
    }
}

