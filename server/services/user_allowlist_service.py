"""
User Allowlist Service
======================

Pattern-based *pre-clearing* of external identities: the mirror image of
``user_blacklist_service``. Where a blacklist rule says "not this identity", an
allowlist rule says "only these identities".

Why this exists
---------------

ORBIT just-in-time provisions a local user for any subject an enabled identity
provider will authenticate (``AuthService._find_or_create_external_user``). With
only a deny-list, the resulting posture is "everyone the IdP will authenticate
is an ORBIT user, minus whoever we explicitly blocked" - untenable against an
Auth0 tenant with open signup or social connections, where the set of
authenticable subjects is effectively the internet. Blocking abusers one subject
at a time is whack-a-mole when the IdP mints new ones freely.

Under ``auth.providers.access_control: allowlist`` an external subject gains no
ORBIT identity at all - no ``users`` row, no session, on any surface - unless it
matches a rule here.

Semantics that differ from the blacklist
----------------------------------------

- **Empty means deny, not allow.** An empty deny-list blocks nobody; an empty
  allow-list (in ``allowlist`` mode) admits nobody. This is what makes the
  control fail closed.
- **Local users are never subject to it.** Only identities carrying a
  ``provider`` are checked, so the bootstrap ``admin`` and every password
  account keep working regardless of what is (or isn't) in here.
- **Session revocation is inverted.** Adding a deny rule must revoke sessions;
  adding an allow rule grants nothing and revokes nothing. It is *removing* or
  *narrowing* an allow rule that cuts users off, so that revocation lives in the
  route layer rather than in ``add_rule``.
- **Deny wins.** ``AuthService`` evaluates the blacklist first, so a deny rule
  always beats an allow rule covering the same identity.

Everything else - wildcard matching, the TTL cache with last-known-good
fallback, rule validation, and CRUD - is inherited unchanged.
"""

import logging
from typing import Any, Dict, Optional

from services.user_blacklist_service import (
    BlacklistRuleError,
    UserBlacklistService,
)

logger = logging.getLogger(__name__)

# The rule-validation error is shared: the same malformed-pattern rules apply to
# both rule sets, and the message carries the rule-set label. Aliased so callers
# reading allowlist code aren't sent hunting through the blacklist module.
AllowlistRuleError = BlacklistRuleError

#: ``auth.providers.access_control`` values.
ACCESS_CONTROL_ALLOWLIST = "allowlist"
ACCESS_CONTROL_OPEN = "open"
ACCESS_CONTROL_MODES = (ACCESS_CONTROL_ALLOWLIST, ACCESS_CONTROL_OPEN)


