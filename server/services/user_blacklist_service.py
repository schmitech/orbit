"""
User Blacklist Service
======================

Pattern-based denial of authenticated identities, enforced at the single point
where ORBIT resolves a caller's identity (``AuthService.validate_token``).

This is deliberately distinct from a user's ``active`` flag. Deactivation needs
an existing row in the ``users`` table, so it can only stop someone who has
already signed in at least once. A blacklist rule is a *pattern*, which lets an
operator block an abusive external user before their first login JIT-provisions
them, or block an entire disposable-email domain in one entry.

Rules are matched with shell-style wildcards (``*`` and ``?``) against the
lowercased value, so ``*@spam-domain.com`` and ``entra:abc*`` both work. An
exact string with no wildcard characters simply matches that one value.

Because matching happens in Python rather than SQL, the (small) rule set is
cached in memory and re-read at most once per ``cache_ttl`` seconds. Writes
invalidate the local cache immediately; under ``performance.workers > 1``,
sibling workers pick up a new rule within the TTL. Existing sessions are
revoked at write time, so an in-flight abuser is cut off at once regardless.
"""

import fnmatch
import logging
import threading
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from services.database_service import (
    DatabaseService,
    DatabaseConnectionError,
    DatabaseDuplicateKeyError,
    DatabaseOperationError,
    DatabaseTimeoutError,
)

logger = logging.getLogger(__name__)

# The identity field a rule's pattern is matched against.
ENTRY_TYPES = ("email", "user_id", "username")

DEFAULT_CACHE_TTL_SECONDS = 30

# Bounds a single rule so a pathological pattern can't be persisted.
MAX_PATTERN_LENGTH = 320  # RFC 5321 maximum email length
MAX_REASON_LENGTH = 500


class BlacklistRuleError(ValueError):
    """Raised when a submitted blacklist rule is malformed."""


def normalize_pattern(pattern: str) -> str:
    """Normalize a rule pattern for storage and matching."""
    if not isinstance(pattern, str):
        raise BlacklistRuleError("Pattern must be a string")
    normalized = pattern.strip().lower()
    if not normalized:
        raise BlacklistRuleError("Pattern cannot be empty")
    if len(normalized) > MAX_PATTERN_LENGTH:
        raise BlacklistRuleError(f"Pattern cannot exceed {MAX_PATTERN_LENGTH} characters")
    if normalized.strip("*?") == "":
        # "*" would block every caller including every admin.
        raise BlacklistRuleError("Pattern must contain at least one literal character")
    return normalized


def matches(pattern: str, value: Optional[str]) -> bool:
    """Return whether a normalized pattern matches an identity value."""
    if not value:
        return False
    return fnmatch.fnmatchcase(str(value).strip().lower(), pattern)


