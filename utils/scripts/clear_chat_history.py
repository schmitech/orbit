#!/usr/bin/env python3
"""Clear chat history and related data in orbit.db.

This script deletes all rows from chat_history, file_chunks, and uploaded_files
in an Orbit SQLite database. Use it to reset conversation state without
dropping the schema (e.g. for a fresh chat or debugging).

What gets cleared (in dependency order):
  1. file_chunks  (references uploaded_files)
  2. uploaded_files
  3. chat_history

Usage
-----
Run with the project venv activated. You can call the script from any directory.

  # Use the default database: orbit.db in this script's directory
  python clear_chat_history.py

  # Specify the database path (absolute or relative to current working directory)
  python clear_chat_history.py -d /path/to/orbit.db
  python clear_chat_history.py --db ./orbit.db

  # Tilde paths work
  python clear_chat_history.py -d ~/orbit/orbit.db

If the given path does not exist, the script exits with an error. It prints
row counts before and after for each table so you can confirm the clear.
"""
import argparse
import os
import sqlite3

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orbit.db')

def main():
    parser = argparse.ArgumentParser(description='Clear chat_history, file_chunks, and uploaded_files in orbit.db')
    parser.add_argument(
        '-d', '--db',
        default=DEFAULT_DB,
        metavar='PATH',
        help=f'Path to orbit.db (default: {DEFAULT_DB})',
    )
    args = parser.parse_args()
    db_path = os.path.abspath(os.path.expanduser(args.db))

    if not os.path.isfile(db_path):
        raise SystemExit(f'Database not found: {db_path}')

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. file_chunks first (references uploaded_files.id)
    cur.execute('SELECT COUNT(*) FROM file_chunks')
    fc_before = cur.fetchone()[0]
    cur.execute('DELETE FROM file_chunks')

    # 2. uploaded_files
    cur.execute('SELECT COUNT(*) FROM uploaded_files')
    uf_before = cur.fetchone()[0]
    cur.execute('DELETE FROM uploaded_files')

    # 3. chat_history
    cur.execute('SELECT COUNT(*) FROM chat_history')
    ch_before = cur.fetchone()[0]
    cur.execute('DELETE FROM chat_history')

    conn.commit()

    cur.execute('SELECT COUNT(*) FROM file_chunks')
    fc_after = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM uploaded_files')
    uf_after = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM chat_history')
    ch_after = cur.fetchone()[0]

    print(f'file_chunks: {fc_before} -> {fc_after}.')
    print(f'uploaded_files: {uf_before} -> {uf_after}.')
    print(f'chat_history: {ch_before} -> {ch_after}.')

    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
