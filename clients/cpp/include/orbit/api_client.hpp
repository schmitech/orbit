#pragma once
#include <functional>
#include <string>

namespace orbit {

struct StreamResponse {
  std::string text;
  bool done{false};
};

class ApiClient {
 public:
  ApiClient(std::string api_url, std::string api_key = {}, std::string session_id = {});
  void stream_chat(const std::string& message, bool stream, std::function<void(const StreamResponse&)> on_chunk);

 private:
  std::string endpoint() const;
  std::string api_url_;
  std::string api_key_;
  std::string session_id_;
};

} // namespace orbit

