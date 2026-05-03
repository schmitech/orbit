# Montréal Police - Actes Criminels (SPVM)

Criminal incidents reported by the Service de police de la Ville de Montréal (SPVM).

**Source:** [Données ouvertes Montréal - Actes criminels](https://donnees.montreal.ca/ville-de-montreal/actes-criminels)

## Dataset overview

| Field | Details |
|-------|---------|
| Records | ~345,000 (growing daily) |
| Period | 2015–present |
| Language | French |
| Updates | Daily |
| Categories | Vol de véhicule à moteur, Vol dans/sur véhicule, Introduction, Méfait, Vols qualifiés, Infractions entrainant la mort |

## Files

| File | Purpose |
|------|---------|
| `actes-criminels.csv` | Raw CSV downloaded from source |
| `actes-criminels-geo.csv` | Geocoded CSV with `arrondissement` column added |
| `limites-administratives-agglomeration.geojson` | Arrondissement boundary polygons ([source](https://donnees.montreal.ca/dataset/9797a946-9da8-41ec-8815-f6b276dec7e9/resource/e18bfd07-edc8-4ce8-8a5a-3b617662a794/download/limites-administratives-agglomeration.geojson)) |
| `pdq_arrondissement_map.yaml` | PDQ → arrondissement fallback mapping |
| `actes_criminels.sql` | DuckDB table schema + indexes |
| `import_config.yaml` | CSV → DuckDB column mapping |
| `actes_criminels_domain.yaml` | Domain configuration (vocabulary, entities, fields) |
| `actes_criminels_templates.yaml` | SQL query templates for natural language matching |
| `montreal-actes-criminels-assistant-prompt.md` | LLM system prompt (French) |
| `montreal-actes-criminels-agent-intro.md` | Chat welcome message (French) |
| `actes_criminels.duckdb` | Generated DuckDB database |

## Daily update workflow

The source CSV is updated daily. Run these 3 commands to update:

### Step 1: Download fresh CSV

Download the latest CSV from the data portal and replace the existing file:

```bash
# Download from: https://donnees.montreal.ca/ville-de-montreal/actes-criminels
# Save as: orbit-templates/montreal/actes-criminels.csv
```

### Step 2: Geocode new rows (incremental)

The `--append` flag only geocodes rows added since the last run. This is fast
(seconds for a few hundred new rows vs minutes for the full dataset).

```bash
cd /path/to/csv-files
source .venv/bin/activate

python3 utils/duckdb/geocode_csv.py \
  --csv orbit-templates/montreal/actes-criminels.csv \
  --geojson orbit-templates/montreal/limites-administratives-agglomeration.geojson \
  --lat LATITUDE --lon LONGITUDE \
  --property NOM \
  --output-column arrondissement \
  --output orbit-templates/montreal/actes-criminels-geo.csv \
  --fallback-map orbit-templates/montreal/pdq_arrondissement_map.yaml \
  --fallback-column PDQ \
  --append
```

If you need to re-geocode everything from scratch (e.g., after fixing the fallback map),
remove the `--append` flag.

### Step 3: Regenerate DuckDB

This rebuilds the DuckDB from the full geocoded CSV (~2 seconds for 345K rows):

```bash
python3 utils/duckdb/generate_duckdbs.py --clean montreal-actes-criminels
```

### All-in-one

```bash
cd /path/to/csv-files
source .venv/bin/activate

# 1. Download fresh CSV (manual or scripted)
# 2. Geocode delta
python3 utils/duckdb/geocode_csv.py \
  --csv orbit-templates/montreal/actes-criminels.csv \
  --geojson orbit-templates/montreal/limites-administratives-agglomeration.geojson \
  --lat LATITUDE --lon LONGITUDE \
  --property NOM \
  --output-column arrondissement \
  --output orbit-templates/montreal/actes-criminels-geo.csv \
  --fallback-map orbit-templates/montreal/pdq_arrondissement_map.yaml \
  --fallback-column PDQ \
  --append

# 3. Rebuild DuckDB
python3 utils/duckdb/generate_duckdbs.py --clean montreal-actes-criminels
```

## First-time setup

If setting up from scratch (no `-geo.csv` exists yet):

```bash
# Install dependencies
source .venv/bin/activate
pip install shapely geopandas

# Full geocode (takes ~5 minutes for 345K rows)
python3 utils/duckdb/geocode_csv.py \
  --csv orbit-templates/montreal/actes-criminels.csv \
  --geojson-url "https://donnees.montreal.ca/dataset/9797a946-9da8-41ec-8815-f6b276dec7e9/resource/e18bfd07-edc8-4ce8-8a5a-3b617662a794/download/limites-administratives-agglomeration.geojson" \
  --lat LATITUDE --lon LONGITUDE \
  --property NOM \
  --output-column arrondissement \
  --output orbit-templates/montreal/actes-criminels-geo.csv \
  --fallback-map orbit-templates/montreal/pdq_arrondissement_map.yaml \
  --fallback-column PDQ

# Generate DuckDB
python3 utils/duckdb/generate_duckdbs.py --clean montreal-actes-criminels
```

The GeoJSON boundary file is cached in `duckdb/.cache/` after the first download.

## Notes

- The geocoded CSV (`actes-criminels-geo.csv`) is the one referenced by `csv_to_duckdb.yaml`, not the raw CSV
- The `--append` flag assumes new rows are appended to the end of the source CSV (which is the case for this dataset)
- If rows in the middle of the CSV change (unlikely for this dataset), use full mode without `--append`
- 6 out of ~345K rows have no coordinates and no PDQ match — these get `arrondissement = 'Inconnu'`
- The PDQ fallback map covers the 32 most common police stations; coordinates cover the rest
