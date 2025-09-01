#include "orbit/api_client.hpp"
#include <curl/curl.h>
#include <sstream>
#include <stdexcept>

namespace orbit {

ApiClient::ApiClient(std::string api_url, std::string api_key, std::string session_id)
  : api_url_(std::move(api_url)), api_key_(std::move(api_key)), session_id_(std::move(session_id)) {}

std::string ApiClient::endpoint() const {
  if (api_url_.size() >= 8 && api_url_.rfind("/v1/chat") == api_url_.size() - 8) return api_url_;
  if (!api_url_.empty() && api_url_.back() == '/') return api_url_ + "v1/chat";
  return api_url_ + "/v1/chat";
}

struct WriteCtx {
  std::function<void(const StreamResponse&)> cb;
  std::string buffer;
};

static size_t on_write(char* ptr, size_t size, size_t nmemb, void* userdata) {
  auto* ctx = static_cast<WriteCtx*>(userdata);
  size_t total = size * nmemb;
  ctx->buffer.append(ptr, total);
  size_t pos = 0;
  for (;;) {
    auto nl = ctx->buffer.find('\n', pos);
    if (nl == std::string::npos) break;
    std::string line = ctx->buffer.substr(pos, nl - pos);
    pos = nl + 1;
    if (line.rfind("data: ", 0) == 0) {
      std::string payload = line.substr(6);
      if (payload == "[DONE]" || payload.empty()) {
        ctx->cb(StreamResponse{"", true});
        continue;
      }
      // naive extraction of response text; for robust use a JSON parser
      auto key = std::string{"\"response\":"};
      auto kpos = payload.find(key);
      if (kpos != std::string::npos) {
        auto start = payload.find('"', kpos + key.size());
        if (start != std::string::npos) {
          auto end = payload.find('"', start + 1);
          if (end != std::string::npos) {
            ctx->cb(StreamResponse{payload.substr(start + 1, end - start - 1), false});
          }
        }
      } else {
        ctx->cb(StreamResponse{payload, false});
      }
    }
  }
  // keep remainder
  ctx->buffer = ctx->buffer.substr(pos);
  return total;
}

void ApiClient::stream_chat(const std::string& message, bool stream, std::function<void(const StreamResponse&)> on_chunk) {
  CURL* curl = curl_easy_init();
  if (!curl) throw std::runtime_error("Failed to init curl");

  std::string url = endpoint();
  curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
  curl_easy_setopt(curl, CURLOPT_POST, 1L);

  std::ostringstream os;
  os << "{\"messages\":[{\"role\":\"user\",\"content\":";
  // very naive escape of quotes/newlines
  for (char c : message) {
    if (c == '\\') os << "\\\\";
    else if (c == '"') os << "\\\"";
    else if (c == '\n') os << "\\n";
    else os << c;
  }
  os << "}],\"stream\":" << (stream ? "true" : "false") << "}";
  auto payload = os.str();
  curl_easy_setopt(curl, CURLOPT_POSTFIELDS, payload.c_str());

  struct curl_slist* headers = nullptr;
  headers = curl_slist_append(headers, "Content-Type: application/json");
  headers = curl_slist_append(headers, stream ? "Accept: text/event-stream" : "Accept: application/json");
  if (!api_key_.empty()) {
    headers = curl_slist_append(headers, ("X-API-Key: " + api_key_).c_str());
  }
  if (!session_id_.empty()) {
    headers = curl_slist_append(headers, ("X-Session-ID: " + session_id_).c_str());
  }
  curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

  WriteCtx ctx{on_chunk, {}};
  curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, on_write);
  curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);

  CURLcode res = curl_easy_perform(curl);
  curl_slist_free_all(headers);
  curl_easy_cleanup(curl);
  if (res != CURLE_OK) {
    throw std::runtime_error("Request failed");
  }
}

} // namespace orbit

