#!/usr/bin/env python3
"""Sync api_keys and system_prompts between auth backends.

Copies the `api_keys` and `system_prompts` collections between the Orbit
SQLite backend (default: orbit.db) and the MongoDB or PostgreSQL `orbit`
database, or between two SQLite database files, so backends stay in sync when
switching `internal_services.backend.type` or rebuilding a fresh SQLite
database after schema changes.

Matching is done on natural unique keys:
  - system_prompts.name
  - api_keys.api_key

Cross-references (api_keys.system_prompt_id -> system_prompts._id) are
re-resolved through the prompt name on the destination side so the link
remains valid regardless of ID format (UUID vs ObjectId).

Environment
-----------
Loads `.env` from the project root for MongoDB credentials:
  INTERNAL_SERVICES_MONGODB_HOST
  INTERNAL_SERVICES_MONGODB_PORT
  INTERNAL_SERVICES_MONGODB_USERNAME
  INTERNAL_SERVICES_MONGODB_PASSWORD
  INTERNAL_SERVICES_MONGODB_DB   (default: orbit)

Loads `.env` from the project root for PostgreSQL credentials:
  INTERNAL_SERVICES_POSTGRES_HOST
  INTERNAL_SERVICES_POSTGRES_PORT
  INTERNAL_SERVICES_POSTGRES_USERNAME
  INTERNAL_SERVICES_POSTGRES_PASSWORD
  INTERNAL_SERVICES_POSTGRES_DB       (default: orbit)
  INTERNAL_SERVICES_POSTGRES_SSLMODE  (default: prefer)

Usage
-----
Run with the project venv activated.

  # Copy SQLite -> MongoDB (upsert into MongoDB)
  python sync_auth_backends.py --direction sqlite-to-mongo

  # Copy SQLite -> PostgreSQL (upsert into PostgreSQL)
  python sync_auth_backends.py --direction sqlite-to-postgres

  # Copy MongoDB -> SQLite (upsert into SQLite)
  python sync_auth_backends.py --direction mongo-to-sqlite

  # Copy PostgreSQL -> SQLite (upsert into SQLite)
  python sync_auth_backends.py --direction postgres-to-sqlite

  # Copy SQLite -> SQLite (upsert into destination SQLite)
  python sync_auth_backends.py --direction sqlite-to-sqlite \
      --source-db ./orbit.db.bak --dest-db ./orbit.db

  # Dry run (show what would change, do not write)
  python sync_auth_backends.py --direction sqlite-to-postgres --dry-run

  # Custom SQLite path / backend database
  python sync_auth_backends.py --direction sqlite-to-postgres \
      --db /path/to/orbit.db --postgres-db orbit

Only upserts are performed. Records present in the destination but absent
from the source are left untouched; pass --delete-missing to remove them.
"""
import argparse
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = PROJECT_ROOT / "orbit.db"

