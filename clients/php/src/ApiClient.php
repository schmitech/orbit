<?php

namespace SchmiTech\Orbit;

class StreamResponse {
    public string $text; public bool $done;
    public function __construct(string $text, bool $done) { $this->text = $text; $this->done = $done; }
}

class ApiClient {
    private string $apiUrl; private ?string $apiKey; private ?string $sessionId;
    public function __construct(string $apiUrl, ?string $apiKey = null, ?string $sessionId = null) {
        $this->apiUrl = $apiUrl; $this->apiKey = $apiKey; $this->sessionId = $sessionId;
    }
    private function endpoint(): string { return str_ends_with($this->apiUrl, '/v1/chat') ? $this->apiUrl : rtrim($this->apiUrl, '/') . '/v1/chat'; }
    public function setSessionId(?string $id): void { $this->sessionId = $id; }

    public function streamChat(string $message, bool $stream, callable $onChunk): void {
        $ch = curl_init($this->endpoint());
        $headers = [
            'Content-Type: application/json',
            'Accept: ' . ($stream ? 'text/event-stream' : 'application/json'),
            'X-Request-ID: ' . (string) (int) (microtime(true)*1000)
        ];
        if ($this->apiKey) $headers[] = 'X-API-Key: ' . $this->apiKey;
        if ($this->sessionId) $headers[] = 'X-Session-ID: ' . $this->sessionId;
        $body = json_encode(['messages' => [['role' => 'user', 'content' => $message]], 'stream' => $stream]);
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_POSTFIELDS => $body,
            CURLOPT_RETURNTRANSFER => false,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_WRITEFUNCTION => function($ch, $data) use ($onChunk) {
                static $buffer = '';
                $buffer .= $data;
                while (($pos = strpos($buffer, "\n")) !== false) {
                    $line = trim(substr($buffer, 0, $pos));
                    $buffer = substr($buffer, $pos + 1);
                    if ($line === '') continue;
                    if (str_starts_with($line, 'data: ')) {
                        $json = trim(substr($line, 6));
                        if ($json === '' || $json === '[DONE]') { $onChunk(new StreamResponse('', true)); continue; }
                        $obj = json_decode($json, true);
                        if (is_array($obj) && isset($obj['response'])) {
                            $done = isset($obj['done']) ? (bool)$obj['done'] : false;
                            $onChunk(new StreamResponse((string)$obj['response'], $done));
                            if ($done) $onChunk(new StreamResponse('', true));
                        } else {
                            $onChunk(new StreamResponse($json, false));
                        }
                    } else {
                        $onChunk(new StreamResponse($line, false));
                    }
                }
                return strlen($data);
            }
        ]);
        $ok = curl_exec($ch);
        if ($ok === false) throw new \RuntimeException('cURL error: ' . curl_error($ch));
        curl_close($ch);
    }
}

