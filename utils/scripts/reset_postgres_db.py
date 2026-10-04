#!/usr/bin/env python3
"""Reset the PostgreSQL backend database to a fresh ORBIT schema.

Drops every ORBIT table in the target PostgreSQL database, then recreates
them from the current code's schema (`PostgresService._schema`/`_indexes`) —
the same `CREATE TABLE IF NOT EXISTS` / index-creation path the server runs
on startup, just against an empty database. Use this when there is no local
SQLite database to copy from and the Postgres database's schema predates a
breaking schema change (e.g. the removal of runtime migrations), so it needs
to be rebuilt from scratch rather than patched column by column.

All data in the ORBIT tables (users, api_keys, system_prompts, chat_history,
audit_logs, ...) is permanently destroyed. Afterwards, use
sync_auth_backends.py to reload api_keys/system_prompts from a SQLite (or
another Postgres) backup:

  python sync_auth_backends.py --direction sqlite-to-postgres \\
      --db /path/to/backup/orbit.db

Environment
-----------
Loads `.env` from the project root for PostgreSQL credentials (same as
sync_auth_backends.py):
  INTERNAL_SERVICES_POSTGRES_HOST
  INTERNAL_SERVICES_POSTGRES_PORT
  INTERNAL_SERVICES_POSTGRES_USERNAME
  INTERNAL_SERVICES_POSTGRES_PASSWORD
  INTERNAL_SERVICES_POSTGRES_DB       (default: orbit)
  INTERNAL_SERVICES_POSTGRES_SSLMODE  (default: prefer)

Usage
-----
Run with the project venv activated.

  # Prompts for confirmation (must type the database name back)
  python reset_postgres_db.py

  # Skip the confirmation prompt (e.g. for scripted use)
  python reset_postgres_db.py --yes

  # Target a different database name than INTERNAL_SERVICES_POSTGRES_DB
  python reset_postgres_db.py --postgres-db orbit_staging --yes
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from services.postgres_service import PostgresService  # noqa: E402


def build_postgres_config(postgres_db: Optional[str] = None) -> Dict[str, Any]:
    """Build the nested config dict PostgresService expects, from the same
    env vars sync_auth_backends.py's build_postgres_config() reads."""
    return {
        "internal_services": {
            "backend": {
                "type": "postgres",
                "postgres": {
                    "host": os.getenv("INTERNAL_SERVICES_POSTGRES_HOST", "localhost"),
                    "port": int(os.getenv("INTERNAL_SERVICES_POSTGRES_PORT", "5432")),
                    "database": postgres_db or os.getenv("INTERNAL_SERVICES_POSTGRES_DB", "orbit"),
                    "username": os.getenv("INTERNAL_SERVICES_POSTGRES_USERNAME", "postgres"),
                    "password": os.getenv("INTERNAL_SERVICES_POSTGRES_PASSWORD", ""),
                    "sslmode": os.getenv("INTERNAL_SERVICES_POSTGRES_SSLMODE", "prefer"),
                },
            }
        }
    }


async def reset(config: Dict[str, Any]) -> None:
    # Fresh instance regardless of any cached singleton from a prior import in
    # this process (there shouldn't be one, but mirrors the other scripts'
    # clear_cache() pattern for safety).
    PostgresService._instances.clear()
    service = PostgresService(config)

    # Open one connection (service._connect_db(), the same psycopg connection
    # setup PostgresService.initialize() uses) to drop every table this
    # service's own schema knows about, CASCADE so dependent objects (e.g.
    # file_chunks' FOREIGN KEY to uploaded_files) are dropped too.
    loop = asyncio.get_running_loop()
    connection = await loop.run_in_executor(service.executor, service._connect_db)
    try:
        cursor = connection.cursor()
        for table_name in service._schema:
            print(f"  DROP TABLE IF EXISTS {table_name} CASCADE")
            cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        connection.commit()
    finally:
        connection.close()

    # Recreate every table/index from the current code's schema — identical to
    # what happens when the server starts up against an empty Postgres database.
    print("\nRecreating schema from current code...")
    await service.initialize()
    print("Schema recreated.")
    service.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drop and recreate all ORBIT tables in a PostgreSQL database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--postgres-db", default=None,
        help="PostgreSQL database name (defaults to INTERNAL_SERVICES_POSTGRES_DB or 'orbit')",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation prompt",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    config = build_postgres_config(args.postgres_db)
    pg = config["internal_services"]["backend"]["postgres"]
    target = f"{pg['host']}:{pg['port']}/{pg['database']}"

    print(f"This will DROP ALL ORBIT TABLES in PostgreSQL database: {target}")
    print("All data (users, api_keys, system_prompts, chat_history, audit_logs, ...) will be permanently lost.")

    if not args.yes:
        confirm = input(f"\nType the database name ('{pg['database']}') to confirm: ")
        if confirm != pg["database"]:
            print("Confirmation did not match. Aborting.", file=sys.stderr)
            return 1

    try:
        asyncio.run(reset(config))
    except Exception as e:
        print(f"ERROR resetting PostgreSQL database: {e}", file=sys.stderr)
        return 2

    print("\nDone. Database now has a fresh ORBIT schema (empty).")
    sync_cmd = (
        "python utils/scripts/sync_auth_backends.py --direction sqlite-to-postgres "
        "--db /path/to/backup/orbit.db"
        f" --postgres-db {pg['database']}"
    )
    print(f"Next, reload api_keys/system_prompts from a backup, e.g. (run from the project root):\n  {sync_cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
