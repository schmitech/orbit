Sys.setenv(LC_ALL="C")
source("../R/orbit_api_client.R")

if (Sys.getenv("ORBIT_INTEGRATION") != "1") {
  cat("Skipping integration test. Set ORBIT_INTEGRATION=1 to enable.\n")
  quit(status=0)
}

url <- Sys.getenv("ORBIT_URL", "http://localhost:3000")
client <- orbit_api_client(url)
buf <- ""
stream_chat(client, "ping", FALSE, function(chunk) { buf <<- paste0(buf, chunk$text) })
if (nchar(buf) == 0) { stop("Empty response") } else { cat("OK\n") }

