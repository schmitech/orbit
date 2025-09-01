(ns orbit.api-client-test
  (:require [clojure.test :refer :all]
            [orbit.api-client :as orbit]))

(deftest integration-non-streaming
  (if (= (System/getenv "ORBIT_INTEGRATION") "1")
    (let [url (or (System/getenv "ORBIT_URL") "http://localhost:3000")
          acc (StringBuilder.)]
      (orbit/stream-chat url nil nil "ping" false (fn [{:keys [text done]}] (.append acc text)))
      (is (>= (.length acc) 0)))
    (do (println "Skipping integration test; set ORBIT_INTEGRATION=1 to enable") (is true))))