API_KEY_FIELDS = [
    "api_key", "client_name", "notes", "active", "created_at",
    "adapter_name", "system_prompt_id",
    "quota_daily_limit", "quota_monthly_limit",
    "quota_throttle_enabled", "quota_throttle_priority",
]
PROMPT_FIELDS = ["name", "prompt", "version", "created_at", "updated_at"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_mongo_uri() -> Tuple[str, str]:
    host = os.getenv("INTERNAL_SERVICES_MONGODB_HOST", "localhost")
    port = os.getenv("INTERNAL_SERVICES_MONGODB_PORT", "27017")
    user = os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME", "")
    pw = os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD", "")
    db = os.getenv("INTERNAL_SERVICES_MONGODB_DB", "orbit")

    if "mongodb.net" in host and user and pw:
        uri = f"mongodb+srv://{user}:{pw}@{host}/{db}?retryWrites=true&w=majority"
    elif user and pw:
        uri = f"mongodb://{user}:{pw}@{host}:{port}/{db}"
    else:
        uri = f"mongodb://{host}:{port}/{db}"
    return uri, db


def build_postgres_config(postgres_db: Optional[str] = None) -> Dict[str, Any]:
    return {
        "host": os.getenv("INTERNAL_SERVICES_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("INTERNAL_SERVICES_POSTGRES_PORT", "5432")),
        "dbname": postgres_db or os.getenv("INTERNAL_SERVICES_POSTGRES_DB", "orbit"),
        "user": os.getenv("INTERNAL_SERVICES_POSTGRES_USERNAME", "postgres"),
        "password": os.getenv("INTERNAL_SERVICES_POSTGRES_PASSWORD", ""),
        "sslmode": os.getenv("INTERNAL_SERVICES_POSTGRES_SSLMODE", "prefer"),
    }


def to_sqlite_value(v: Any) -> Any:
    """Normalize a value for SQLite binding (datetimes -> ISO string)."""
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _as_datetime(v: Any) -> Optional[datetime]:
    """Parse a value into a naive datetime if possible, else None."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, str):
        try:
            parsed = datetime.fromisoformat(v)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None
    return None


def values_equal(a: Any, b: Any) -> bool:
    """Compare two values, treating ms-truncated datetimes as equal to their
    µs-precision counterparts (BSON stores datetimes at ms resolution, so a
    sqlite -> mongo -> sqlite round-trip loses sub-millisecond digits)."""
    if a == b:
        return True
    da, db = _as_datetime(a), _as_datetime(b)
    if da is not None and db is not None:
        return da.replace(microsecond=(da.microsecond // 1000) * 1000) == \
               db.replace(microsecond=(db.microsecond // 1000) * 1000)
    return False


def to_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return bool(v)
    if isinstance(v, str):
        return v.lower() in ("1", "true", "yes")
    return bool(v)


def sqlite_row_to_prompt(row: sqlite3.Row) -> Dict[str, Any]:
    return {f: row[f] for f in ["id", *PROMPT_FIELDS] if f in row.keys()}


def sqlite_row_to_api_key(row: sqlite3.Row) -> Dict[str, Any]:
    doc = {f: row[f] for f in ["id", *API_KEY_FIELDS] if f in row.keys()}
    # Normalize booleans for cross-backend comparison
    if doc.get("active") is not None:
        doc["active"] = bool(doc["active"])
    if doc.get("quota_throttle_enabled") is not None:
        doc["quota_throttle_enabled"] = bool(doc["quota_throttle_enabled"])
    return doc


def open_sqlite(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SystemExit(f"SQLite database not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_sqlite_table_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row["name"] for row in cur.fetchall()]


def read_sqlite_prompts(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    desired_cols = ["id", *PROMPT_FIELDS]
    available_cols = set(get_sqlite_table_columns(conn, "system_prompts"))
    cols = [col for col in desired_cols if col in available_cols]
    cur = conn.execute("SELECT " + ", ".join(cols) + " FROM system_prompts")
    return [sqlite_row_to_prompt(r) for r in cur.fetchall()]


def read_sqlite_api_keys(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    desired_cols = [
        "id", "api_key", "client_name", "notes", "active", "created_at",
        "adapter_name", "system_prompt_id",
        "quota_daily_limit", "quota_monthly_limit",
        "quota_throttle_enabled", "quota_throttle_priority",
    ]
    available_cols = set(get_sqlite_table_columns(conn, "api_keys"))
    cols = [col for col in desired_cols if col in available_cols]
    cur = conn.execute("SELECT " + ", ".join(cols) + " FROM api_keys")
    return [sqlite_row_to_api_key(r) for r in cur.fetchall()]


def mongo_id_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, ObjectId):
        return str(v)
    return str(v)


def postgres_row_to_prompt(row: Dict[str, Any]) -> Dict[str, Any]:
    return {f: row.get(f) for f in ["id", *PROMPT_FIELDS] if f in row}


def postgres_row_to_api_key(row: Dict[str, Any]) -> Dict[str, Any]:
    doc = {f: row.get(f) for f in ["id", *API_KEY_FIELDS] if f in row}
    if doc.get("active") is not None:
        doc["active"] = bool(doc["active"])
    if doc.get("quota_throttle_enabled") is not None:
        doc["quota_throttle_enabled"] = bool(doc["quota_throttle_enabled"])
    return doc


# --- SQLite -> MongoDB -------------------------------------------------------

def sync_sqlite_to_mongo(conn: sqlite3.Connection, mdb, dry_run: bool, delete_missing: bool) -> None:
    print("== Syncing system_prompts: SQLite -> MongoDB ==")
    prompts_coll = mdb["system_prompts"]
    sqlite_prompts = read_sqlite_prompts(conn)
    mongo_prompts = list(prompts_coll.find({}))
    mongo_by_name = {p["name"]: p for p in mongo_prompts}

    # Map SQLite prompt id -> MongoDB _id (string) for cross-ref resolution
    prompt_id_map: Dict[str, str] = {}
    inserted = updated = unchanged = 0

    for p in sqlite_prompts:
        name = p["name"]
        existing = mongo_by_name.get(name)
        doc = {f: p.get(f) for f in PROMPT_FIELDS}
        if existing:
            prompt_id_map[p["id"]] = mongo_id_str(existing["_id"])
            changes = {k: v for k, v in doc.items() if not values_equal(existing.get(k), v)}
            if not changes:
                unchanged += 1
                continue
            print(f"  UPDATE prompt '{name}': {list(changes.keys())}")
            if not dry_run:
                prompts_coll.update_one({"_id": existing["_id"]}, {"$set": changes})
            updated += 1
        else:
            new_id = p["id"] or str(uuid.uuid4())
            doc["_id"] = new_id
            prompt_id_map[p["id"]] = new_id
            print(f"  INSERT prompt '{name}' (_id={new_id})")
            if not dry_run:
                prompts_coll.insert_one(doc)
            inserted += 1

    if delete_missing:
        sqlite_names = {p["name"] for p in sqlite_prompts}
        for m in mongo_prompts:
            if m["name"] not in sqlite_names:
                print(f"  DELETE prompt '{m['name']}' (not in SQLite)")
                if not dry_run:
                    prompts_coll.delete_one({"_id": m["_id"]})
    print(f"  prompts: inserted={inserted} updated={updated} unchanged={unchanged}")

    print("== Syncing api_keys: SQLite -> MongoDB ==")
    keys_coll = mdb["api_keys"]
    sqlite_keys = read_sqlite_api_keys(conn)
    mongo_keys = list(keys_coll.find({}))
    mongo_by_apikey = {k["api_key"]: k for k in mongo_keys}

    inserted = updated = unchanged = 0
    for k in sqlite_keys:
        api_key = k["api_key"]
        doc = {f: k.get(f) for f in API_KEY_FIELDS}
        # Re-resolve system_prompt_id through the prompt id map
        if k.get("system_prompt_id"):
            mapped = prompt_id_map.get(k["system_prompt_id"])
            if mapped:
                doc["system_prompt_id"] = mapped
            else:
                print(f"  WARN api_key {api_key[:8]}... references unknown system_prompt_id {k['system_prompt_id']}")
                doc["system_prompt_id"] = None

        existing = mongo_by_apikey.get(api_key)
        if existing:
            changes = {kk: vv for kk, vv in doc.items() if not values_equal(existing.get(kk), vv)}
            if not changes:
                unchanged += 1
                continue
            print(f"  UPDATE api_key {api_key[:8]}...: {list(changes.keys())}")
            if not dry_run:
                keys_coll.update_one({"_id": existing["_id"]}, {"$set": changes})
            updated += 1
        else:
            new_id = k["id"] or str(uuid.uuid4())
            doc["_id"] = new_id
            print(f"  INSERT api_key {api_key[:8]}... (_id={new_id})")
            if not dry_run:
                keys_coll.insert_one(doc)
            inserted += 1

    if delete_missing:
        sqlite_apikeys = {k["api_key"] for k in sqlite_keys}
        for m in mongo_keys:
            if m["api_key"] not in sqlite_apikeys:
                print(f"  DELETE api_key {m['api_key'][:8]}... (not in SQLite)")
                if not dry_run:
                    keys_coll.delete_one({"_id": m["_id"]})
    print(f"  api_keys: inserted={inserted} updated={updated} unchanged={unchanged}")


# --- MongoDB -> SQLite -------------------------------------------------------

def upsert_sqlite_prompt(conn: sqlite3.Connection, existing: Optional[sqlite3.Row], doc: Dict[str, Any], dry_run: bool) -> str:
    """Upsert a system_prompts row. Returns the row's id."""
    available_cols = set(get_sqlite_table_columns(conn, "system_prompts"))
    if existing:
        fields = [f for f in PROMPT_FIELDS if f in available_cols and f in doc and doc.get(f) is not None]
        set_clause = ", ".join(f"{f} = ?" for f in fields)
        params = [to_sqlite_value(doc[f]) for f in fields] + [existing["id"]]
        if not dry_run and fields:
            conn.execute(f"UPDATE system_prompts SET {set_clause} WHERE id = ?", params)
        return existing["id"]
    new_id = doc.get("_sqlite_id") or str(uuid.uuid4())
    insert_values = {
        "name": doc.get("name"),
        "prompt": doc.get("prompt"),
        "version": doc.get("version") or "1.0",
        "created_at": to_sqlite_value(doc.get("created_at")) or now_iso(),
        "updated_at": to_sqlite_value(doc.get("updated_at")) or now_iso(),
    }
    cols = [col for col in PROMPT_FIELDS if col in available_cols and col in insert_values]
    if not dry_run:
        conn.execute(
            "INSERT INTO system_prompts (id, " + ", ".join(cols) + ") VALUES (?" + ", ?" * len(cols) + ")",
            [new_id, *[insert_values[col] for col in cols]],
        )
    return new_id


def upsert_sqlite_api_key(conn: sqlite3.Connection, existing: Optional[sqlite3.Row], doc: Dict[str, Any], dry_run: bool) -> None:
    desired_cols = [
        "api_key", "client_name", "notes", "active", "created_at",
        "adapter_name", "system_prompt_id",
        "quota_daily_limit", "quota_monthly_limit",
        "quota_throttle_enabled", "quota_throttle_priority",
    ]
    available_cols = set(get_sqlite_table_columns(conn, "api_keys"))
    cols = [col for col in desired_cols if col in available_cols and col in doc]
    vals = []
    for c in cols:
        v = doc.get(c)
        if c in ("active", "quota_throttle_enabled") and v is not None:
            v = 1 if v else 0
        vals.append(to_sqlite_value(v))

    if existing:
        set_clause = ", ".join(f"{c} = ?" for c in cols)
        if not dry_run:
            conn.execute(f"UPDATE api_keys SET {set_clause} WHERE id = ?", [*vals, existing["id"]])
        return
    new_id = doc.get("_sqlite_id") or str(uuid.uuid4())
    if not dry_run:
        conn.execute(
            "INSERT INTO api_keys (id, " + ", ".join(cols) + ") VALUES (?" + ", ?" * len(cols) + ")",
            [new_id, *vals],
        )


def sync_mongo_to_sqlite(conn: sqlite3.Connection, mdb, dry_run: bool, delete_missing: bool) -> None:
    print("== Syncing system_prompts: MongoDB -> SQLite ==")
    mongo_prompts = list(mdb["system_prompts"].find({}))
    sqlite_prompts = {r["name"]: r for r in conn.execute("SELECT * FROM system_prompts").fetchall()}

    # Map MongoDB prompt _id -> SQLite id (for api_keys.system_prompt_id rewrite)
    prompt_id_map: Dict[str, str] = {}
    inserted = updated = unchanged = 0

    for p in mongo_prompts:
        name = p.get("name")
        if not name:
            continue
        existing = sqlite_prompts.get(name)
        # Carry the Mongo _id forward as the SQLite id when inserting new rows
        # (uses string form; if it's an ObjectId we'd rather mint a UUID for portability).
        mongo_id = mongo_id_str(p.get("_id"))
        sqlite_new_id = mongo_id if (mongo_id and _looks_like_uuid(mongo_id)) else str(uuid.uuid4())

        if existing:
            prompt_id_map[mongo_id] = existing["id"]
            changed = any(
                not values_equal(existing[f], p.get(f))
                for f in PROMPT_FIELDS if f in existing.keys()
            )
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE prompt '{name}'")
            upsert_sqlite_prompt(conn, existing, p, dry_run)
            updated += 1
        else:
            print(f"  INSERT prompt '{name}' (id={sqlite_new_id})")
            doc = dict(p)
            doc["_sqlite_id"] = sqlite_new_id
            upsert_sqlite_prompt(conn, None, doc, dry_run)
            prompt_id_map[mongo_id] = sqlite_new_id
            inserted += 1

    if delete_missing:
        mongo_names = {p.get("name") for p in mongo_prompts}
        for name, row in sqlite_prompts.items():
            if name not in mongo_names:
                print(f"  DELETE prompt '{name}' (not in MongoDB)")
                if not dry_run:
                    conn.execute("DELETE FROM system_prompts WHERE id = ?", (row["id"],))
    print(f"  prompts: inserted={inserted} updated={updated} unchanged={unchanged}")

    print("== Syncing api_keys: MongoDB -> SQLite ==")
    mongo_keys = list(mdb["api_keys"].find({}))
    sqlite_keys = {r["api_key"]: r for r in conn.execute("SELECT * FROM api_keys").fetchall()}

    inserted = updated = unchanged = 0
    for k in mongo_keys:
        api_key = k.get("api_key")
        if not api_key:
            continue
        # Translate system_prompt_id through the prompt id map (if known).
        # If the Mongo doc's system_prompt_id isn't in the map, we fall back to
        # looking up the prompt name via MongoDB and resolving in SQLite.
        src_prompt_id = mongo_id_str(k.get("system_prompt_id"))
        translated = prompt_id_map.get(src_prompt_id) if src_prompt_id else None
        if src_prompt_id and translated is None:
            # Try to find the source prompt in Mongo and match by name in SQLite.
            mongo_prompt = mdb["system_prompts"].find_one({"_id": k.get("system_prompt_id")})
            if mongo_prompt and mongo_prompt.get("name"):
                sqlite_match = sqlite_prompts.get(mongo_prompt["name"])
                if sqlite_match:
                    translated = sqlite_match["id"]
            if not translated:
                print(f"  WARN api_key {api_key[:8]}... references unknown system_prompt_id {src_prompt_id}")

        doc = dict(k)
        doc["system_prompt_id"] = translated if src_prompt_id else None

        existing = sqlite_keys.get(api_key)
        mongo_id = mongo_id_str(k.get("_id"))
        doc["_sqlite_id"] = mongo_id if (mongo_id and _looks_like_uuid(mongo_id)) else str(uuid.uuid4())

        if existing:
            # Compare normalized values
            changed = False
            for f in API_KEY_FIELDS:
                sv = existing[f] if f in existing.keys() else None
                dv = doc.get(f)
                if f in ("active", "quota_throttle_enabled"):
                    sv_b = bool(sv) if sv is not None else None
                    dv_b = to_bool(dv)
                    if sv_b != dv_b:
                        changed = True
                        break
                elif not values_equal(sv, dv):
                    changed = True
                    break
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE api_key {api_key[:8]}...")
            upsert_sqlite_api_key(conn, existing, doc, dry_run)
            updated += 1
        else:
            print(f"  INSERT api_key {api_key[:8]}... (id={doc['_sqlite_id']})")
            upsert_sqlite_api_key(conn, None, doc, dry_run)
            inserted += 1

    if delete_missing:
        mongo_apikeys = {k.get("api_key") for k in mongo_keys}
        for apikey, row in sqlite_keys.items():
            if apikey not in mongo_apikeys:
                print(f"  DELETE api_key {apikey[:8]}... (not in MongoDB)")
                if not dry_run:
                    conn.execute("DELETE FROM api_keys WHERE id = ?", (row["id"],))
    print(f"  api_keys: inserted={inserted} updated={updated} unchanged={unchanged}")


# --- SQLite -> PostgreSQL ----------------------------------------------------

def ensure_postgres_auth_schema(pg_conn) -> None:
    pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS system_prompts (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            prompt TEXT NOT NULL,
            version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            api_key TEXT UNIQUE NOT NULL,
            client_name TEXT NOT NULL,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            adapter_name TEXT,
            system_prompt_id TEXT,
            quota_daily_limit INTEGER,
            quota_monthly_limit INTEGER,
            quota_throttle_enabled INTEGER,
            quota_throttle_priority INTEGER
        )
    """)
    pg_conn.execute("CREATE INDEX IF NOT EXISTS idx_system_prompts_name ON system_prompts(name)")
    pg_conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_api_key ON api_keys(api_key)")


def postgres_table_exists(pg_conn, table: str) -> bool:
    row = pg_conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row.get("table_name"))


def read_postgres_prompts(pg_conn) -> List[Dict[str, Any]]:
    if not postgres_table_exists(pg_conn, "system_prompts"):
        return []
    rows = pg_conn.execute(
        "SELECT id, name, prompt, version, created_at, updated_at FROM system_prompts"
    ).fetchall()
    return [postgres_row_to_prompt(row) for row in rows]


def read_postgres_api_keys(pg_conn) -> List[Dict[str, Any]]:
    if not postgres_table_exists(pg_conn, "api_keys"):
        return []
    rows = pg_conn.execute(
        """
        SELECT id, api_key, client_name, notes, active, created_at, adapter_name,
               system_prompt_id, quota_daily_limit, quota_monthly_limit,
               quota_throttle_enabled, quota_throttle_priority
        FROM api_keys
        """
    ).fetchall()
    return [postgres_row_to_api_key(row) for row in rows]


def upsert_postgres_prompt(pg_conn, existing: Optional[Dict[str, Any]], doc: Dict[str, Any], dry_run: bool) -> str:
    if existing:
        fields = [f for f in PROMPT_FIELDS if f in doc and doc.get(f) is not None]
        if fields and not dry_run:
            set_clause = ", ".join(f'"{f}" = %s' for f in fields)
            pg_conn.execute(
                f"UPDATE system_prompts SET {set_clause} WHERE id = %s",
                [*[doc[f] for f in fields], existing["id"]],
            )
        return existing["id"]

    new_id = doc.get("_postgres_id") or str(uuid.uuid4())
    values = {
        "name": doc.get("name"),
        "prompt": doc.get("prompt"),
        "version": doc.get("version") or "1.0",
        "created_at": doc.get("created_at") or now_iso(),
        "updated_at": doc.get("updated_at") or now_iso(),
    }
    if not dry_run:
        pg_conn.execute(
            """
            INSERT INTO system_prompts (id, name, prompt, version, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                new_id,
                values["name"],
                values["prompt"],
                values["version"],
                values["created_at"],
                values["updated_at"],
            ],
        )
    return new_id


def upsert_postgres_api_key(pg_conn, existing: Optional[Dict[str, Any]], doc: Dict[str, Any], dry_run: bool) -> str:
    desired_cols = [
        "api_key", "client_name", "notes", "active", "created_at",
        "adapter_name", "system_prompt_id",
        "quota_daily_limit", "quota_monthly_limit",
        "quota_throttle_enabled", "quota_throttle_priority",
    ]
    values = dict(doc)
    for key in ("active", "quota_throttle_enabled"):
        if values.get(key) is not None:
            values[key] = 1 if to_bool(values[key]) else 0

    if existing:
        fields = [f for f in desired_cols if f in values]
        if fields and not dry_run:
            set_clause = ", ".join(f'"{f}" = %s' for f in fields)
            pg_conn.execute(
                f"UPDATE api_keys SET {set_clause} WHERE id = %s",
                [*[values.get(f) for f in fields], existing["id"]],
            )
        return existing["id"]

    new_id = values.get("_postgres_id") or str(uuid.uuid4())
    insert_values = {
        "api_key": values.get("api_key"),
        "client_name": values.get("client_name"),
        "notes": values.get("notes"),
        "active": values.get("active") if values.get("active") is not None else 1,
        "created_at": values.get("created_at") or now_iso(),
        "adapter_name": values.get("adapter_name"),
        "system_prompt_id": values.get("system_prompt_id"),
        "quota_daily_limit": values.get("quota_daily_limit"),
        "quota_monthly_limit": values.get("quota_monthly_limit"),
        "quota_throttle_enabled": values.get("quota_throttle_enabled"),
        "quota_throttle_priority": values.get("quota_throttle_priority"),
    }
    if not dry_run:
        pg_conn.execute(
            """
            INSERT INTO api_keys (
                id, api_key, client_name, notes, active, created_at,
                adapter_name, system_prompt_id, quota_daily_limit,
                quota_monthly_limit, quota_throttle_enabled, quota_throttle_priority
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                new_id,
                insert_values["api_key"],
                insert_values["client_name"],
                insert_values["notes"],
                insert_values["active"],
                insert_values["created_at"],
                insert_values["adapter_name"],
                insert_values["system_prompt_id"],
                insert_values["quota_daily_limit"],
                insert_values["quota_monthly_limit"],
                insert_values["quota_throttle_enabled"],
                insert_values["quota_throttle_priority"],
            ],
        )
    return new_id


def sync_sqlite_to_postgres(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    dry_run: bool,
    delete_missing: bool,
) -> None:
    if not dry_run:
        ensure_postgres_auth_schema(pg_conn)

    print("== Syncing system_prompts: SQLite -> PostgreSQL ==")
    sqlite_prompts = read_sqlite_prompts(sqlite_conn)
    postgres_prompts = read_postgres_prompts(pg_conn)
    postgres_by_name = {p["name"]: p for p in postgres_prompts if p.get("name")}

    prompt_id_map: Dict[str, str] = {}
    inserted = updated = unchanged = 0

    for p in sqlite_prompts:
        name = p.get("name")
        if not name:
            continue
        existing = postgres_by_name.get(name)
        source_id = p.get("id")

        if existing:
            if source_id:
                prompt_id_map[source_id] = existing["id"]
            changed = any(
                f in p and not values_equal(existing.get(f), p.get(f))
                for f in PROMPT_FIELDS
            )
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE prompt '{name}'")
            upsert_postgres_prompt(pg_conn, existing, p, dry_run)
            updated += 1
        else:
            new_id = source_id if (source_id and _looks_like_uuid(source_id)) else str(uuid.uuid4())
            print(f"  INSERT prompt '{name}' (id={new_id})")
            doc = dict(p)
            doc["_postgres_id"] = new_id
            upsert_postgres_prompt(pg_conn, None, doc, dry_run)
            if source_id:
                prompt_id_map[source_id] = new_id
            inserted += 1

    if delete_missing:
        sqlite_names = {p.get("name") for p in sqlite_prompts}
        for p in postgres_prompts:
            if p.get("name") not in sqlite_names:
                print(f"  DELETE prompt '{p['name']}' (not in SQLite)")
                if not dry_run:
                    pg_conn.execute("DELETE FROM system_prompts WHERE id = %s", (p["id"],))
    print(f"  prompts: inserted={inserted} updated={updated} unchanged={unchanged}")

    print("== Syncing api_keys: SQLite -> PostgreSQL ==")
    sqlite_keys = read_sqlite_api_keys(sqlite_conn)
    postgres_keys = read_postgres_api_keys(pg_conn)
    postgres_by_apikey = {k["api_key"]: k for k in postgres_keys if k.get("api_key")}

    inserted = updated = unchanged = 0
    for k in sqlite_keys:
        api_key = k.get("api_key")
        if not api_key:
            continue

        doc = dict(k)
        source_prompt_id = k.get("system_prompt_id")
        if source_prompt_id:
            translated = prompt_id_map.get(source_prompt_id)
            if translated:
                doc["system_prompt_id"] = translated
            else:
                print(f"  WARN api_key {api_key[:8]}... references unknown system_prompt_id {source_prompt_id}")
                doc["system_prompt_id"] = None

        existing = postgres_by_apikey.get(api_key)
        source_id = k.get("id")
        doc["_postgres_id"] = source_id if (source_id and _looks_like_uuid(source_id)) else str(uuid.uuid4())

        if existing:
            changed = False
            for f in API_KEY_FIELDS:
                if f not in doc:
                    continue
                sv = existing.get(f)
                dv = doc.get(f)
                if f in ("active", "quota_throttle_enabled"):
                    if (bool(sv) if sv is not None else None) != to_bool(dv):
                        changed = True
                        break
                elif not values_equal(sv, dv):
                    changed = True
                    break
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE api_key {api_key[:8]}...")
            upsert_postgres_api_key(pg_conn, existing, doc, dry_run)
            updated += 1
        else:
            print(f"  INSERT api_key {api_key[:8]}... (id={doc['_postgres_id']})")
            upsert_postgres_api_key(pg_conn, None, doc, dry_run)
            inserted += 1

    if delete_missing:
        sqlite_apikeys = {k.get("api_key") for k in sqlite_keys}
        for k in postgres_keys:
            if k.get("api_key") not in sqlite_apikeys:
                print(f"  DELETE api_key {k['api_key'][:8]}... (not in SQLite)")
                if not dry_run:
                    pg_conn.execute("DELETE FROM api_keys WHERE id = %s", (k["id"],))
    print(f"  api_keys: inserted={inserted} updated={updated} unchanged={unchanged}")


# --- PostgreSQL -> SQLite ----------------------------------------------------

def sync_postgres_to_sqlite(pg_conn, sqlite_conn: sqlite3.Connection, dry_run: bool, delete_missing: bool) -> None:
    print("== Syncing system_prompts: PostgreSQL -> SQLite ==")
    postgres_prompts = read_postgres_prompts(pg_conn)
    sqlite_prompts = {
        r["name"]: r
        for r in sqlite_conn.execute("SELECT * FROM system_prompts").fetchall()
        if r["name"]
    }

    # Map PostgreSQL prompt id -> SQLite prompt id for api_keys.system_prompt_id rewrite.
    prompt_id_map: Dict[str, str] = {}
    inserted = updated = unchanged = 0

    for p in postgres_prompts:
        name = p.get("name")
        if not name:
            continue
        existing = sqlite_prompts.get(name)
        source_id = p.get("id")
        if existing:
            if source_id:
                prompt_id_map[source_id] = existing["id"]
            changed = any(
                f in p and not values_equal(existing[f], p.get(f))
                for f in PROMPT_FIELDS if f in existing.keys()
            )
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE prompt '{name}'")
            upsert_sqlite_prompt(sqlite_conn, existing, p, dry_run)
            updated += 1
        else:
            new_id = source_id if (source_id and _looks_like_uuid(source_id)) else str(uuid.uuid4())
            print(f"  INSERT prompt '{name}' (id={new_id})")
            doc = dict(p)
            doc["_sqlite_id"] = new_id
            upsert_sqlite_prompt(sqlite_conn, None, doc, dry_run)
            if source_id:
                prompt_id_map[source_id] = new_id
            inserted += 1

    if delete_missing:
        postgres_names = {p.get("name") for p in postgres_prompts}
        for name, row in sqlite_prompts.items():
            if name not in postgres_names:
                print(f"  DELETE prompt '{name}' (not in PostgreSQL)")
                if not dry_run:
                    sqlite_conn.execute("DELETE FROM system_prompts WHERE id = ?", (row["id"],))
    print(f"  prompts: inserted={inserted} updated={updated} unchanged={unchanged}")

    print("== Syncing api_keys: PostgreSQL -> SQLite ==")
    postgres_keys = read_postgres_api_keys(pg_conn)
    sqlite_keys = {
        r["api_key"]: r
        for r in sqlite_conn.execute("SELECT * FROM api_keys").fetchall()
        if r["api_key"]
    }

    inserted = updated = unchanged = 0
    for k in postgres_keys:
        api_key = k.get("api_key")
        if not api_key:
            continue

        doc = dict(k)
        source_prompt_id = k.get("system_prompt_id")
        if source_prompt_id:
            translated = prompt_id_map.get(source_prompt_id)
            if translated:
                doc["system_prompt_id"] = translated
            else:
                print(f"  WARN api_key {api_key[:8]}... references unknown system_prompt_id {source_prompt_id}")
                doc["system_prompt_id"] = None

        existing = sqlite_keys.get(api_key)
        source_id = k.get("id")
        doc["_sqlite_id"] = source_id if (source_id and _looks_like_uuid(source_id)) else str(uuid.uuid4())

        if existing:
            changed = False
            for f in API_KEY_FIELDS:
                if f not in doc or f not in existing.keys():
                    continue
                sv = existing[f]
                dv = doc.get(f)
                if f in ("active", "quota_throttle_enabled"):
                    if (bool(sv) if sv is not None else None) != to_bool(dv):
                        changed = True
                        break
                elif not values_equal(sv, dv):
                    changed = True
                    break
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE api_key {api_key[:8]}...")
            upsert_sqlite_api_key(sqlite_conn, existing, doc, dry_run)
            updated += 1
        else:
            print(f"  INSERT api_key {api_key[:8]}... (id={doc['_sqlite_id']})")
            upsert_sqlite_api_key(sqlite_conn, None, doc, dry_run)
            inserted += 1

    if delete_missing:
        postgres_apikeys = {k.get("api_key") for k in postgres_keys}
        for apikey, row in sqlite_keys.items():
            if apikey not in postgres_apikeys:
                print(f"  DELETE api_key {apikey[:8]}... (not in PostgreSQL)")
                if not dry_run:
                    sqlite_conn.execute("DELETE FROM api_keys WHERE id = ?", (row["id"],))
    print(f"  api_keys: inserted={inserted} updated={updated} unchanged={unchanged}")


# --- SQLite -> SQLite --------------------------------------------------------

def sync_sqlite_to_sqlite(
    source_conn: sqlite3.Connection,
    dest_conn: sqlite3.Connection,
    dry_run: bool,
    delete_missing: bool,
) -> None:
    print("== Syncing system_prompts: SQLite -> SQLite ==")
    source_prompts = read_sqlite_prompts(source_conn)
    dest_prompts = {
        r["name"]: r
        for r in dest_conn.execute("SELECT * FROM system_prompts").fetchall()
        if r["name"]
    }

    # Map source prompt id -> destination prompt id for api_keys.system_prompt_id.
    prompt_id_map: Dict[str, str] = {}
    inserted = updated = unchanged = 0

    for p in source_prompts:
        name = p.get("name")
        if not name:
            continue
        existing = dest_prompts.get(name)
        source_id = p.get("id")
        if existing:
            if source_id:
                prompt_id_map[source_id] = existing["id"]
            changed = any(
                f in p and not values_equal(existing[f], p.get(f))
                for f in PROMPT_FIELDS if f in existing.keys()
            )
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE prompt '{name}'")
            upsert_sqlite_prompt(dest_conn, existing, p, dry_run)
            updated += 1
        else:
            new_id = source_id if (source_id and _looks_like_uuid(source_id)) else str(uuid.uuid4())
            print(f"  INSERT prompt '{name}' (id={new_id})")
            doc = dict(p)
            doc["_sqlite_id"] = new_id
            upsert_sqlite_prompt(dest_conn, None, doc, dry_run)
            if source_id:
                prompt_id_map[source_id] = new_id
            inserted += 1

    if delete_missing:
        source_names = {p.get("name") for p in source_prompts}
        for name, row in dest_prompts.items():
            if name not in source_names:
                print(f"  DELETE prompt '{name}' (not in source SQLite)")
                if not dry_run:
                    dest_conn.execute("DELETE FROM system_prompts WHERE id = ?", (row["id"],))
    print(f"  prompts: inserted={inserted} updated={updated} unchanged={unchanged}")

    print("== Syncing api_keys: SQLite -> SQLite ==")
    source_keys = read_sqlite_api_keys(source_conn)
    dest_keys = {
        r["api_key"]: r
        for r in dest_conn.execute("SELECT * FROM api_keys").fetchall()
        if r["api_key"]
    }

    inserted = updated = unchanged = 0
    for k in source_keys:
        api_key = k.get("api_key")
        if not api_key:
            continue

        doc = dict(k)
        source_prompt_id = k.get("system_prompt_id")
        if source_prompt_id:
            translated = prompt_id_map.get(source_prompt_id)
            if translated:
                doc["system_prompt_id"] = translated
            else:
                print(f"  WARN api_key {api_key[:8]}... references unknown system_prompt_id {source_prompt_id}")
                doc["system_prompt_id"] = None

        existing = dest_keys.get(api_key)
        source_id = k.get("id")
        doc["_sqlite_id"] = source_id if (source_id and _looks_like_uuid(source_id)) else str(uuid.uuid4())

        if existing:
            changed = False
            for f in API_KEY_FIELDS:
                if f not in doc or f not in existing.keys():
                    continue
                sv = existing[f]
                dv = doc.get(f)
                if f in ("active", "quota_throttle_enabled"):
                    if (bool(sv) if sv is not None else None) != to_bool(dv):
                        changed = True
                        break
                elif not values_equal(sv, dv):
                    changed = True
                    break
            if not changed:
                unchanged += 1
                continue
            print(f"  UPDATE api_key {api_key[:8]}...")
            upsert_sqlite_api_key(dest_conn, existing, doc, dry_run)
            updated += 1
        else:
            print(f"  INSERT api_key {api_key[:8]}... (id={doc['_sqlite_id']})")
            upsert_sqlite_api_key(dest_conn, None, doc, dry_run)
            inserted += 1

    if delete_missing:
        source_apikeys = {k.get("api_key") for k in source_keys}
        for apikey, row in dest_keys.items():
            if apikey not in source_apikeys:
                print(f"  DELETE api_key {apikey[:8]}... (not in source SQLite)")
                if not dry_run:
                    dest_conn.execute("DELETE FROM api_keys WHERE id = ?", (row["id"],))
    print(f"  api_keys: inserted={inserted} updated={updated} unchanged={unchanged}")


def _looks_like_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync api_keys and system_prompts between auth backends.")
    parser.add_argument("--direction", required=True,
                        choices=["sqlite-to-mongo", "mongo-to-sqlite", "sqlite-to-sqlite",
                                 "sqlite-to-postgres", "postgres-to-sqlite"],
                        help="Copy direction. Destination is upserted from source.")
    parser.add_argument("-d", "--db", default=str(DEFAULT_DB),
                        help=(
                            "Path to SQLite database for MongoDB/PostgreSQL directions; "
                            f"destination SQLite database for sqlite-to-sqlite if --dest-db is omitted (default: {DEFAULT_DB})"
                        ))
    parser.add_argument("--source-db", default=None,
                        help="Source SQLite database path for sqlite-to-sqlite")
    parser.add_argument("--dest-db", default=None,
                        help="Destination SQLite database path for sqlite-to-sqlite")
    parser.add_argument("--mongo-db", default=None,
                        help="MongoDB database name (defaults to INTERNAL_SERVICES_MONGODB_DB or 'orbit')")
    parser.add_argument("--postgres-db", default=None,
                        help="PostgreSQL database name (defaults to INTERNAL_SERVICES_POSTGRES_DB or 'orbit')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show planned changes without writing to the destination")
    parser.add_argument("--delete-missing", action="store_true",
                        help="Delete rows in destination that are not present in source")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")

    db_path = Path(args.db).expanduser().resolve()
    if args.direction == "sqlite-to-sqlite":
        if not args.source_db:
            print("ERROR: --source-db is required for sqlite-to-sqlite", file=sys.stderr)
            return 2
        source_path = Path(args.source_db).expanduser().resolve()
        dest_path = Path(args.dest_db).expanduser().resolve() if args.dest_db else db_path
        if source_path == dest_path:
            print("ERROR: source and destination SQLite databases must be different files", file=sys.stderr)
            return 2

        print(f"Source SQLite:      {source_path}")
        print(f"Destination SQLite: {dest_path}")
        print(f"Direction: {args.direction}{' (DRY RUN)' if args.dry_run else ''}")
        print()

        source_conn = open_sqlite(source_path)
        dest_conn = open_sqlite(dest_path)
        try:
            sync_sqlite_to_sqlite(source_conn, dest_conn, args.dry_run, args.delete_missing)
            if not args.dry_run:
                dest_conn.commit()
        finally:
            source_conn.close()
            dest_conn.close()
    elif args.direction == "sqlite-to-postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as e:
            print(f"ERROR importing psycopg: {e}", file=sys.stderr)
            return 2

        pg_config = build_postgres_config(args.postgres_db)
        safe_host = f"{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"

        print(f"SQLite:    {db_path}")
        print(f"PostgreSQL: {safe_host}")
        print(f"Direction: {args.direction}{' (DRY RUN)' if args.dry_run else ''}")
        print()

        conn = open_sqlite(db_path)
        try:
            pg_conn = psycopg.connect(**pg_config, row_factory=dict_row)
        except Exception as e:
            print(f"ERROR connecting to PostgreSQL: {e}", file=sys.stderr)
            conn.close()
            return 2

        try:
            sync_sqlite_to_postgres(conn, pg_conn, args.dry_run, args.delete_missing)
            if not args.dry_run:
                pg_conn.commit()
            else:
                pg_conn.rollback()
        except Exception:
            pg_conn.rollback()
            raise
        finally:
            conn.close()
            pg_conn.close()
    elif args.direction == "postgres-to-sqlite":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as e:
            print(f"ERROR importing psycopg: {e}", file=sys.stderr)
            return 2

        pg_config = build_postgres_config(args.postgres_db)
        safe_host = f"{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"

        print(f"PostgreSQL: {safe_host}")
        print(f"SQLite:     {db_path}")
        print(f"Direction: {args.direction}{' (DRY RUN)' if args.dry_run else ''}")
        print()

        try:
            pg_conn = psycopg.connect(**pg_config, row_factory=dict_row)
        except Exception as e:
            print(f"ERROR connecting to PostgreSQL: {e}", file=sys.stderr)
            return 2

        conn = open_sqlite(db_path)
        try:
            sync_postgres_to_sqlite(pg_conn, conn, args.dry_run, args.delete_missing)
            if not args.dry_run:
                conn.commit()
        finally:
            conn.close()
            pg_conn.close()
    else:
        mongo_uri, default_db = build_mongo_uri()
        mongo_db_name = args.mongo_db or default_db

        print(f"SQLite:  {db_path}")
        print(f"MongoDB: {mongo_uri.split('@')[-1]} (db={mongo_db_name})")
        print(f"Direction: {args.direction}{' (DRY RUN)' if args.dry_run else ''}")
        print()

        conn = open_sqlite(db_path)
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        try:
            client.admin.command("ping")
        except Exception as e:
            print(f"ERROR connecting to MongoDB: {e}", file=sys.stderr)
            conn.close()
            client.close()
            return 2

        mdb = client[mongo_db_name]

        try:
            if args.direction == "sqlite-to-mongo":
                sync_sqlite_to_mongo(conn, mdb, args.dry_run, args.delete_missing)
            else:
                sync_mongo_to_sqlite(conn, mdb, args.dry_run, args.delete_missing)
                if not args.dry_run:
                    conn.commit()
        finally:
            conn.close()
            client.close()

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
