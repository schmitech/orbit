#!/usr/bin/env python3
"""
Split a large CSV file into chunks of approximately 5 MB each.
Uses streaming: does not load the entire file into memory.
Preserves the header row in every chunk so each part is valid CSV.

Usage:
    python split_csv.py <input_file> [-d <output_dir>]

Arguments:
    input_file          Path to the CSV file to split.
    -d, --output-dir    Directory where chunk files will be created.
                        Defaults to the current directory. Created
                        automatically if it does not exist.

Examples:
    python split_csv.py data.csv
    python split_csv.py data.csv -d ./chunks

Run "python split_csv.py --help" for full usage information.
"""

import argparse
import csv
import os
import sys

CHUNK_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
OUTPUT_SUFFIX = ".csv"


def split_csv(
    input_path: str,
    output_dir: str = ".",
    chunk_size: int = CHUNK_SIZE_BYTES,
    encoding: str = "utf-8",
) -> list[str]:
    """
    Split input_path CSV into chunks of ~chunk_size bytes.
    Returns list of output file paths.
    """
    output_files = []
    part = 0
    current_size = 0
    header: list | None = None
    out_file = None
    writer = None

    def _estimate_row_size(row: list) -> int:
        """Cheap byte-length estimate: field lengths + commas + newline."""
        return sum(len(field) for field in row) + len(row)

    output_prefix = os.path.splitext(os.path.basename(input_path))[0]

    def _start_new_chunk() -> tuple:
        nonlocal part, current_size
        part += 1
        current_size = 0
        out_path = os.path.join(output_dir, f"{output_prefix}_part_{part:03d}{OUTPUT_SUFFIX}")
        f_out = open(out_path, "w", newline="", encoding=encoding)
        w = csv.writer(f_out)
        w.writerow(header)
        output_files.append(out_path)
        return f_out, w

    with open(input_path, "r", newline="", encoding=encoding, errors="replace") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print("File is empty or has no header.", file=sys.stderr)
            return []

        try:
            for row in reader:
                row_len = _estimate_row_size(row)

                if current_size + row_len > chunk_size and out_file is not None:
                    out_file.close()
                    print(f"  Wrote {output_files[-1]} ({current_size / (1024*1024):.2f} MB)")
                    out_file, writer = _start_new_chunk()

                if out_file is None:
                    out_file, writer = _start_new_chunk()

                writer.writerow(row)
                current_size += row_len
        finally:
            if out_file is not None:
                out_file.close()
                print(f"  Wrote {output_files[-1]} ({current_size / (1024*1024):.2f} MB)")

    return output_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split a large CSV file into chunks of approximately 5 MB each.",
    )
    parser.add_argument("input_file", help="Path to the CSV file to split")
    parser.add_argument(
        "-d", "--output-dir",
        default=".",
        help="Directory where chunk files will be created (default: current directory)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input_file):
        print(f"Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    size_mb = os.path.getsize(args.input_file) / (1024 * 1024)
    print(f"Splitting {args.input_file} ({size_mb:.1f} MB) into ~5 MB chunks...")
    files = split_csv(args.input_file, output_dir=args.output_dir)
    print(f"Done. Created {len(files)} part(s).")


if __name__ == "__main__":
    main()
