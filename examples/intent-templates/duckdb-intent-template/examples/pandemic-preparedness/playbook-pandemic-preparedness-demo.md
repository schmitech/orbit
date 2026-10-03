# Manual/Integration Check: Canadian Pandemic Preparedness Demo Adapter

Steps to verify the `intent-duckdb-pandemic-preparedness` adapter end-to-end
before the CP2H demo — build the data, start the server, and exercise each
template category with `curl`.

## 1. Build the data

The two source CSVs and the pre-built `.duckdb` file are already committed, so
this step is only needed if you want to regenerate from scratch.

```bash
cd examples/intent-templates/duckdb-intent-template/examples/pandemic-preparedness
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python generate_pandemic_preparedness_data.py
```

**Expected:** prints `facilities=60 trials=220` and rewrites
`biomanufacturing_facilities.csv` / `clinical_trials.csv`.

```bash
cd ../../../../../utils/duckdb
EX=../../examples/intent-templates/duckdb-intent-template/examples/pandemic-preparedness
/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python csv_to_duckdb.py "$EX/biomanufacturing_facilities.csv" \
  --schema "$EX/biomanufacturing_facilities.sql" --output "$EX/pandemic_preparedness.duckdb" \
  --table biomanufacturing_facilities --clean

/Users/remsyschmilinsky/Downloads/orbit/venv/bin/python csv_to_duckdb.py "$EX/clinical_trials.csv" \
  --schema "$EX/clinical_trials.sql" --output "$EX/pandemic_preparedness.duckdb" \
  --table clinical_trials --clean
```

**Expected:** both commands print `Database created: .../pandemic_preparedness.duckdb`
with `Total Records: 60` and `Total Records: 220` respectively.

Spot-check row counts and the join:

```bash
duckdb "$EX/pandemic_preparedness.duckdb" "
  SELECT (SELECT COUNT(*) FROM biomanufacturing_facilities) AS facilities,
         (SELECT COUNT(*) FROM clinical_trials) AS trials;
"
```

**Expected:** `facilities=60`, `trials=220`.

## 2. Start the server and create an API key

```bash
python3 server/main.py
# in another shell:
./bin/orbit.sh key create --adapter intent-duckdb-pandemic-preparedness --name "CP2H demo"
```

```bash
export ORBIT_KEY=<the-key-just-created>
```

**Expected:** server logs show `intent-duckdb-pandemic-preparedness` loading
without error (no missing-file or schema-mismatch warnings referencing
`pandemic_preparedness`).

## 3. Overview / counts

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "Give me an overview of pandemic preparedness readiness"}' | jq
```

**Expected:** resolves to `preparedness_overview`, a single summary row with
`total_facilities=60`, `total_trials=220`, plus operational/GMP/active/Phase III counts.

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "How many biomanufacturing facilities do we have?"}' | jq
```

**Expected:** `total_facility_count` → `total_facilities=60`.

## 4. Breakdowns (province / facility type / phase / pathogen)

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "Show me facilities by province"}' | jq
```

**Expected:** `facilities_by_province` → a table with one row per province
(ON highest, ~59 facility-adjacent trial count from the earlier join check is
unrelated — this is facility counts, so expect ON/BC/QC near the top).

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "What are we researching for coronavirus vs influenza?"}' | jq
```

**Expected:** `trials_by_pathogen` → table with `pathogen_target`, `trial_count`,
`active_count`, `phase_3_count` columns.

## 5. Filtered lookups

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "Show me GMP-certified operational facilities"}' | jq
```

**Expected:** `operational_gmp_certified_facilities` → table where every row has
`status=operational` and `gmp_certified=true`.

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "What clinical trials are in Phase III for coronavirus?"}' | jq
```

**Expected:** `trials_for_pathogen_and_phase` → table where every row has
`trial_phase=Phase III` and `pathogen_target` containing "coronavirus".

## 6. Facility ↔ trial joins

```bash
curl -s -X POST http://localhost:3000/v1/chat \
  -H "Content-Type: application/json" -H "X-API-Key: $ORBIT_KEY" \
  -d '{"message": "Which facilities are hosting mpox vaccine trials?"}' | jq
```

**Expected:** `facilities_hosting_pathogen_trials` → table of facilities, each
with a `trial_count >= 1`. Cross-check with:

```bash
duckdb examples/intent-templates/duckdb-intent-template/examples/pandemic-preparedness/pandemic_preparedness.duckdb \
  "SELECT DISTINCT f.facility_name FROM biomanufacturing_facilities f
   JOIN clinical_trials t ON t.facility_id = f.facility_id
   WHERE t.pathogen_target = 'mpox';"
```

the two result sets should match (modulo the `LIMIT`/ordering).

## 7. Confirm adapter registration

```bash
grep -n "pandemic-preparedness" config/adapters.yaml
grep -n "intent-duckdb-pandemic-preparedness" config/adapters/pandemic-preparedness.yaml
```

**Expected:** both greps return matches. If an admin "list adapters" endpoint
is configured, confirm `intent-duckdb-pandemic-preparedness` appears there too.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Server fails to start or logs an error mentioning `pandemic_preparedness` | `config/adapters/pandemic-preparedness.yaml` not imported — check `- "adapters/pandemic-preparedness.yaml"` is present in `config/adapters.yaml`'s `import:` list. |
| "No matching template" / fallback response for every question | `confidence_threshold` too high for your embedding model, or `template_library_path` points to a stale file — verify the path in `config/adapters/pandemic-preparedness.yaml` matches the actual file location. |
| Results are empty or counts don't match this doc (60 / 220) | `database:` path is stale or the `.duckdb` file wasn't regenerated after a schema change — rebuild per step 1. |
| Join templates return 0 rows | `facility_id` values in `clinical_trials.csv` don't overlap with `biomanufacturing_facilities.csv` — only possible after manual editing of the CSVs; regenerate both together with the same script run (they share facility IDs by construction). |

## Regression check

```bash
venv/bin/python -m pytest server/tests/ -m unit
```

**Expected:** no new failures — this adapter only adds new files/config, it
doesn't change any existing adapter or retriever code.
