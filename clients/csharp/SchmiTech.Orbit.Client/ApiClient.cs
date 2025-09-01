using System.Buffers;
using System.Net.Http.Headers;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;

namespace SchmiTech.Orbit;

public record StreamResponse(string Text, bool Done);

public class ApiClient
{
    private readonly string _apiUrl;
    private readonly string? _apiKey;
    private string? _sessionId;
    private readonly HttpClient _http;

    public ApiClient(string apiUrl, string? apiKey = null, string? sessionId = null)
    {
        _apiUrl = apiUrl ?? throw new ArgumentNullException(nameof(apiUrl));
        _apiKey = apiKey;
        _sessionId = sessionId;
        _http = new HttpClient(new SocketsHttpHandler { PooledConnectionLifetime = TimeSpan.FromMinutes(5) })
        {
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    private string Endpoint => _apiUrl.EndsWith("/v1/chat") ? _apiUrl : _apiUrl.TrimEnd('/') + "/v1/chat";

    public void SetSessionId(string? sessionId) => _sessionId = sessionId;
    public string? GetSessionId() => _sessionId;

    private HttpRequestMessage BuildRequest(string message, bool stream)
    {
        var req = new HttpRequestMessage(HttpMethod.Post, Endpoint);
        req.Headers.Accept.Clear();
        req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue(stream ? "text/event-stream" : "application/json"));
        if (!string.IsNullOrEmpty(_apiKey)) req.Headers.Add("X-API-Key", _apiKey);
        if (!string.IsNullOrEmpty(_sessionId)) req.Headers.Add("X-Session-ID", _sessionId);
        req.Headers.Add("X-Request-ID", DateTimeOffset.UtcNow.ToUnixTimeMilliseconds().ToString());

        var body = new
        {
            messages = new[] { new { role = "user", content = message } },
            stream
        };
        req.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");
        return req;
    }

    public async IAsyncEnumerable<StreamResponse> StreamChatAsync(string message, bool stream, [EnumeratorCancellation] CancellationToken ct = default)
    {
        using var req = BuildRequest(message, stream);
        using var resp = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        resp.EnsureSuccessStatusCode();

        if (!stream)
        {
            var json = await resp.Content.ReadAsStringAsync(ct);
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("response", out var r))
            {
                yield return new StreamResponse(r.GetString() ?? string.Empty, true);
                yield break;
            }
            yield return new StreamResponse(json, true);
            yield break;
        }

        await using var s = await resp.Content.ReadAsStreamAsync(ct);
        var reader = new StreamReader(s, Encoding.UTF8);
        string? line;
        while ((line = await reader.ReadLineAsync()) != null)
        {
            ct.ThrowIfCancellationRequested();
            line = line.Trim();
            if (line.Length == 0) continue;
            if (line.StartsWith("data: "))
            {
                var payload = line[6..].Trim();
                if (payload.Length == 0 || payload == "[DONE]")
                {
                    yield return new StreamResponse(string.Empty, true);
                    yield break;
                }
                try
                {
                    using var doc = JsonDocument.Parse(payload);
                    if (doc.RootElement.TryGetProperty("error", out var err) && err.TryGetProperty("message", out var msg))
                        throw new Exception(msg.GetString());
                    bool done = doc.RootElement.TryGetProperty("done", out var d) && d.GetBoolean();
                    if (doc.RootElement.TryGetProperty("response", out var t))
                        yield return new StreamResponse(t.GetString() ?? string.Empty, done);
                    if (done) { yield return new StreamResponse(string.Empty, true); yield break; }
                }
                catch
                {
                    yield return new StreamResponse(payload, false);
                }
            }
            else
            {
                yield return new StreamResponse(line, false);
            }
        }
    }
}

