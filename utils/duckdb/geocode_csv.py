#!/usr/bin/env python3
"""
Reverse-geocode CSV coordinates to neighbourhood/borough names using a GeoJSON boundary file.

This is a reusable pre-processing step for datasets that contain lat/long coordinates
but no neighbourhood or borough names. It performs point-in-polygon lookups against
a GeoJSON boundary file and adds a new column to the CSV.

Modes:
    Full (default):  Process the entire input CSV and write a new output CSV.
    Append (--append): Only geocode rows that are new since the last run.
                       Compares input CSV row count to existing output CSV row count,
                       skips already-processed rows, and appends only the delta.

Usage:
    # Full geocode:
    python geocode_csv.py --csv <input.csv> --geojson <boundaries.geojson> \
        --lat LATITUDE --lon LONGITUDE \
        --property NOM \
        --output-column arrondissement \
        --output <output.csv>

    # Incremental append (daily updates):
    python geocode_csv.py --csv <input.csv> --geojson <boundaries.geojson> \
        --lat LATITUDE --lon LONGITUDE \
        --property NOM \
        --output-column arrondissement \
        --output <output.csv> \
        --append

Arguments:
    --csv              Input CSV file path
    --geojson          Local GeoJSON boundary file
    --geojson-url      URL to download GeoJSON from (alternative to --geojson)
    --lat              CSV column name for latitude
    --lon              CSV column name for longitude
    --property         GeoJSON property name to extract (e.g., NOM, name, ARROND)
    --output-column    Name for the new column added to the CSV (default: neighbourhood)
    --output           Output CSV file path (default: overwrites input)
    --append           Incremental mode: only geocode new rows appended to the source CSV
    --fallback-map     Optional YAML file mapping a CSV column to the property value
                       (e.g., PDQ number -> arrondissement) for rows with missing coordinates
    --fallback-column  CSV column to use for fallback mapping (e.g., PDQ)
    --encoding         CSV encoding (default: utf-8)
"""

import argparse
import csv
import os
import sys
import time

import requests


def download_geojson(url, cache_dir=None):
    """Download GeoJSON from URL, caching locally."""
    if cache_dir is None:
        cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)

    filename = url.split("/")[-1].split("?")[0]
    if not filename.endswith(".geojson") and not filename.endswith(".json"):
        filename = "boundaries.geojson"
    cache_path = os.path.join(cache_dir, filename)

    if os.path.exists(cache_path):
        print(f"  Using cached GeoJSON: {cache_path}")
        return cache_path

    print(f"  Downloading GeoJSON from {url}...")
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(cache_path, "wb") as f:
        f.write(resp.content)
    print(f"  Saved to {cache_path} ({len(resp.content) / 1024:.0f} KB)")
    return cache_path


def build_spatial_index(geojson_path, property_name):
    """Load GeoJSON and build a spatial index for point-in-polygon lookups."""
    import geopandas as gpd

    print(f"  Loading boundaries from {geojson_path}...")
    gdf = gpd.read_file(geojson_path)

    if property_name not in gdf.columns:
        available = [c for c in gdf.columns if c != "geometry"]
        print(f"  ERROR: Property '{property_name}' not found. Available: {available}")
        sys.exit(1)

    # Ensure WGS84
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    print(f"  Loaded {len(gdf)} boundary polygons")
    print(f"  Property '{property_name}' values: {sorted(gdf[property_name].unique())[:10]}...")
    return gdf, property_name


def geocode_point(lon, lat, gdf, property_name):
    """Find which polygon contains the given point."""
    from shapely.geometry import Point

    if lon is None or lat is None:
        return None

    try:
        lon = float(lon)
        lat = float(lat)
    except (ValueError, TypeError):
        return None

    if lon == 0 or lat == 0:
        return None

    point = Point(lon, lat)
    mask = gdf.geometry.contains(point)
    matches = gdf[mask]

    if len(matches) > 0:
        return matches.iloc[0][property_name]
    return None


def load_fallback_map(fallback_file):
    """Load a YAML fallback mapping file."""
    import yaml

    with open(fallback_file, "r") as f:
        data = yaml.safe_load(f)
    # Convert keys to strings for matching
    return {str(k): v for k, v in data.items()}


