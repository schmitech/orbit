# Canadian Pandemic Preparedness Demo

A DuckDB intent-SQL retrieval adapter showcasing biomanufacturing capacity and
clinical trial readiness tracking — built for a demo with the Canadian Pandemic
Preparedness Hub (CP2H, University of Ottawa / McMaster University).

**All data in this example is synthetic**, generated with `faker` plus a curated
list of real Canadian cities/provinces and academic institutions for realism.
It is illustrative only — not real facility or trial data.

## Dataset

Two tables, joined by `facility_id`:

- `biomanufacturing_facilities` (60 rows) — facility name, organization, province,
  city, facility type (vaccine, viral_vector, cell_therapy, antibody, mRNA),
  production capacity, operational status, GMP certification, partner network.
- `clinical_trials` (220 rows) — candidate name, pathogen target, trial phase,
  sponsor, facility, start date, status, enrollment count.

See `pandemic_preparedness.sql` for the full schema (reference copy).

## Files

| File | Purpose |
|---|---|
| `biomanufacturing_facilities.csv`, `clinical_trials.csv` | Synthetic source data |
| `biomanufacturing_facilities.sql`, `clinical_trials.sql` | Per-table DDL used by the loader |
| `pandemic_preparedness.sql` | Combined schema (reference only) |
| `pandemic_preparedness.duckdb` | Pre-built database (both tables) |
| `pandemic_preparedness_domain.yaml` | Domain/entity definitions for intent matching |
| `pandemic_preparedness_templates.yaml` | 15 intent templates (counts, breakdowns, filters, joins) |
| `demo-questions.md` | Sample NL questions for the live demo |
| `playbook-pandemic-preparedness-demo.md` | Manual verification playbook |

## Regenerating the data

```bash
# From this directory, with the venv python:
python generate_pandemic_preparedness_data.py   # regenerates the two CSVs (seeded, deterministic)

# From utils/duckdb/, load each table into the shared .duckdb file:
cd ../../../../../utils/duckdb
EX=../../examples/intent-templates/duckdb-intent-template/examples/pandemic-preparedness
python csv_to_duckdb.py "$EX/biomanufacturing_facilities.csv" \
  --schema "$EX/biomanufacturing_facilities.sql" \
  --output "$EX/pandemic_preparedness.duckdb" \
  --table biomanufacturing_facilities --clean

python csv_to_duckdb.py "$EX/clinical_trials.csv" \
  --schema "$EX/clinical_trials.sql" \
  --output "$EX/pandemic_preparedness.duckdb" \
  --table clinical_trials --clean
```

## Registration

Registered as the `intent-duckdb-pandemic-preparedness` adapter in
`config/adapters/pandemic-preparedness.yaml`, imported from `config/adapters.yaml`.

## Verification

See `playbook-pandemic-preparedness-demo.md` for a step-by-step manual check.
