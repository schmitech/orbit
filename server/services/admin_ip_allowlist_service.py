"""
Admin IP Allowlist Service
==========================

Restricts *where* the admin panel and its admin-scoped ``/auth/*`` API
surface can be reached from, independent of identity — a defense-in-depth
layer on top of authentication and RBAC. This is deliberately not the same
control as :mod:`user_allowlist_service`, which gates *who* may be
provisioned an account at all.

The effective allowed set is the union of two sources, so a deployment can
start with a simple static config list and grow into DB-managed rules
without a breaking change:

- ``auth.admin_ip_allowlist.default_ranges`` — static config, always in effect.
- The ``admin_ip_rules`` table — managed at runtime via the admin panel's
  ``/auth/admin-ip-rules`` endpoints or ``orbit admin-ip``.

Loopback requests are handled separately by the enforcing middleware, not
here — this service only answers "is this IP in the allowed set", not
"should this request be exempt".
"""

import ipaddress
import logging
import threading
from datetime import datetime, UTC
from typing import Any, Optional

from services.database_service import (
    DatabaseService,
    DatabaseConnectionError,
    DatabaseDuplicateKeyError,
    DatabaseOperationError,
    DatabaseTimeoutError,
)
from utils.ip_utils import parse_trusted_networks

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 30

MODE_ALLOWLIST = "allowlist"
MODE_OPEN = "open"
MODES = (MODE_ALLOWLIST, MODE_OPEN)

COLLECTION = "admin_ip_rules"


class AdminIpRuleError(ValueError):
    """Raised when a submitted admin IP rule is malformed."""


def normalize_cidr(value: str) -> str:
    """Validate and normalize a CIDR/IP string for storage and matching."""
    if not isinstance(value, str) or not value.strip():
        raise AdminIpRuleError("CIDR cannot be empty")
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as e:
        raise AdminIpRuleError(f"Invalid IP address/CIDR: {e}")
    return str(network)


