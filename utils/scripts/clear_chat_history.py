#!/usr/bin/env python3
"""Clear chat_history, file_chunks, and uploaded_files in orbit.db.

Order: file_chunks first (FK to uploaded_files), then uploaded_files, then chat_history.
Run from orbit-2.4.0 with venv activated.
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orbit.db')
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
