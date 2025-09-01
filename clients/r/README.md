# R Orbit Client

Streaming and non-streaming client for `/v1/chat` using the `curl` package.

## Usage

```r
source("R/orbit_api_client.R")
client <- orbit_api_client("http://localhost:3000")
stream_chat(client, "Hello from R!", TRUE, function(chunk) {
  cat(chunk$text)
  if (chunk$done) cat("\n")
})
```

Install deps: `install.packages(c("curl", "jsonlite"))`.

