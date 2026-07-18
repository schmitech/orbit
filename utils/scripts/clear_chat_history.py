#!/usr/bin/env python3
"""Clear chat history and related data from an Orbit database backend.

The tables/collections are cleared in dependency order so conversation state
can be reset without dropping the schema:

  1. feedback
  2. conversation_threads
  3. thread_datasets
  4. file_chunks
  5. uploaded_files
  6. chat_history
  7. audit_logs
  8. audit_admin_logs
  9. sessions

MongoDB and PostgreSQL connection settings are loaded from ``.env`` in the
project root and use the same ``INTERNAL_SERVICES_MONGODB_*`` and
``INTERNAL_SERVICES_POSTGRES_*`` variables as ``sync_auth_backends.py``.

Usage
-----
Run with the project venv activated. You can call the script from any directory.

  # Clear the default SQLite database
  python clear_chat_history.py

  # Clear a specific SQLite database
  python clear_chat_history.py --backend sqlite --db /path/to/orbit.db

  # Clear MongoDB or PostgreSQL
  python clear_chat_history.py --backend mongodb
  python clear_chat_history.py --backend postgres

  # Override the database name from .env
  python clear_chat_history.py --backend mongodb --mongo-db orbit_test
  python clear_chat_history.py --backend postgres --postgres-db orbit_test
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = Path(__file__).resolve().parent / "orbit.db"

# Keep children before their parents where relationships exist.
COLLECTIONS: Tuple[str, ...] = (
    "feedback",
    "conversation_threads",
    "thread_datasets",
    "file_chunks",
    "uploaded_files",
    "chat_history",
    "audit_logs",
    "audit_admin_logs",
    "sessions",
)


def build_mongo_uri() -> Tuple[str, str]:
    """Build a MongoDB URI from the internal-services environment variables."""
    host = os.getenv("INTERNAL_SERVICES_MONGODB_HOST", "localhost")
    port = os.getenv("INTERNAL_SERVICES_MONGODB_PORT", "27017")
    user = os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME", "")
    password = os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD", "")
    database = os.getenv("INTERNAL_SERVICES_MONGODB_DB", "orbit")

    if "mongodb.net" in host and user and password:
        uri = (
            f"mongodb+srv://{user}:{password}@{host}/{database}"
            "?retryWrites=true&w=majority"
        )
    elif user and password:
        uri = f"mongodb://{user}:{password}@{host}:{port}/{database}"
    else:
        uri = f"mongodb://{host}:{port}/{database}"
    return uri, database


def build_postgres_config(postgres_db: Optional[str] = None) -> Dict[str, Any]:
    """Build psycopg connection arguments from internal-services settings."""
    return {
        "host": os.getenv("INTERNAL_SERVICES_POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("INTERNAL_SERVICES_POSTGRES_PORT", "5432")),
        "dbname": postgres_db
        or os.getenv("INTERNAL_SERVICES_POSTGRES_DB", "orbit"),
        "user": os.getenv("INTERNAL_SERVICES_POSTGRES_USERNAME", "postgres"),
        "password": os.getenv("INTERNAL_SERVICES_POSTGRES_PASSWORD", ""),
        "sslmode": os.getenv("INTERNAL_SERVICES_POSTGRES_SSLMODE", "prefer"),
    }


def print_counts(counts: Dict[str, Tuple[int, int]]) -> None:
    for name in COLLECTIONS:
        before, after = counts[name]
        print(f"{name}: {before} -> {after}.")


def clear_sqlite(db_path: Path) -> None:
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        before = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in COLLECTIONS
        }
        for table in COLLECTIONS:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in COLLECTIONS
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print_counts({table: (before[table], after[table]) for table in COLLECTIONS})


def clear_mongodb(database: Any) -> None:
    before = {
        collection: database[collection].count_documents({})
        for collection in COLLECTIONS
    }
    for collection in COLLECTIONS:
        database[collection].delete_many({})
    after = {
        collection: database[collection].count_documents({})
        for collection in COLLECTIONS
    }
    print_counts(
        {
            collection: (before[collection], after[collection])
            for collection in COLLECTIONS
        }
    )


def clear_postgres(conn: Any) -> None:
    before = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in COLLECTIONS
    }
    try:
        for table in COLLECTIONS:
            conn.execute(f"DELETE FROM {table}")
        after = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in COLLECTIONS
        }
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print_counts({table: (before[table], after[table]) for table in COLLECTIONS})


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clear chat history and related data from an Orbit backend."
    )
    parser.add_argument(
        "--backend",
        choices=("sqlite", "mongodb", "mongdb", "postgres"),
        default="sqlite",
        help=(
            "Database backend to clear (default: sqlite). "
            "'mongdb' is accepted as an alias for 'mongodb'."
        ),
    )
    parser.add_argument(
        "-d",
        "--db",
        default=str(DEFAULT_DB),
        metavar="PATH",
        help=f"Path to the SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--mongo-db",
        default=None,
        help="MongoDB database name (defaults to INTERNAL_SERVICES_MONGODB_DB or 'orbit')",
    )
    parser.add_argument(
        "--postgres-db",
        default=None,
        help="PostgreSQL database name (defaults to INTERNAL_SERVICES_POSTGRES_DB or 'orbit')",
    )
    return parser.parse_args(argv)


def load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is required for MongoDB and PostgreSQL backends"
        ) from exc
    load_dotenv(PROJECT_ROOT / ".env")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    backend = "mongodb" if args.backend == "mongdb" else args.backend

    try:
        if backend == "sqlite":
            db_path = Path(args.db).expanduser().resolve()
            print(f"SQLite: {db_path}\n")
            clear_sqlite(db_path)
        elif backend == "mongodb":
            load_project_env()
            try:
                from pymongo import MongoClient
            except ImportError as exc:
                raise RuntimeError("pymongo is required for the MongoDB backend") from exc

            mongo_uri, default_db = build_mongo_uri()
            mongo_db_name = args.mongo_db or default_db
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            try:
                client.admin.command("ping")
                print(f"MongoDB: {mongo_uri.split('@')[-1]} (db={mongo_db_name})\n")
                clear_mongodb(client[mongo_db_name])
            finally:
                client.close()
        else:
            load_project_env()
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("psycopg is required for the PostgreSQL backend") from exc

            pg_config = build_postgres_config(args.postgres_db)
            safe_host = f"{pg_config['host']}:{pg_config['port']}/{pg_config['dbname']}"
            print(f"PostgreSQL: {safe_host}\n")
            conn = psycopg.connect(**pg_config)
            try:
                clear_postgres(conn)
            finally:
                conn.close()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