def main():
    parser = argparse.ArgumentParser(description="Reverse-geocode CSV coordinates to neighbourhood names")
    parser.add_argument("--csv", required=True, help="Input CSV file")
    parser.add_argument("--geojson", help="Local GeoJSON boundary file")
    parser.add_argument("--geojson-url", help="URL to download GeoJSON from")
    parser.add_argument("--lat", required=True, help="CSV column name for latitude")
    parser.add_argument("--lon", required=True, help="CSV column name for longitude")
    parser.add_argument("--property", required=True, help="GeoJSON property to extract")
    parser.add_argument("--output-column", default="neighbourhood", help="New column name (default: neighbourhood)")
    parser.add_argument("--output", help="Output CSV path (default: overwrites input)")
    parser.add_argument("--append", action="store_true", help="Incremental mode: only geocode new rows")
    parser.add_argument("--fallback-map", help="YAML file mapping a column value to property")
    parser.add_argument("--fallback-column", help="CSV column for fallback lookup")
    parser.add_argument("--encoding", default="utf-8", help="CSV encoding")
    args = parser.parse_args()

    if not args.geojson and not args.geojson_url:
        print("ERROR: Must provide either --geojson or --geojson-url")
        sys.exit(1)

    # Resolve GeoJSON path
    if args.geojson_url:
        geojson_path = download_geojson(args.geojson_url)
    else:
        geojson_path = args.geojson

    # Build spatial index
    gdf, prop = build_spatial_index(geojson_path, args.property)

    # Load fallback map if provided
    fallback_map = None
    if args.fallback_map:
        fallback_map = load_fallback_map(args.fallback_map)
        print(f"  Loaded fallback map: {len(fallback_map)} entries")

    # Process CSV
    output_path = args.output or args.csv

    # Determine how many rows to skip in append mode
    skip_rows = 0
    if args.append and os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            existing_lines = sum(1 for _ in f) - 1  # subtract header
        skip_rows = existing_lines
        print(f"\n  Append mode: output has {existing_lines:,} existing rows, will skip those")

    # Read input CSV
    with open(args.csv, "r", encoding=args.encoding, newline="") as infile:
        content = infile.read()
        if content.startswith("\ufeff"):
            content = content[1:]

    reader = csv.DictReader(content.splitlines())
    input_fieldnames = list(reader.fieldnames)
    fieldnames = input_fieldnames + [args.output_column]

    # Count total input rows to determine if there's anything new
    all_rows = list(reader)
    total_input = len(all_rows)

    if args.append and skip_rows >= total_input:
        print(f"  No new rows to process ({total_input:,} input rows, {skip_rows:,} already geocoded)")
        return

    rows_to_process = all_rows[skip_rows:] if args.append else all_rows
    new_count = len(rows_to_process)

    if args.append:
        print(f"  Input has {total_input:,} rows, {new_count:,} new rows to geocode")

    # Choose write mode: append to existing or write fresh
    if args.append and skip_rows > 0:
        outfile_mode = "a"
        write_header = False
    else:
        outfile_mode = "w"
        write_header = True

    # Use temp file for full mode, direct append for append mode
    if args.append and skip_rows > 0:
        write_path = output_path
    else:
        write_path = output_path + ".tmp"

    print(f"\n  Processing {args.csv} ({'append' if args.append else 'full'} mode)...")
    start = time.time()

    total = 0
    geocoded = 0
    fallback_used = 0
    missing = 0

    with open(write_path, outfile_mode, encoding="utf-8", newline="") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        if write_header:
            writer.writeheader()

        for row in rows_to_process:
            total += 1

            # Try geocoding
            lon = row.get(args.lon, "").strip().strip('"')
            lat = row.get(args.lat, "").strip().strip('"')

            result = geocode_point(lon, lat, gdf, prop)

            if result:
                geocoded += 1
            elif fallback_map and args.fallback_column:
                key = str(row.get(args.fallback_column, "")).strip().strip('"')
                result = fallback_map.get(key)
                if result:
                    fallback_used += 1

            if not result:
                missing += 1
                result = "Inconnu"

            row[args.output_column] = result
            writer.writerow(row)

            if total % 50000 == 0:
                elapsed = time.time() - start
                rate = total / elapsed
                print(f"    {total:,} rows processed ({rate:.0f} rows/sec) - geocoded: {geocoded:,}, fallback: {fallback_used:,}, missing: {missing:,}")

    # Replace original with temp (only in full mode)
    if write_path != output_path:
        os.replace(write_path, output_path)

    elapsed = time.time() - start
    if total > 0:
        print(f"\n  Completed in {elapsed:.1f}s ({total / elapsed:.0f} rows/sec)")
        print(f"  New rows:  {total:,}")
        print(f"  Geocoded:  {geocoded:,} ({geocoded * 100 / total:.1f}%)")
        if fallback_map:
            print(f"  Fallback:  {fallback_used:,} ({fallback_used * 100 / total:.1f}%)")
        print(f"  Missing:   {missing:,} ({missing * 100 / total:.1f}%)")
        if args.append and skip_rows > 0:
            print(f"  Total in output: {skip_rows + total:,} rows")
    print(f"  Output:    {output_path}")


if __name__ == "__main__":
    main()
