#!/usr/bin/env python3
"""Reset the MongoDB backend database to a fresh, empty ORBIT state.

Drops every ORBIT collection in the target MongoDB database. MongoDB is
schemaless, so there is nothing to "recreate" the way reset_postgres_db.py
recreates Postgres tables — once the collections are dropped, the next
server startup (or each service's own `initialize()`, e.g. ApiKeyService,
ChatHistoryService) recreates any indexes it needs on first use, exactly as
it would against a brand-new empty database.

The canonical collection list starts from SQLiteService._schema (the logical
schema — table/collection names — is identical across all three backends,
see docs/sqlite-schema.md), then applies any MongoDB-specific renames found
in config/config.yaml (internal_services.mongodb.*_collection,
chat_history.collection_name, internal_services.audit.collection_name /
admin_events.collection_name) — a deployment using one of those renames would
otherwise have its data silently left behind in the renamed collection while
this script reports the database empty.

All data in the ORBIT collections (users, api_keys, system_prompts,
chat_history, audit_logs, ...) is permanently destroyed. Afterwards, use
sync_auth_backends.py to reload api_keys/system_prompts from a SQLite (or
another backend's) backup:

  python sync_auth_backends.py --direction sqlite-to-mongo \\
      --db /path/to/backup/orbit.db

Environment
-----------
Loads `.env` from the project root for MongoDB credentials (same as
sync_auth_backends.py):
  INTERNAL_SERVICES_MONGODB_HOST
  INTERNAL_SERVICES_MONGODB_PORT
  INTERNAL_SERVICES_MONGODB_USERNAME
  INTERNAL_SERVICES_MONGODB_PASSWORD
  INTERNAL_SERVICES_MONGODB_DB   (default: orbit)

Usage
-----
Run with the project venv activated.

  # Prompts for confirmation (must type the database name back)
  python reset_mongo_db.py

  # Skip the confirmation prompt (e.g. for scripted use)
  python reset_mongo_db.py --yes

  # Target a different database name than INTERNAL_SERVICES_MONGODB_DB.
  # Only selects the target database for the drop — the connection/auth URI
  # is still built from INTERNAL_SERVICES_MONGODB_DB (see build_mongo_uri()),
  # so this does not change which database credentials authenticate against.
  python reset_mongo_db.py --mongo-db orbit_staging --yes
"""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from services.sqlite_service import SQLiteService  # noqa: E402


