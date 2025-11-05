
# AI Log Correlation and Analysis Test Scenarios

This markdown file contains a curated list of questions and prompts designed to test AI reasoning, retrieval, and correlation capabilities using the provided **application/system logs (JSON)** and **load balancer logs (.log)**.

---

## 🔗 Correlation & Cross-File Matching

1. Identify all requests that share the same `correlation_id` between `app_system_logs.json` and `edge_load_balancer.log`.  
   → Expected: Matching timestamps, same correlation ID, but possibly different latency details.

2. For a given `correlation_id`, compare the latency (`latency_ms` from app logs vs. `request_time` / `upstream_response_time` from LB logs).  
   → Determine which service or layer contributed the most to total latency.

3. Detect orphaned records — correlation IDs that exist **only** in one file but not the other.  
   → Highlight whether missing entries are from the app layer or LB layer.

4. Check if any app log entries show HTTP 5xx status but have **no corresponding** load balancer request with the same correlation ID.

5. Aggregate request counts per service (`auth-service`, `orders-service`, etc.) and correlate the top 3 slowest transactions across both sources.

---

## ⏱️ Performance & Latency Analysis

6. Find correlation IDs where the total LB `upstream_response_time` exceeds 2 seconds but the application’s own `latency_ms` is below 500ms.  
   → Investigate potential upstream or network latency issues.

7. Identify the top 5 requests by total `latency_ms` and show their LB counterpart timings and HTTP statuses.

8. Detect if LB request timestamps precede application timestamps by more than 5 seconds.  
   → This may suggest clock drift or delayed ingestion.

9. Compute average, median, and P95 latency across both files for successful (`status=200`) transactions.

---

## ⚠️ Error & Exception Investigation

10. List all correlation IDs where the app log contains `level=ERROR` or message includes `"db_timeout"`, `"upstream_error"`, or `"null_pointer_exception"`.

11. Cross-check these error IDs in the LB log — do they show elevated response times, 5xx statuses, or retries?

12. Detect if any repeated correlation IDs appear more than once in the app logs — potential retry or duplicate processing.

13. For `500` or `504` statuses in LB logs, check if the corresponding app log entry has a matching exception stacktrace.

14. Correlate user agents (`user_agent`) from app logs with LB logs for the same correlation IDs to confirm consistency.

---

## 🌐 Network & Proxy Behavior

15. Identify patterns where multiple client IPs (`x_forwarded_for`) map to the same `correlation_id`.  
   → Possible proxy hops or load balancer fan-out.

16. Group requests by `host` and summarize average request and upstream response times per backend (`upstream_addr`).

17. Check if any upstream servers (e.g., `10.10.3.21:8080`) consistently return higher latency or 5xx errors.

18. Detect whether TLS version (`tls`) differs across correlated LB entries (should consistently show `TLSv1.3`).

---

## 🧭 User & API Behavior

19. Find the most active users (based on `user_id` field) across all services.  
   → Then correlate their traffic to LB logs to see which paths and methods dominate.

20. Identify any correlation ID linked to multiple user IDs — possible token leakage or session reuse.

21. For `POST` operations on `/api/v1/orders` or `/api/v1/payments`, determine the average app vs. LB latency ratio.

22. Analyze failed login attempts (`/api/v1/login` with 4xx/5xx) and their source IPs — any repeated attackers?

---

## 🔍 Advanced AI Reasoning & Anomaly Detection

23. Detect correlation IDs with unusually long latency relative to their peers (outliers).  
   → Compare per-service latency distributions.

24. Identify correlation IDs with mismatched HTTP status codes between LB and app logs (e.g., LB 200 but app 500).

25. Cluster correlation IDs by user agent and response time patterns — find anomalies in latency or routing behavior.

26. Predict potential service degradation based on patterns in latency increase and error frequency over time.

27. Detect temporal bursts of errors or latency spikes across correlation IDs — e.g., network congestion windows.

28. Infer potential dependency issues (e.g., spikes in `payments-service` errors correlate with upstream LB delays).

---

## 🧩 Example Composite Queries

- “Find all 5xx correlation IDs where app latency > 1000ms and LB upstream time > 1.5s.”  
- “Which upstream_addr had the most failed responses (≥500) within a 10-minute window?”  
- “List correlation IDs where app reported `null_pointer_exception` but LB log shows status=200.”  
- “Compute overall error rate and latency distribution by service, method, and HTTP status.”

---

**Dataset Files:**  
- `app_system_logs.json` (application & system events)  
- `edge_load_balancer.log` (network/load balancer logs)  

**Correlation Key:** `correlation_id`  

**Time Range:** ~2025-01-15T14:00Z ± 60 minutes  
**Entries:** ~90 total (40 shared correlation IDs; 6 orphaned per side)

---

These prompts help evaluate if an AI system can reason across structured (JSON) and semi-structured (log text) data, align entries via correlation IDs, and extract actionable insights involving latency, status codes, and network dependencies.
