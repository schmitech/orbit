source("../R/orbit_api_client.R")
url <- Sys.getenv("ORBIT_URL", "http://localhost:3000")
client <- orbit_api_client(url)
stream_chat(client, "Hello from R!", TRUE, function(chunk) {
  cat(chunk$text)
  if (chunk$done) cat("\n")
})