def build_mongo_uri() -> str:
    """Connection URI built from the configured database only (same as
    sync_auth_backends.py's build_mongo_uri()). A `--mongo-db` override must
    never be substituted in here: without an explicit `authSource`, MongoDB
    authenticates against the URI's database, so doing so could authenticate
    against a database the configured credentials have no access to even
    though they're valid against the configured one. The override instead
    only selects which database's collections get dropped, via `client[db_name]`.
    """
    host = os.getenv("INTERNAL_SERVICES_MONGODB_HOST", "localhost")
    port = os.getenv("INTERNAL_SERVICES_MONGODB_PORT", "27017")
    user = os.getenv("INTERNAL_SERVICES_MONGODB_USERNAME", "")
    pw = os.getenv("INTERNAL_SERVICES_MONGODB_PASSWORD", "")
    db = os.getenv("INTERNAL_SERVICES_MONGODB_DB", "orbit")

    if "mongodb.net" in host and user and pw:
        return f"mongodb+srv://{user}:{pw}@{host}/{db}?retryWrites=true&w=majority"
    elif user and pw:
        return f"mongodb://{user}:{pw}@{host}:{port}/{db}"
    else:
        return f"mongodb://{host}:{port}/{db}"


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Best-effort read of config/config.yaml for collection-name overrides.
    Not full config_manager.py-style import resolution — only the top-level
    file is read, since collection-name overrides are set directly there in
    practice — but ${VAR}/${VAR:-default} placeholders ARE resolved (see
    _resolve_placeholder()), since a raw, unresolved placeholder string would
    silently become a bogus actual collection name."""
    path = config_path or (PROJECT_ROOT / "config" / "config.yaml")
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception:
        pass
    return {}


_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(:-(.*))?\}$")


def _resolve_placeholder(value: Any, field_name: str) -> Any:
    """Resolve a config_manager.py-style ${VAR} / ${VAR:-default} placeholder
    against the process environment. Non-string values and plain literals are
    returned unchanged.

    Aborts (SystemExit) on an unresolved reference (no default and the env
    var is unset) rather than silently using the literal "${VAR}" string as a
    collection name — that would make this script report the database empty
    while real data sits untouched under the actual configured name.
    """
    if not isinstance(value, str):
        return value
    match = _PLACEHOLDER_RE.match(value.strip())
    if not match:
        return value
    env_var, has_default, default = match.group(1), match.group(2), match.group(3)
    resolved = os.environ.get(env_var)
    if has_default is not None:
        # Matches config_manager.py's replace_env_vars(): with a default,
        # an empty-string env var counts as unset too, not as "set to empty".
        return resolved if resolved else default
    if resolved is not None:
        return resolved
    print(
        f"ERROR: config value for '{field_name}' is '{value}', referencing environment "
        f"variable {env_var}, which is not set and has no default. Set {env_var} "
        "(or edit config.yaml) so the real configured collection name can be resolved — "
        "proceeding with the literal placeholder string would silently miss the actual collection.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def resolve_collection_names(config: Dict[str, Any]) -> list:
    """The ORBIT collection names to drop: SQLiteService._schema's logical
    names, with any MongoDB-specific rename from config applied — mirrors
    exactly how each service (ApiKeyService, AuthService, PromptService,
    ToolSkillService, ChatHistoryService, the audit strategies) resolves its
    own collection name."""
    SQLiteService._instances.clear()
    default_names = list(SQLiteService({})._schema.keys())

    internal = config.get("internal_services", {}) or {}
    mongodb_cfg = internal.get("mongodb", {}) or {}
    top_level_mongodb_cfg = config.get("mongodb", {}) or {}
    audit_cfg = internal.get("audit", {}) or {}
    admin_events_cfg = audit_cfg.get("admin_events", {}) or {}
    chat_history_cfg = config.get("chat_history", {}) or {}

    # logical name -> resolved collection name, only for names that have a
    # configurable rename; everything else keeps its default.
    raw_overrides = {
        "users": mongodb_cfg.get("users_collection", "users"),
        "sessions": mongodb_cfg.get("sessions_collection", "sessions"),
        "api_keys": (
            mongodb_cfg.get("apikey_collection")
            or top_level_mongodb_cfg.get("apikey_collection")
            or "api_keys"
        ),
        "system_prompts": mongodb_cfg.get("prompts_collection", "system_prompts"),
        "tool_skills": mongodb_cfg.get("tool_skills_collection", "tool_skills"),
        "chat_history": chat_history_cfg.get("collection_name", "chat_history"),
        "audit_logs": audit_cfg.get("collection_name", "audit_logs"),
        "audit_admin_logs": admin_events_cfg.get("collection_name", "audit_admin_logs"),
    }
    overrides = {
        field: _resolve_placeholder(value, field) for field, value in raw_overrides.items()
    }

    return [overrides.get(name, name) for name in default_names]


def reset(uri: str, db_name: str, names: list) -> None:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as e:
        print(f"ERROR connecting to MongoDB: {e}", file=sys.stderr)
        raise SystemExit(2)

    db = client[db_name]
    existing = set(db.list_collection_names())
    for name in names:
        if name in existing:
            print(f"  DROP COLLECTION {name}")
            db.drop_collection(name)
        else:
            print(f"  (skip {name}, does not exist)")
    client.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Drop all ORBIT collections in a MongoDB database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mongo-db", default=None,
        help=(
            "MongoDB database name to reset (defaults to INTERNAL_SERVICES_MONGODB_DB or "
            "'orbit'). Only selects which database's collections are dropped — does not "
            "change the connection/auth URI; see build_mongo_uri()."
        ),
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config.yaml to read collection-name overrides from (default: config/config.yaml)",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation prompt",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    uri = build_mongo_uri()
    db_name = args.mongo_db or os.getenv("INTERNAL_SERVICES_MONGODB_DB", "orbit")
    config = load_config(Path(args.config) if args.config else None)
    names = resolve_collection_names(config)

    safe_target = f"{uri.split('@')[-1]} (db={db_name})"
    print(f"This will DROP ALL ORBIT COLLECTIONS in MongoDB database: {safe_target}")
    print("All data (users, api_keys, system_prompts, chat_history, audit_logs, ...) will be permanently lost.")
    print(f"Collections: {', '.join(names)}")

    if not args.yes:
        confirm = input(f"\nType the database name ('{db_name}') to confirm: ")
        if confirm != db_name:
            print("Confirmation did not match. Aborting.", file=sys.stderr)
            return 1

    try:
        reset(uri, db_name, names)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR resetting MongoDB database: {e}", file=sys.stderr)
        return 2

    print("\nDone. Database is now empty — collections/indexes are recreated on first use.")
    sync_cmd = (
        "python utils/scripts/sync_auth_backends.py --direction sqlite-to-mongo "
        f"--db /path/to/backup/orbit.db --mongo-db {db_name}"
    )
    print(f"Next, reload api_keys/system_prompts from a backup, e.g. (run from the project root):\n  {sync_cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
