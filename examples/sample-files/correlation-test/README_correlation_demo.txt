
Correlation Demo Files
======================
Files:
- app_system_logs.json  (JSON array; size: 46 records)
- edge_load_balancer.txt (text; size: 46 lines)

How to correlate:
- Key: correlation_id (present in both files). In LB logs, it appears as correlation_id=...; in app logs, it's a JSON field.
- Timestamps are ISO8601 (Z) in JSON; LB logs use common log format date but aligned to the same minute for shared entries.

Example correlation_id to try:
- cd38ace8-0e48-45e1-bde2-697efb23d30b
- 49e93c41-edb4-481c-bd2e-40c2b3b134e7
- bebec171-4125-44ae-b3ce-99c71d7da3e4
