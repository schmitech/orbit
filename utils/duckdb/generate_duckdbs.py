#!/usr/bin/env python3
"""
Generate DuckDB Databases from YAML Configuration
"""

import argparse
import yaml
import sys
import subprocess
import os

def load_config(config_path):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def generate_database(target_name, config, clean=False):
    print("----------------------------------------")
    print(f"Generating: {config['description']} ({target_name})")
    print(f"  CSV:    {config['csv_path']}")
    print(f"  Schema: {config['schema_path']}")
    print(f"  Output: {config['output_path']}")
    if config.get('url'):
        print(f"  URL:    {config['url']}")
    print("")

    # Only check if CSV exists if we aren't downloading it
    if not config.get('url') and not os.path.exists(config['csv_path']):
        print(f"  ERROR: CSV file not found: {config['csv_path']}")
        return False
    
    if not os.path.exists(config['schema_path']):
        print(f"  ERROR: Schema file not found: {config['schema_path']}")
        return False

    cmd = [
        sys.executable, "csv_to_duckdb.py",
        config['csv_path'],
        "--schema", config['schema_path'],
        "--output", config['output_path']
    ]
    
    if config.get('url'):
        cmd.extend(["--url", config['url']])

    if config.get('config_path'):
        if not os.path.exists(config['config_path']):
            print(f"  ERROR: Config file not found: {config['config_path']}")
            return False
        cmd.extend(["--config", config['config_path']])

    if config.get('split_size'):
        cmd.extend(["--split-size", str(config['split_size'])])

    if clean:
        cmd.append("--clean")

    try:
        subprocess.check_call(cmd)
        print("  SUCCESS")
        return True
    except subprocess.CalledProcessError:
        print("  FAILED")
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate DuckDB databases from CSV based on YAML config.")
    parser.add_argument("--config", default="csv_to_duckdb.yaml", help="Path to YAML config file")
    parser.add_argument("--clean", action="store_true", help="Clean existing databases before generating")
    parser.add_argument("target", nargs="?", default="all", help="Target dataset name (from config) or 'all'")
    
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: Config file '{args.config}' not found.")
        sys.exit(1)

    config_data = load_config(args.config)
    datasets = config_data.get('datasets', {})

    if not datasets:
        print("No datasets found in config.")
        sys.exit(1)

    targets = []
    if args.target == "all":
        targets = list(datasets.keys())
    elif args.target in datasets:
        targets = [args.target]
    else:
        print(f"Error: Target '{args.target}' not found in config.")
        print("Available targets:", ", ".join(datasets.keys()))
        sys.exit(1)

    print("============================================================")
    print("  Generating DuckDB Databases")
    print("============================================================")
    print("")

    success_count = 0
    fail_count = 0

    for target in targets:
        if generate_database(target, datasets[target], args.clean):
            success_count += 1
        else:
            fail_count += 1
        print("")

    print("============================================================")
    print("  Generation Complete")
    print("============================================================")
    print(f"  Successful: {success_count}")
    print(f"  Failed:     {fail_count}")
    print("============================================================")

    if fail_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