class UserBlacklistService:
    """Loads, caches, and evaluates user blacklist rules.

    The storage, caching, matching, and CRUD mechanics here are identical for a
    deny-list and an allow-list - only the collection, the config sub-key, and
    the wording differ. Subclasses override the three class attributes below;
    see ``user_allowlist_service.UserAllowlistService``.
    """

    #: Database collection holding this rule set.
    COLLECTION = "user_blacklist"
    #: Sub-key under ``auth:`` supplying ``cache_ttl``.
    CONFIG_KEY = "blacklist"
    #: Human-readable rule-set name used in errors and log lines.
    LABEL = "blacklist"

    def __init__(self, config: Dict[str, Any], database_service: DatabaseService):
        self.config = config
        self.database = database_service
        self.collection_name = self.COLLECTION

        rules_config = config.get("auth", {}).get(self.CONFIG_KEY, {}) or {}
        self.cache_ttl = rules_config.get("cache_ttl", DEFAULT_CACHE_TTL_SECONDS)

        # Resolve the users/sessions collection names the same way AuthService
        # does. Hardcoding "users"/"sessions" silently breaks session revocation
        # on a MongoDB deployment that configures its own collection names: the
        # scan finds no identities, so a write reports success having revoked
        # nothing - the blacklist would fail to cut off an in-flight abuser, and
        # allowlist removal would fail to withdraw access.
        backend_type = (
            config.get("internal_services", {}).get("backend", {}).get("type", "mongodb")
        )
        if backend_type == "mongodb":
            mongodb_config = config.get("internal_services", {}).get("mongodb", {}) or {}
            self.users_collection_name = mongodb_config.get("users_collection", "users")
            self.sessions_collection_name = mongodb_config.get(
                "sessions_collection", "sessions"
            )
        else:
            # SQL backends use fixed table names.
            self.users_collection_name = "users"
            self.sessions_collection_name = "sessions"

        self._rules: List[Dict[str, Any]] = []
        self._loaded_at: Optional[datetime] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        """Force the next evaluation to re-read rules from the database."""
        with self._lock:
            self._loaded_at = None

    def _cache_is_fresh(self) -> bool:
        with self._lock:
            if self._loaded_at is None:
                return False
            age = (datetime.now(UTC) - self._loaded_at).total_seconds()
            return age < self.cache_ttl

    async def _get_rules(self) -> List[Dict[str, Any]]:
        """Return the cached rule set, refreshing it when stale."""
        if self._cache_is_fresh():
            with self._lock:
                return self._rules

        try:
            rules = await self.database.find_many(self.collection_name, {}, limit=1000)
        except (DatabaseConnectionError, DatabaseTimeoutError, DatabaseOperationError) as e:
            # Fail closed on the cached set rather than the empty set: a database
            # blip must not silently un-block everyone. If nothing was ever
            # loaded the list is empty, matching today's unrestricted behavior.
            logger.error(f"Failed to load user {self.LABEL}, using last known rules: {str(e)}")
            with self._lock:
                return self._rules
        except Exception as e:
            logger.error(f"Unexpected error loading user {self.LABEL}: {str(e)}")
            with self._lock:
                return self._rules

        with self._lock:
            self._rules = rules
            self._loaded_at = datetime.now(UTC)
            return self._rules

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def match_identity(
        self,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the first rule blocking this identity, or None if allowed."""
        return self.match_in(
            await self._get_rules(), user_id=user_id, email=email, username=username
        )

    def match_in(
        self,
        rules: List[Dict[str, Any]],
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the first of ``rules`` matching this identity, or None.

        Split out from :meth:`match_identity` so a caller can evaluate a
        hypothetical rule set - e.g. asking whether an allowlist rule's removal
        would revoke the requesting administrator's own clearance.
        """
        values = {"user_id": user_id, "email": email, "username": username}
        for rule in rules:
            entry_type = rule.get("entry_type")
            pattern = rule.get("pattern")
            if not pattern or entry_type not in values:
                continue
            if matches(pattern, values[entry_type]):
                return rule
        return None

    async def match_user(self, user: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return the first rule blocking a user record, or None if allowed.

        Accepts both raw database rows (``_id``) and auth-context dicts (``id``).
        """
        raw_id = user.get("id") or user.get("_id")
        return await self.match_identity(
            user_id=str(raw_id) if raw_id else None,
            email=user.get("email"),
            username=user.get("username"),
        )

    async def is_blocked(self, user: Dict[str, Any]) -> bool:
        """Convenience predicate over :meth:`match_user`."""
        return await self.match_user(user) is not None

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    def _validate_rule_fields(
        self, pattern: str, entry_type: str, reason: Optional[str]
    ) -> tuple:
        """Validate and normalize the writable fields shared by add and update."""
        if entry_type not in ENTRY_TYPES:
            raise BlacklistRuleError(
                f"entry_type must be one of: {', '.join(ENTRY_TYPES)}"
            )
        normalized = normalize_pattern(pattern)
        if reason is not None:
            reason = reason.strip()[:MAX_REASON_LENGTH] or None
        return normalized, reason

    async def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one rule by id, or None if the id is unknown or malformed."""
        try:
            rule_id_converted = await self.database.ensure_id_is_object_id(rule_id)
        except ValueError:
            logger.warning(f"Invalid {self.LABEL} rule id format: {rule_id}")
            return None
        return await self.database.find_one(
            self.collection_name, {"_id": rule_id_converted}
        )

    async def list_rules(self) -> List[Dict[str, Any]]:
        """Return every configured rule, newest first."""
        rules = await self.database.find_many(self.collection_name, {}, limit=1000)
        return sorted(rules, key=lambda r: str(r.get("created_at") or ""), reverse=True)

    async def find_matching_users(self, pattern: str, entry_type: str) -> List[Dict[str, Any]]:
        """Return existing user records a rule would block.

        Used both to revoke sessions when a rule is added and to warn an
        operator before they lock themselves out.
        """
        users = await self.database.find_many(
            self.users_collection_name, {}, limit=10000
        )
        matched = []
        for user in users:
            value = {
                "user_id": str(user.get("_id") or ""),
                "email": user.get("email"),
                "username": user.get("username"),
            }.get(entry_type)
            if matches(pattern, value):
                matched.append(user)
        return matched

    async def revoke_sessions_for(self, users: List[Dict[str, Any]]) -> int:
        """Delete active sessions for the given users; returns the count removed."""
        revoked = 0
        for user in users:
            try:
                revoked += await self.database.delete_many(
                    self.sessions_collection_name, {"user_id": user["_id"]}
                )
            except Exception as e:
                logger.error(
                    f"Failed to revoke sessions for user {user.get('username')}: {str(e)}"
                )
        return revoked

    async def add_rule(
        self,
        pattern: str,
        entry_type: str,
        reason: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Persist a rule, revoke matching sessions, and invalidate the cache.

        Returns the stored rule with a ``revoked_sessions`` count attached.
        """
        normalized, reason = self._validate_rule_fields(pattern, entry_type, reason)

        existing = await self.database.find_one(
            self.collection_name, {"pattern": normalized, "entry_type": entry_type}
        )
        if existing:
            raise BlacklistRuleError(f"An identical {self.LABEL} rule already exists")

        rule_doc = {
            "pattern": normalized,
            "entry_type": entry_type,
            "reason": reason,
            "created_by": created_by,
            "created_at": datetime.now(UTC),
        }
        try:
            rule_id = await self.database.insert_one(self.collection_name, rule_doc)
        except DatabaseDuplicateKeyError:
            # The find_one above is advisory only - two concurrent creates can
            # both pass it. The compound unique index is what actually decides,
            # so report the loser as a duplicate rather than a server error.
            raise BlacklistRuleError(f"An identical {self.LABEL} rule already exists")
        rule_doc["_id"] = rule_id
        self.invalidate_cache()

        matched_users = await self.find_matching_users(normalized, entry_type)
        rule_doc["revoked_sessions"] = await self.revoke_sessions_for(matched_users)
        rule_doc["matched_users"] = len(matched_users)

        logger.info(
            f"{self.LABEL.capitalize()} rule added: {entry_type}={normalized} "
            f"(matched {len(matched_users)} existing users) by {created_by}"
        )
        return rule_doc

    async def update_rule(
        self,
        rule_id: str,
        pattern: str,
        entry_type: str,
        reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Edit an existing rule in place, returning it with revocation counts.

        Returns None if the rule id is unknown, so callers can 404.

        Editing a pattern changes *who* is blocked, so this re-runs the same
        session revocation as creation against the new pattern's matches. Users
        the rule no longer matches keep whatever sessions they still have - it
        never mints access, it only stops being the thing that denies them.
        """
        normalized, reason = self._validate_rule_fields(pattern, entry_type, reason)

        current = await self.get_rule(rule_id)
        if not current:
            return None

        unchanged = (
            current.get("pattern") == normalized
            and current.get("entry_type") == entry_type
            and (current.get("reason") or None) == reason
        )
        if unchanged:
            # Nothing to write, and no sessions to revoke that adding the rule
            # wouldn't already have taken.
            return {**current, "matched_users": 0, "revoked_sessions": 0}

        # Reject a collision with a *different* rule; matching itself is fine.
        clash = await self.database.find_one(
            self.collection_name, {"pattern": normalized, "entry_type": entry_type}
        )
        if clash and str(clash.get("_id")) != str(current.get("_id")):
            raise BlacklistRuleError(f"An identical {self.LABEL} rule already exists")

        # No backend raises DatabaseDuplicateKeyError from update_one the way
        # insert_one does - SQLite, Postgres, and MongoDB each catch every
        # exception, log it, and return False - so a uniqueness violation
        # arrives here only as a falsy result. Treat that as a failed write:
        # reporting success would revoke sessions for a rule that was never
        # actually changed.
        updated_ok = await self.database.update_one(
            self.collection_name,
            {"_id": current["_id"]},
            {"$set": {
                "pattern": normalized,
                "entry_type": entry_type,
                "reason": reason,
            }},
        )
        if not updated_ok:
            # Distinguish the likely cause rather than blaming the caller for a
            # database outage: if another rule now holds this
            # (entry_type, pattern), a concurrent write beat us to it.
            raced = await self.database.find_one(
                self.collection_name,
                {"pattern": normalized, "entry_type": entry_type},
            )
            if raced and str(raced.get("_id")) != str(current.get("_id")):
                raise BlacklistRuleError(
                    f"An identical {self.LABEL} rule already exists"
                )
            raise DatabaseOperationError(
                f"Failed to update {self.LABEL} rule {rule_id}"
            )

        self.invalidate_cache()

        updated = {
            **current,
            "pattern": normalized,
            "entry_type": entry_type,
            "reason": reason,
        }
        matched_users = await self.find_matching_users(normalized, entry_type)
        updated["revoked_sessions"] = await self.revoke_sessions_for(matched_users)
        updated["matched_users"] = len(matched_users)

        logger.info(
            f"{self.LABEL.capitalize()} rule {rule_id} updated: {entry_type}={normalized} "
            f"(matched {len(matched_users)} existing users)"
        )
        return updated

    async def delete_rule(self, rule_id: str) -> bool:
        """Remove a rule by id and invalidate the cache."""
        # Let the backend coerce the id (ObjectId for Mongo, str elsewhere).
        # A malformed id is "not found", not a server error.
        try:
            rule_id_converted = await self.database.ensure_id_is_object_id(rule_id)
        except ValueError:
            logger.warning(f"Invalid {self.LABEL} rule id format: {rule_id}")
            return False
        deleted = await self.database.delete_one(
            self.collection_name, {"_id": rule_id_converted}
        )
        if deleted:
            self.invalidate_cache()
            logger.info(f"{self.LABEL.capitalize()} rule removed: {rule_id}")
        return bool(deleted)
