(ns example
  (:require [orbit.api-client :as orbit]))

(defn -main []
  (let [url (or (System/getenv "ORBIT_URL") "http://localhost:3000")]
    (orbit/stream-chat url nil nil "Hello from Clojure!" true
                       (fn [{:keys [text done]}]
                         (print text)
                         (when done (println))))))