class AdminIpAllowlistService:
    """Loads, caches, and evaluates admin IP allowlist rules."""

    def __init__(self, config: dict[str, Any], database_service: DatabaseService):
        self.config = config
        self.database = database_service
        self.collection_name = COLLECTION

        admin_ip_config = (config.get("auth", {}) or {}).get("admin_ip_allowlist", {}) or {}
        self.enabled = bool(admin_ip_config.get("enabled", False))

        mode = str(admin_ip_config.get("mode", MODE_ALLOWLIST) or "").strip().lower()
        if mode not in MODES:
            logger.error(
                "Invalid auth.admin_ip_allowlist.mode %r; expected one of %s. "
                "Falling back to %r (deny-by-default).",
                mode, ", ".join(MODES), MODE_ALLOWLIST,
            )
            mode = MODE_ALLOWLIST
        self.mode = mode

        self.cache_ttl = admin_ip_config.get("cache_ttl", DEFAULT_CACHE_TTL_SECONDS)
        self.default_networks = parse_trusted_networks(
            admin_ip_config.get("default_ranges", []) or []
        )

        self._rule_networks: list[Any] = []
        self._loaded_at: Optional[datetime] = None
        self._lock = threading.Lock()

    @property
    def enforcing(self) -> bool:
        """Whether admin surfaces are actually gated by IP right now."""
        return self.enabled and self.mode == MODE_ALLOWLIST

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        with self._lock:
            self._loaded_at = None

    def _cache_is_fresh(self) -> bool:
        with self._lock:
            if self._loaded_at is None:
                return False
            return (datetime.now(UTC) - self._loaded_at).total_seconds() < self.cache_ttl

    async def _get_rule_networks(self) -> list[Any]:
        if self._cache_is_fresh():
            with self._lock:
                return self._rule_networks

        try:
            rules = await self.database.find_many(self.collection_name, {}, limit=1000)
        except (DatabaseConnectionError, DatabaseTimeoutError, DatabaseOperationError) as e:
            # Fail closed on the cached set, not the empty set: a database blip
            # must not silently widen (or narrow) who can reach the admin panel.
            logger.error(f"Failed to load admin IP rules, using last known rules: {str(e)}")
            with self._lock:
                return self._rule_networks
        except Exception as e:
            logger.error(f"Unexpected error loading admin IP rules: {str(e)}")
            with self._lock:
                return self._rule_networks

        networks = parse_trusted_networks([r.get("cidr") for r in rules if r.get("cidr")])
        with self._lock:
            self._rule_networks = networks
            self._loaded_at = datetime.now(UTC)
            return self._rule_networks

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    async def is_allowed(self, ip: str) -> bool:
        """Whether ``ip`` may reach a gated admin surface.

        Always True when not enforcing. An unparseable IP is denied rather
        than raising, matching the fail-closed posture of the rest of this
        control.
        """
        if not self.enforcing:
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        rule_networks = await self._get_rule_networks()
        return any(addr in net for net in self.default_networks) or any(
            addr in net for net in rule_networks
        )

    def allowed_under(self, extra_cidrs: list[str], ip: str) -> bool:
        """Whether ``ip`` would be allowed given ``default_ranges`` plus exactly
        ``extra_cidrs`` (uncached rule CIDR strings) — used to simulate a
        pending rule deletion before performing it (the self-lockout guard).
        """
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if any(addr in net for net in self.default_networks):
            return True
        return any(addr in net for net in parse_trusted_networks(extra_cidrs))

    # ------------------------------------------------------------------
    # Management
    # ------------------------------------------------------------------

    async def get_rule(self, rule_id: str) -> Optional[dict[str, Any]]:
        try:
            rule_id_converted = await self.database.ensure_id_is_object_id(rule_id)
        except ValueError:
            logger.warning(f"Invalid admin IP rule id format: {rule_id}")
            return None
        return await self.database.find_one(self.collection_name, {"_id": rule_id_converted})

    async def list_rules(self) -> list[dict[str, Any]]:
        """Return every configured rule, newest first."""
        rules = await self.database.find_many(self.collection_name, {}, limit=1000)
        return sorted(rules, key=lambda r: str(r.get("created_at") or ""), reverse=True)

    async def rules_excluding(self, rule_id: Optional[str]) -> list[dict[str, Any]]:
        """Every stored rule except ``rule_id`` (uncached, for simulation)."""
        rules = await self.list_rules()
        if rule_id is None:
            return rules
        return [r for r in rules if str(r.get("_id")) != str(rule_id)]

    async def add_rule(
        self,
        cidr: str,
        reason: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> dict[str, Any]:
        """Persist a rule and invalidate the cache. This can only ever widen
        the allowed set, so there is no self-lockout risk on add."""
        normalized = normalize_cidr(cidr)
        if reason is not None:
            reason = reason.strip()[:500] or None

        existing = await self.database.find_one(self.collection_name, {"cidr": normalized})
        if existing:
            raise AdminIpRuleError("An identical admin IP rule already exists")

        rule_doc = {
            "cidr": normalized,
            "reason": reason,
            "created_by": created_by,
            "created_at": datetime.now(UTC),
        }
        try:
            rule_id = await self.database.insert_one(self.collection_name, rule_doc)
        except DatabaseDuplicateKeyError:
            raise AdminIpRuleError("An identical admin IP rule already exists")
        rule_doc["_id"] = rule_id
        self.invalidate_cache()

        logger.info(f"Admin IP rule added: {normalized} by {created_by}")
        return rule_doc

    async def delete_rule(self, rule_id: str) -> bool:
        try:
            rule_id_converted = await self.database.ensure_id_is_object_id(rule_id)
        except ValueError:
            logger.warning(f"Invalid admin IP rule id format: {rule_id}")
            return False
        deleted = await self.database.delete_one(self.collection_name, {"_id": rule_id_converted})
        if deleted:
            self.invalidate_cache()
            logger.info(f"Admin IP rule removed: {rule_id}")
        return bool(deleted)
