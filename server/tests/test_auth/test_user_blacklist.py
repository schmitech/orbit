"""
User Blacklist Tests
====================

Covers pattern matching, enforcement at every identity-resolution point in
AuthService, and session revocation, against a real SQLite backend.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

from services.auth_service import AuthService  # noqa: E402
from services.database_service import DatabaseDuplicateKeyError  # noqa: E402
from services.sqlite_service import SQLiteService  # noqa: E402
from services.user_blacklist_service import (  # noqa: E402
    BlacklistRuleError,
    UserBlacklistService,
    matches,
    normalize_pattern,
)

TEMP_DIR = None


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def get_test_config(name):
    return {
        'general': {},
        'auth': {
            'default_admin_username': 'admin',
            'default_admin_password': 'admin12345',
            # Disable caching so a rule added mid-test takes effect at once.
            'blacklist': {'cache_ttl': 0},
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(TEMP_DIR, f"blacklist_{name}_{os.getpid()}.db")
                }
            }
        },
    }


@pytest_asyncio.fixture
async def auth_service(request):
    config = get_test_config(request.node.name)
    database = SQLiteService(config)
    await database.initialize()
    service = AuthService(config, database)
    await service.initialize()
    yield service
    await service.close()


# ---------------------------------------------------------------------------
# Pattern semantics
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("pattern,value,expected", [
    ("abuser@example.com", "abuser@example.com", True),
    ("abuser@example.com", "ABUSER@Example.COM", True),   # case-insensitive
    ("abuser@example.com", " abuser@example.com ", True),  # whitespace-trimmed
    ("abuser@example.com", "other@example.com", False),
    ("*@spam-domain.com", "anyone@spam-domain.com", True),
    ("*@spam-domain.com", "anyone@good-domain.com", False),
    ("*@spam-domain.com", "anyone@sub.spam-domain.com", False),
    ("entra:abc*", "entra:abc123", True),
    ("entra:abc*", "auth0:abc123", False),
    ("user?", "user1", True),
    ("user?", "user12", False),
    ("anything", None, False),
    ("anything", "", False),
])
def test_pattern_matching(pattern, value, expected):
    assert matches(pattern, value) is expected


@pytest.mark.unit
def test_normalize_pattern_lowercases_and_trims():
    assert normalize_pattern("  ABUSER@Example.COM  ") == "abuser@example.com"


@pytest.mark.unit
@pytest.mark.parametrize("pattern", ["", "   ", "*", "**", "?", "*?*"])
def test_normalize_pattern_rejects_catch_all(pattern):
    """A pattern of only wildcards would block every user, including admins."""
    with pytest.raises(BlacklistRuleError):
        normalize_pattern(pattern)


@pytest.mark.unit
def test_normalize_pattern_rejects_overlong():
    with pytest.raises(BlacklistRuleError):
        normalize_pattern("a" * 321)


# ---------------------------------------------------------------------------
# Rule management
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_and_list_rule(auth_service):
    await auth_service.blacklist.add_rule("bad@example.com", "email", reason="spam", created_by="admin")
    rules = await auth_service.blacklist.list_rules()
    assert len(rules) == 1
    assert rules[0]["pattern"] == "bad@example.com"
    assert rules[0]["entry_type"] == "email"
    assert rules[0]["reason"] == "spam"
    assert rules[0]["created_by"] == "admin"


@pytest.mark.asyncio
async def test_duplicate_rule_rejected(auth_service):
    await auth_service.blacklist.add_rule("bad@example.com", "email")
    with pytest.raises(BlacklistRuleError):
        await auth_service.blacklist.add_rule("BAD@example.com", "email")


@pytest.mark.asyncio
async def test_duplicate_rule_rejected_by_database_constraint(auth_service):
    """add_rule's find_one is advisory - the unique index is the real guard.

    Simulates the concurrent case by inserting directly, bypassing the
    pre-check, and asserts the backend refuses it rather than storing a
    duplicate. Without the compound unique index this silently passes.
    """
    await auth_service.blacklist.add_rule("bad@example.com", "email")

    with pytest.raises(DatabaseDuplicateKeyError):
        await auth_service.database.insert_one("user_blacklist", {
            "pattern": "bad@example.com", "entry_type": "email", "reason": None,
            "created_by": None, "created_at": "2026-01-01T00:00:00+00:00",
        })

    rules = await auth_service.blacklist.list_rules()
    assert len(rules) == 1


@pytest.mark.asyncio
async def test_same_pattern_allowed_across_entry_types(auth_service):
    """Uniqueness is per (entry_type, pattern), not per pattern alone."""
    await auth_service.blacklist.add_rule("victim", "username")
    await auth_service.blacklist.add_rule("victim", "user_id")
    assert len(await auth_service.blacklist.list_rules()) == 2


@pytest.mark.asyncio
async def test_invalid_entry_type_rejected(auth_service):
    with pytest.raises(BlacklistRuleError):
        await auth_service.blacklist.add_rule("bad@example.com", "not_a_field")


@pytest.mark.asyncio
async def test_delete_rule_unblocks(auth_service):
    rule = await auth_service.blacklist.add_rule("blocked", "username")
    user = {"_id": "x", "username": "blocked", "email": None}
    assert await auth_service.blacklist.is_blocked(user) is True

    assert await auth_service.blacklist.delete_rule(str(rule["_id"])) is True
    assert await auth_service.blacklist.is_blocked(user) is False


@pytest.mark.asyncio
async def test_update_rule_changes_who_is_blocked(auth_service):
    rule = await auth_service.blacklist.add_rule("olduser", "username")
    await auth_service.create_user("newuser", "password123", role="user")

    updated = await auth_service.blacklist.update_rule(
        str(rule["_id"]), "newuser", "username", reason="moved"
    )
    assert updated["pattern"] == "newuser"
    assert updated["reason"] == "moved"

    # The old target authenticates again, the new one no longer can.
    await auth_service.create_user("olduser", "password123", role="user")
    assert (await auth_service.authenticate_user("olduser", "password123"))[0] is True
    assert (await auth_service.authenticate_user("newuser", "password123"))[0] is False


@pytest.mark.asyncio
async def test_update_rule_revokes_sessions_for_new_pattern(auth_service):
    await auth_service.create_user("victim", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is True

    rule = await auth_service.blacklist.add_rule("someone-else", "username")
    updated = await auth_service.blacklist.update_rule(
        str(rule["_id"]), "victim", "username"
    )

    assert updated["matched_users"] == 1
    assert updated["revoked_sessions"] == 1
    assert (await auth_service.validate_token(token))[0] is False


@pytest.mark.asyncio
async def test_update_rule_normalizes_and_validates(auth_service):
    rule = await auth_service.blacklist.add_rule("bad@example.com", "email")

    updated = await auth_service.blacklist.update_rule(
        str(rule["_id"]), "  OTHER@Example.COM  ", "email"
    )
    assert updated["pattern"] == "other@example.com"

    with pytest.raises(BlacklistRuleError):
        await auth_service.blacklist.update_rule(str(rule["_id"]), "*", "email")
    with pytest.raises(BlacklistRuleError):
        await auth_service.blacklist.update_rule(str(rule["_id"]), "x", "bogus_type")


@pytest.mark.asyncio
async def test_update_rule_rejects_collision_with_other_rule(auth_service):
    first = await auth_service.blacklist.add_rule("first@example.com", "email")
    await auth_service.blacklist.add_rule("second@example.com", "email")

    with pytest.raises(BlacklistRuleError):
        await auth_service.blacklist.update_rule(
            str(first["_id"]), "second@example.com", "email"
        )
    # The failed edit left the original untouched.
    assert (await auth_service.blacklist.get_rule(str(first["_id"])))["pattern"] == "first@example.com"


@pytest.mark.asyncio
async def test_update_rule_to_its_own_values_is_allowed(auth_service):
    """Re-saving an unchanged row must not trip the uniqueness check."""
    rule = await auth_service.blacklist.add_rule("bad@example.com", "email", reason="spam")
    updated = await auth_service.blacklist.update_rule(
        str(rule["_id"]), "bad@example.com", "email", reason="spam"
    )
    assert updated is not None
    assert updated["matched_users"] == 0
    assert len(await auth_service.blacklist.list_rules()) == 1


@pytest.mark.asyncio
async def test_update_reason_only_keeps_pattern(auth_service):
    rule = await auth_service.blacklist.add_rule("bad@example.com", "email")
    updated = await auth_service.blacklist.update_rule(
        str(rule["_id"]), "bad@example.com", "email", reason="now documented"
    )
    assert updated["pattern"] == "bad@example.com"
    assert updated["reason"] == "now documented"


@pytest.mark.asyncio
async def test_update_rule_does_not_report_success_when_write_fails(auth_service):
    """A rejected UPDATE must not yield a 200 or revoke anyone's sessions.

    No backend raises DatabaseDuplicateKeyError from update_one - SQLite,
    Postgres, and MongoDB all swallow every exception and return False - so a
    uniqueness violation surfaces only as a falsy return value.
    """
    await auth_service.create_user("victim", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is True

    rule = await auth_service.blacklist.add_rule("someone-else", "username")

    original_update_one = auth_service.database.update_one

    async def rejecting_update_one(collection_name, query, update):
        if collection_name == "user_blacklist":
            return False
        return await original_update_one(collection_name, query, update)

    auth_service.database.update_one = rejecting_update_one
    try:
        with pytest.raises(Exception) as excinfo:
            await auth_service.blacklist.update_rule(
                str(rule["_id"]), "victim", "username"
            )
        assert not isinstance(excinfo.value, AssertionError)
    finally:
        auth_service.database.update_one = original_update_one

    # The rule is untouched and the user keeps working.
    assert (await auth_service.blacklist.get_rule(str(rule["_id"])))["pattern"] == "someone-else"
    assert (await auth_service.validate_token(token))[0] is True


@pytest.mark.asyncio
async def test_update_rule_reports_real_uniqueness_violation_as_duplicate(auth_service):
    """The genuine race, not a mocked failure: the clash pre-check passes, then
    a competing rule claims the same (entry_type, pattern) before our UPDATE.

    The database rejects the write via the compound unique index; the caller
    must see a duplicate error (400), not a false success.
    """
    rule = await auth_service.blacklist.add_rule("first@example.com", "email")

    original_find_one = auth_service.database.find_one
    calls = {"n": 0}

    async def find_one_then_race(collection_name, query):
        result = await original_find_one(collection_name, query)
        # Let the clash pre-check see a clear field, then insert the competitor
        # so only the database can catch it.
        if collection_name == "user_blacklist" and query.get("pattern") == "taken@example.com":
            calls["n"] += 1
            if calls["n"] == 1:
                await original_find_one(collection_name, query)
                await auth_service.database.insert_one("user_blacklist", {
                    "pattern": "taken@example.com", "entry_type": "email",
                    "reason": None, "created_by": None,
                    "created_at": "2026-01-01T00:00:00+00:00",
                })
                return None
        return result

    auth_service.database.find_one = find_one_then_race
    try:
        with pytest.raises(BlacklistRuleError):
            await auth_service.blacklist.update_rule(
                str(rule["_id"]), "taken@example.com", "email"
            )
    finally:
        auth_service.database.find_one = original_find_one

    assert (await auth_service.blacklist.get_rule(str(rule["_id"])))["pattern"] == "first@example.com"


@pytest.mark.asyncio
async def test_update_missing_rule_returns_none(auth_service):
    assert await auth_service.blacklist.update_rule(
        "does-not-exist", "x@example.com", "email"
    ) is None


@pytest.mark.asyncio
async def test_delete_missing_rule_returns_false(auth_service):
    assert await auth_service.blacklist.delete_rule("does-not-exist") is False


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_password_login_blocked(auth_service):
    await auth_service.create_user("victim", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is True and token

    await auth_service.blacklist.add_rule("victim", "username")

    ok, token, info = await auth_service.authenticate_user("victim", "password123")
    assert ok is False
    assert token is None
    assert info is None


@pytest.mark.asyncio
async def test_existing_session_rejected_after_blacklisting(auth_service):
    """A token minted before the rule must stop validating."""
    await auth_service.create_user("victim", "password123", role="user")
    ok, token, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is True

    valid, _ = await auth_service.validate_token(token)
    assert valid is True

    await auth_service.blacklist.add_rule("victim", "username")

    valid, info = await auth_service.validate_token(token)
    assert valid is False
    assert info is None


@pytest.mark.asyncio
async def test_add_rule_revokes_sessions(auth_service):
    await auth_service.create_user("victim", "password123", role="user")
    await auth_service.authenticate_user("victim", "password123")
    await auth_service.authenticate_user("victim", "password123")

    rule = await auth_service.blacklist.add_rule("victim", "username")
    assert rule["matched_users"] == 1
    assert rule["revoked_sessions"] == 2

    remaining = await auth_service.database.find_many("sessions", {}, limit=100)
    assert remaining == []


@pytest.mark.asyncio
async def test_verify_credentials_blocked(auth_service):
    """The websocket/basic-auth path is covered too."""
    await auth_service.create_user("victim", "password123", role="user")
    assert (await auth_service.verify_credentials("victim", "password123"))[0] is True

    await auth_service.blacklist.add_rule("victim", "username")
    assert (await auth_service.verify_credentials("victim", "password123"))[0] is False


@pytest.mark.asyncio
async def test_email_wildcard_blocks_by_domain(auth_service):
    await auth_service.create_user("victim", "password123", role="user")
    user = await auth_service.database.find_one("users", {"username": "victim"})
    await auth_service.database.update_one(
        "users", {"_id": user["_id"]}, {"$set": {"email": "someone@spam-domain.com"}}
    )

    await auth_service.blacklist.add_rule("*@spam-domain.com", "email")

    ok, _, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is False


@pytest.mark.asyncio
async def test_unrelated_user_unaffected(auth_service):
    await auth_service.create_user("victim", "password123", role="user")
    await auth_service.create_user("bystander", "password123", role="user")

    await auth_service.blacklist.add_rule("victim", "username")

    ok, token, _ = await auth_service.authenticate_user("bystander", "password123")
    assert ok is True
    valid, _ = await auth_service.validate_token(token)
    assert valid is True


@pytest.mark.asyncio
async def test_external_user_not_provisioned_when_blacklisted(auth_service):
    """A blocked external identity must never gain a row in the users table."""
    await auth_service.blacklist.add_rule("*@spam-domain.com", "email")

    user = await auth_service._find_or_create_external_user(
        "entra", "subject-123", "newcomer@spam-domain.com"
    )
    assert user is None
    assert await auth_service.database.find_one("users", {"username": "entra:subject-123"}) is None


@pytest.mark.asyncio
async def test_external_user_provisioned_when_not_blacklisted(auth_service):
    await auth_service.blacklist.add_rule("*@spam-domain.com", "email")

    user = await auth_service._find_or_create_external_user(
        "entra", "subject-456", "newcomer@good-domain.com"
    )
    assert user is not None
    assert user["username"] == "entra:subject-456"


@pytest.mark.asyncio
async def test_blacklist_by_user_id(auth_service):
    user_id = await auth_service.create_user("victim", "password123", role="user")
    await auth_service.blacklist.add_rule(str(user_id), "user_id")

    ok, _, _ = await auth_service.authenticate_user("victim", "password123")
    assert ok is False


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_serves_rules_without_requerying(auth_service):
    """With a live TTL, a rule written behind the service's back isn't seen
    until the cache is invalidated - the documented multi-worker tradeoff."""
    service = UserBlacklistService(
        {'auth': {'blacklist': {'cache_ttl': 300}}}, auth_service.database
    )
    user = {"_id": "x", "username": "victim", "email": None}
    assert await service.is_blocked(user) is False  # primes the empty cache

    await auth_service.database.insert_one("user_blacklist", {
        "pattern": "victim", "entry_type": "username", "reason": None,
        "created_by": None, "created_at": "2026-01-01T00:00:00+00:00",
    })
    assert await service.is_blocked(user) is False  # still cached

    service.invalidate_cache()
    assert await service.is_blocked(user) is True
