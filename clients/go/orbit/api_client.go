package orbit

import (
    "bufio"
    "bytes"
    "context"
    "encoding/json"
    "errors"
    "io"
    "net/http"
    "strings"
    "time"
)

type StreamResponse struct {
    Text string
    Done bool
    Err  error
}

type ApiClient struct {
    apiURL    string
    apiKey    string
    sessionID string
    http      *http.Client
}

func NewApiClient(apiURL, apiKey, sessionID string) *ApiClient {
    return &ApiClient{
        apiURL:    apiURL,
        apiKey:    apiKey,
        sessionID: sessionID,
        http: &http.Client{Timeout: 0}, // infinite for streaming; we manage via context
    }
}

func (c *ApiClient) endpoint() string {
    if strings.HasSuffix(c.apiURL, "/v1/chat") { return c.apiURL }
    return strings.TrimRight(c.apiURL, "/") + "/v1/chat"
}

func (c *ApiClient) StreamChat(ctx context.Context, message string, stream bool) (<-chan StreamResponse, error) {
    body := map[string]any{
        "messages": []map[string]string{{"role": "user", "content": message}},
        "stream":   stream,
    }
    b, _ := json.Marshal(body)

    req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint(), bytes.NewReader(b))
    if err != nil { return nil, err }
    req.Header.Set("Content-Type", "application/json")
    if stream { req.Header.Set("Accept", "text/event-stream") } else { req.Header.Set("Accept", "application/json") }
    if c.apiKey != "" { req.Header.Set("X-API-Key", c.apiKey) }
    if c.sessionID != "" { req.Header.Set("X-Session-ID", c.sessionID) }
    req.Header.Set("X-Request-ID", time.Now().Format(time.RFC3339Nano))

    resp, err := c.http.Do(req)
    if err != nil { return nil, err }
    if resp.StatusCode < 200 || resp.StatusCode >= 300 {
        data, _ := io.ReadAll(resp.Body)
        resp.Body.Close()
        return nil, errors.New(string(data))
    }

    ch := make(chan StreamResponse)

    if !stream {
        go func() {
            defer close(ch)
            data, err := io.ReadAll(resp.Body)
            resp.Body.Close()
            if err != nil { ch <- StreamResponse{Err: err}; return }
            var v map[string]any
            if err := json.Unmarshal(data, &v); err == nil {
                if s, ok := v["response"].(string); ok {
                    ch <- StreamResponse{Text: s, Done: true}
                    return
                }
            }
            ch <- StreamResponse{Text: string(data), Done: true}
        }()
        return ch, nil
    }

    go func() {
        defer close(ch)
        defer resp.Body.Close()
        reader := bufio.NewReader(resp.Body)
        for {
            line, err := reader.ReadString('\n')
            if err != nil {
                if errors.Is(err, io.EOF) { return }
                ch <- StreamResponse{Err: err}
                return
            }
            line = strings.TrimSpace(line)
            if line == "" { continue }
            if strings.HasPrefix(line, "data: ") {
                payload := strings.TrimSpace(line[6:])
                if payload == "" || payload == "[DONE]" {
                    ch <- StreamResponse{Text: "", Done: true}
                    return
                }
                var v map[string]any
                if err := json.Unmarshal([]byte(payload), &v); err == nil {
                    if errObj, ok := v["error"].(map[string]any); ok {
                        if msg, ok := errObj["message"].(string); ok {
                            ch <- StreamResponse{Err: errors.New(msg)}
                            return
                        }
                    }
                    if s, ok := v["response"].(string); ok {
                        done := false
                        if d, ok := v["done"].(bool); ok { done = d }
                        ch <- StreamResponse{Text: s, Done: done}
                        if done { ch <- StreamResponse{Text: "", Done: true}; return }
                    }
                } else {
                    ch <- StreamResponse{Text: payload, Done: false}
                }
            } else {
                ch <- StreamResponse{Text: line, Done: false}
            }
        }
    }()

    return ch, nil
}

