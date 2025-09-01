import Foundation

public struct StreamResponse { public let text: String; public let done: Bool }

public final class ApiClient {
    private let apiUrl: String
    private let apiKey: String?
    private var sessionId: String?

    public init(apiUrl: String, apiKey: String? = nil, sessionId: String? = nil) {
        self.apiUrl = apiUrl
        self.apiKey = apiKey
        self.sessionId = sessionId
    }

    private var endpoint: String { apiUrl.hasSuffix("/v1/chat") ? apiUrl : apiUrl.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/v1/chat" }

    public func setSessionId(_ id: String?) { self.sessionId = id }

    public func streamChat(message: String, stream: Bool = true) -> AsyncThrowingStream<StreamResponse, Error> {
        var req = URLRequest(url: URL(string: endpoint)!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(stream ? "text/event-stream" : "application/json", forHTTPHeaderField: "Accept")
        if let apiKey { req.setValue(apiKey, forHTTPHeaderField: "X-API-Key") }
        if let sessionId { req.setValue(sessionId, forHTTPHeaderField: "X-Session-ID") }
        req.setValue(String(Int64(Date().timeIntervalSince1970*1000)), forHTTPHeaderField: "X-Request-ID")
        let body: [String: Any] = ["messages":[["role":"user","content":message]], "stream": stream]
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    if stream {
                        let (bytes, response) = try await URLSession.shared.bytes(for: req)
                        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
                            throw URLError(.badServerResponse)
                        }
                        for try await line in bytes.lines {
                            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard !trimmed.isEmpty else { continue }
                            if trimmed.hasPrefix("data: ") {
                                let jsonText = String(trimmed.dropFirst(6)).trimmingCharacters(in: .whitespaces)
                                if jsonText.isEmpty || jsonText == "[DONE]" {
                                    continuation.yield(StreamResponse(text: "", done: true))
                                    continuation.finish()
                                    return
                                }
                                if let data = jsonText.data(using: .utf8),
                                   let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                                    if let err = obj["error"] as? [String: Any], let msg = err["message"] as? String {
                                        throw NSError(domain: "Orbit", code: 1, userInfo: [NSLocalizedDescriptionKey: msg])
                                    }
                                    let done = (obj["done"] as? Bool) ?? false
                                    if let text = obj["response"] as? String { continuation.yield(StreamResponse(text: text, done: done)) }
                                    if done { continuation.yield(StreamResponse(text: "", done: true)); continuation.finish(); return }
                                } else {
                                    continuation.yield(StreamResponse(text: jsonText, done: false))
                                }
                            } else {
                                continuation.yield(StreamResponse(text: trimmed, done: false))
                            }
                        }
                        continuation.finish()
                    } else {
                        let (data, response) = try await URLSession.shared.data(for: req)
                        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
                            throw URLError(.badServerResponse)
                        }
                        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let text = obj["response"] as? String {
                            continuation.yield(StreamResponse(text: text, done: true))
                        } else {
                            continuation.yield(StreamResponse(text: String(data: data, encoding: .utf8) ?? "", done: true))
                        }
                        continuation.finish()
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }
}

