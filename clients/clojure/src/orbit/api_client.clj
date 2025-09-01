(ns orbit.api-client
  (:require [org.httpkit.client :as http])
  (:import [java.io BufferedReader InputStreamReader]))

(defn endpoint [api-url]
  (if (.endsWith api-url "/v1/chat") api-url (str (.replaceAll api-url "/+$" "") "/v1/chat")))

(defn stream-chat
  "Streams chat. on-chunk is called with {:text string :done boolean}."
  [api-url api-key session-id message stream on-chunk]
  (let [req {:url (endpoint api-url)
             :method :post
             :headers (cond-> {"Content-Type" "application/json"
                               "Accept" (if stream "text/event-stream" "application/json")
                               "X-Request-ID" (str (System/currentTimeMillis))}
                         api-key (assoc "X-API-Key" api-key)
                         session-id (assoc "X-Session-ID" session-id))
             :body (str "{\"messages\":[{\"role\":\"user\",\"content\":\""
                        (.replace (.replace (.replace message "\\" "\\\\") "\"" "\\\"") "\n" "\\n")
                        "\"}],\"stream\":" stream "}")
             :as :stream}]
    (http/request req
                  (fn [{:keys [status body error]}]
                    (when error (throw (ex-info "HTTP error" {:error error})))
                    (when (and status (<= 200 status 299))
                      (with-open [r (BufferedReader. (InputStreamReader. ^java.io.InputStream body))]
                        (loop []
                          (when-let [line (.readLine r)]
                            (let [line (.trim line)]
                              (when (seq line)
                                (if (.startsWith line "data: ")
                                  (let [json (.trim (subs line 6))]
                                    (if (or (= json "") (= json "[DONE]"))
                                      (on-chunk {:text "" :done true})
                                      (if (and (.contains json "\"response\"") (.contains json "\"done\":true"))
                                        (do (on-chunk {:text (subs json (inc (.indexOf json "\"response\":"))
                                                                     (.indexOf json "\"" (inc (.indexOf json "\"response\":"))))
                                                       :done true})
                                            (on-chunk {:text "" :done true}))
                                        (if (.contains json "\"response\"")
                                          (on-chunk {:text (subs json (inc (.indexOf json "\"response\":"))
                                                                 (.indexOf json "\"" (inc (.indexOf json "\"response\":"))))
                                                     :done false})
                                          (on-chunk {:text json :done false}))))
                                  (on-chunk {:text line :done false}))))
                            (recur))))))))

