orbit_api_client <- function(api_url, api_key=NULL, session_id=NULL) {
  list(api_url=api_url, api_key=api_key, session_id=session_id)
}

endpoint <- function(client) {
  if (grepl("/v1/chat$", client$api_url)) client$api_url else paste0(sub("/+$/,", "", client$api_url), "/v1/chat")
}

stream_chat <- function(client, message, stream=TRUE, on_chunk=function(x){}) {
  url <- endpoint(client)
  h <- curl::new_handle()
  headers <- c(
    'Content-Type'='application/json',
    'Accept'= if (stream) 'text/event-stream' else 'application/json',
    'X-Request-ID'= as.character(as.integer(as.numeric(Sys.time())*1000))
  )
  if (!is.null(client$api_key)) headers['X-API-Key'] <- client$api_key
  if (!is.null(client$session_id)) headers['X-Session-ID'] <- client$session_id
  curl::handle_setheaders(h, .list=as.list(headers))
  body <- jsonlite::toJSON(list(messages=list(list(role='user', content=message)), stream=stream), auto_unbox=TRUE)
  curl::handle_setopt(h, postfields=body)
  curl::handle_setopt(h, customrequest='POST')

  if (!stream) {
    res <- curl::curl_fetch_memory(url, handle=h)
    txt <- rawToChar(res$content)
    obj <- tryCatch(jsonlite::fromJSON(txt), error=function(e) NULL)
    if (!is.null(obj$response)) on_chunk(list(text=obj$response, done=TRUE)) else on_chunk(list(text=txt, done=TRUE))
    return(invisible(NULL))
  }

  buffer <- ""
  cb <- function(data) {
    buffer <<- paste0(buffer, rawToChar(data))
    repeat {
      nl <- regexpr("\n", buffer)
      if (nl == -1) break
      line <- trimws(substr(buffer, 1, nl-1))
      buffer <<- substr(buffer, nl+1, nchar(buffer))
      if (nchar(line) == 0) next
      if (startsWith(line, 'data: ')) {
        json <- trimws(sub('^data: ', '', line))
        if (json == '' || json == '[DONE]') { on_chunk(list(text='', done=TRUE)); next }
        obj <- tryCatch(jsonlite::fromJSON(json), error=function(e) NULL)
        if (!is.null(obj) && !is.null(obj$response)) {
          done <- isTRUE(obj$done)
          on_chunk(list(text=obj$response, done=done))
          if (done) on_chunk(list(text='', done=TRUE))
        } else {
          on_chunk(list(text=json, done=FALSE))
        }
      } else on_chunk(list(text=line, done=FALSE))
    }
    TRUE
  }
  curl::curl_fetch_stream(url, cb, handle=h)
  invisible(NULL)
}

