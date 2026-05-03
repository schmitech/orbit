# Edmonton Police Service — Occurrences

Police-reported occurrences from the Edmonton Police Service (EPS) Community Safety Data Portal.

**Source:** [Edmonton Police Service — Open Data](https://data.edmonton.ca/)

## Dataset overview

| Field | Details |
|-------|---------|
| Records | ~256,000 (growing daily) |
| Period | 2023–present |
| Language | English |
| Updates | Daily (rolling 30-day file) |
| Categories | Disorder, Drugs, Non-Violent, Other, Traffic, Violent, Weapons |
| Location | Street intersections (e.g., 93 ST/122 AV) |

## Files

| File | Purpose |
|------|---------|
| `Historic_Occurrences_CSDP_2_view_*.csv` | Historical data — 2023 |
| `Historic_Occurrences_CSDP_2023View_*.csv` | Historical data — 2024 |
| `Historic_Occurrences_CSDP_2022_View_*.csv` | Historical data — 2025 |
| `EPS_OCC_30DAY_*.csv` | Rolling 30-day data (updated daily) |
| `edmonton-occurrences.csv` | Merged CSV (all years combined, x/y coordinates dropped) |
| `occurrences.sql` | DuckDB table schema + indexes |
| `import_config.yaml` | CSV → DuckDB column mapping |
| `occurrences_domain.yaml` | Domain configuration (vocabulary, entities, fields) |
| `occurrences_templates.yaml` | SQL query templates for natural language matching |
| `edmonton-occurrences-assistant-prompt.md` | LLM system prompt |
| `edmonton-occurrences-agent-intro.md` | Chat welcome message |
| `occurrences.duckdb` | Generated DuckDB database |
| `data-dictionary.md` | Glossary of occurrence types |

## Data structure

The source CSVs have 8 columns. During the merge step, `OBJECTID`, `x`, and `y` are dropped (coordinates are in inconsistent projections across files). A `Year` column is extracted from `Date Reported`.

**Merged columns:** `Occurrence_Category`, `Occurrence_Group`, `Occurrence_Type_Group`, `Intersection`, `Date_Reported`, `Year`

**Note:** The historical files have `OBJECTID` as the first column, while the rolling EPS file has `Occurrence_Category` first. The merge script handles this automatically via column-name-based reading.

## Daily update workflow

The rolling 30-day file (`EPS_OCC_30DAY_*.csv`) is updated daily. Historical files are static yearly exports.

### Step 1: Download fresh EPS CSV

Download the latest rolling 30-day CSV from the data portal and replace the existing `EPS_OCC_30DAY_*.csv` file.

### Step 2: Merge all CSVs

Merge the 4 source files into a single `edmonton-occurrences.csv`, dropping coordinates and adding a year column:

```bash
cd /path/to/csv-files

python3 -c "
import csv, glob, os

base = 'orbit-templates/edmonton-police'
files = sorted(glob.glob(f'{base}/Historic_*.csv')) + sorted(glob.glob(f'{base}/EPS_*.csv'))
keep_cols = ['Occurrence_Category','Occurrence_Group','Occurrence_Type_Group','Intersection','Date Reported']
out_cols = ['Occurrence_Category','Occurrence_Group','Occurrence_Type_Group','Intersection','Date_Reported','Year']

total = 0
with open(f'{base}/edmonton-occurrences.csv', 'w', newline='') as out:
    writer = csv.writer(out)
    writer.writerow(out_cols)
    for f in files:
        with open(f, 'r', encoding='utf-8-sig') as inp:
            reader = csv.DictReader(inp)
            reader.fieldnames = [h.strip() for h in reader.fieldnames]
            for row in reader:
                date_val = row['Date Reported'].strip()
                year = date_val[:4] if date_val else ''
                writer.writerow([row[c].strip() for c in keep_cols] + [year])
                total += 1
print(f'Merged {total} rows')
"
```

### Step 3: Regenerate DuckDB

```bash
source .venv/bin/activate
python3 utils/duckdb/generate_duckdbs.py edmonton-occurrences --clean
```

### All-in-one

```bash
cd /path/to/csv-files
source .venv/bin/activate

# 1. Download fresh EPS CSV (manual or scripted)
# 2. Merge
python3 -c "
import csv, glob, os
base = 'orbit-templates/edmonton-police'
files = sorted(glob.glob(f'{base}/Historic_*.csv')) + sorted(glob.glob(f'{base}/EPS_*.csv'))
keep_cols = ['Occurrence_Category','Occurrence_Group','Occurrence_Type_Group','Intersection','Date Reported']
out_cols = ['Occurrence_Category','Occurrence_Group','Occurrence_Type_Group','Intersection','Date_Reported','Year']
total = 0
with open(f'{base}/edmonton-occurrences.csv', 'w', newline='') as out:
    writer = csv.writer(out)
    writer.writerow(out_cols)
    for f in files:
        with open(f, 'r', encoding='utf-8-sig') as inp:
            reader = csv.DictReader(inp)
            reader.fieldnames = [h.strip() for h in reader.fieldnames]
            for row in reader:
                date_val = row['Date Reported'].strip()
                year = date_val[:4] if date_val else ''
                writer.writerow([row[c].strip() for c in keep_cols] + [year])
                total += 1
print(f'Merged {total} rows')
"

# 3. Rebuild DuckDB
python3 utils/duckdb/generate_duckdbs.py edmonton-occurrences --clean
```

## Notes

- The merge takes ~1 second for 256K rows; no incremental mode needed
- Full DuckDB rebuild takes ~2 seconds
- Coordinates were dropped because historical files use a local projection while the rolling file uses Web Mercator — they are inconsistent and not needed since `Intersection` provides location data
- Historical files are released annually; when a new year's historical file is published, place it in this folder with the `Historic_` prefix and the merge will pick it up automatically