class UserAllowlistService(UserBlacklistService):
    """Loads, caches, and evaluates external-identity allowlist rules."""

    COLLECTION = "user_allowlist"
    CONFIG_KEY = "allowlist"
    LABEL = "allowlist"

    def __init__(self, config: Dict[str, Any], database_service):
        super().__init__(config, database_service)

        providers_config = (config.get("auth", {}) or {}).get("providers", {}) or {}
        # With no external provider enabled there are no external identities to
        # gate, so enforcement would only be a surprise. The mode is still parsed
        # and reported so a misconfiguration is visible before providers go live.
        self._providers_enabled = bool(providers_config.get("enabled"))
        mode = str(
            providers_config.get("access_control", ACCESS_CONTROL_ALLOWLIST) or ""
        ).strip().lower()
        if mode not in ACCESS_CONTROL_MODES:
            # Fail closed on a typo: a misspelled mode must not silently become
            # "open", which is exactly the posture this control exists to end.
            logger.error(
                "Invalid auth.providers.access_control %r; expected one of %s. "
                "Falling back to %r (deny-by-default).",
                mode, ", ".join(ACCESS_CONTROL_MODES), ACCESS_CONTROL_ALLOWLIST,
            )
            mode = ACCESS_CONTROL_ALLOWLIST
        self.mode = mode

        # Identities already approved via the admin-SSO allowlist are implicitly
        # cleared. Requiring an operator to restate the same decision in two
        # places is how they lock themselves out of the panel that manages it.
        #
        # Parsed exactly as AdminSSOService parses admin_users, and for the same
        # reason: OIDC subjects are case-SENSITIVE, so folding them would make
        # "entra:AdminSub" also clear the distinct identity "entra:adminsub".
        # Only emails are matched case-insensitively.
        admin_sso = providers_config.get("admin_sso", {}) or {}
        self._implicit_emails: set = set()
        self._implicit_subjects: set = set()
        for raw in admin_sso.get("admin_users", []) or []:
            if not raw:
                continue
            entry = str(raw).strip()
            if entry.lower().startswith(("entra:", "auth0:")):
                provider, subject = entry.split(":", 1)
                self._implicit_subjects.add(f"{provider.lower()}:{subject}")
            else:
                self._implicit_emails.add(entry.lower())

    @property
    def enforcing(self) -> bool:
        """Whether external identities must be pre-cleared to gain access."""
        return self._providers_enabled and self.mode == ACCESS_CONTROL_ALLOWLIST

    def _is_implicitly_allowed(
        self, email: Optional[str], username: Optional[str]
    ) -> bool:
        """Whether ``admin_users`` already approved this identity.

        ``username`` is the stored ``"{provider}:{subject}"``, which is exactly
        the form an ``admin_users`` subject entry takes, so the two compare
        directly - but only with the subject's case preserved. Matching
        ``entra:adminsub`` against an ``entra:AdminSub`` entry would hand a
        *different* external identity ordinary allowlist clearance, and with it
        any panel role an operator had assigned to it.
        """
        if email and str(email).strip().lower() in self._implicit_emails:
            return True
        if username:
            candidate = str(username).strip()
            provider, _, subject = candidate.partition(":")
            if subject and f"{provider.lower()}:{subject}" in self._implicit_subjects:
                return True
        return False

    async def is_cleared(
        self,
        email: Optional[str] = None,
        username: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Whether this external identity may be granted access.

        Always True when not enforcing. When enforcing, the identity must either
        be implicitly allowed via ``admin_users`` or match an allowlist rule -
        an empty rule set therefore clears nobody.
        """
        if not self.enforcing:
            return True
        if self._is_implicitly_allowed(email, username):
            return True
        rule = await self.match_identity(
            user_id=user_id, email=email, username=username
        )
        return rule is not None

    async def is_user_cleared(self, user: Dict[str, Any]) -> bool:
        """:meth:`is_cleared` over a user record (row or auth-context dict).

        Local password users have no ``provider`` and are never gated.
        """
        if not user.get("provider"):
            return True
        raw_id = user.get("id") or user.get("_id")
        return await self.is_cleared(
            email=user.get("email"),
            username=user.get("username"),
            user_id=str(raw_id) if raw_id else None,
        )

    async def clears_under(
        self, rules: list, user: Dict[str, Any]
    ) -> bool:
        """Whether ``user`` would still be cleared given exactly ``rules``.

        Used to answer "does this deletion/edit revoke someone's access?" before
        performing it (the self-lockout guard) and after it (session revocation).
        Non-enforcing mode and implicit ``admin_users`` clearance short-circuit
        the same way :meth:`is_cleared` does.
        """
        if not self.enforcing or not user.get("provider"):
            return True
        email, username = user.get("email"), user.get("username")
        if self._is_implicitly_allowed(email, username):
            return True
        raw_id = user.get("id") or user.get("_id")
        return self.match_in(
            rules,
            user_id=str(raw_id) if raw_id else None,
            email=email,
            username=username,
        ) is not None

    async def rules_excluding(self, rule_id: Optional[str]) -> list:
        """Every stored rule except ``rule_id`` (uncached, for simulation)."""
        rules = await self.list_rules()
        if rule_id is None:
            return rules
        return [r for r in rules if str(r.get("_id")) != str(rule_id)]

    async def find_uncleared_users(self, rules: list) -> list:
        """External users that ``rules`` would not clear.

        The counterpart to :meth:`find_matching_users`: an allow rule's removal
        is what cuts people off, so revocation looks for who *stops* matching.
        """
        try:
            users = await self.database.find_many(
                self.users_collection_name, {}, limit=10000
            )
        except Exception as e:
            logger.error(f"Failed to load users for allowlist evaluation: {str(e)}")
            return []
        uncleared = []
        for user in users:
            if not user.get("provider"):
                continue
            if not await self.clears_under(rules, user):
                uncleared.append(user)
        return uncleared

    async def has_rules(self) -> bool:
        """Whether any allowlist rule exists (uncached; for startup reporting)."""
        return bool(await self.list_rules())
