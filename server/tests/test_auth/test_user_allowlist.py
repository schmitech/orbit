"""
User Allowlist Tests
====================

Covers pre-clearing of external identities: mode semantics, the implicit
``admin_users`` clearance, enforcement at provisioning and at every request,
precedence against the blacklist, and the guarantee that local password users
are never gated. Real SQLite backend.

Pattern matching, caching, and CRUD are inherited from UserBlacklistService and
covered by test_user_blacklist.py; this file only tests what differs.
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
from services.sqlite_service import SQLiteService  # noqa: E402
from services.user_allowlist_service import UserAllowlistService  # noqa: E402

TEMP_DIR = None


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def get_test_config(name, *, access_control="allowlist", admin_users=None,
                    providers_enabled=True):
    return {
        'general': {},
        'auth': {
            'default_admin_username': 'admin',
            'default_admin_password': 'admin12345',
            # Disable caching so a rule added mid-test takes effect at once.
            'blacklist': {'cache_ttl': 0},
            'allowlist': {'cache_ttl': 0},
            'providers': {
                'enabled': providers_enabled,
                'default_role': 'user',
                'access_control': access_control,
                'admin_sso': {'admin_users': admin_users or []},
            },
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(
                        TEMP_DIR, f"allowlist_{name}_{os.getpid()}.db"
                    )
                }
            }
        },
    }


async def make_auth_service(name, **kwargs):
    """Build an initialized AuthService over a fresh SQLite file."""
    config = get_test_config(name, **kwargs)
    database = SQLiteService(config)
    await database.initialize()
    service = AuthService(config, database)
    await service.initialize()
    return service


@pytest_asyncio.fixture
async def auth_service(request):
    """Enforcing allowlist mode, no rules, no implicit entries."""
    service = await make_auth_service(request.node.name)
    yield service
    await service.close()


# ---------------------------------------------------------------------------
# Mode semantics
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_allowlist_mode_is_the_default():
    config = get_test_config("default_mode")
    del config['auth']['providers']['access_control']
    svc = UserAllowlistService(config, None)
    assert svc.mode == "allowlist"
    assert svc.enforcing


@pytest.mark.unit
def test_open_mode_does_not_enforce():
    svc = UserAllowlistService(get_test_config("open", access_control="open"), None)
    assert not svc.enforcing


@pytest.mark.unit
def test_invalid_mode_fails_closed():
    """A typo must not silently become 'open' - that's the posture being fixed."""
    svc = UserAllowlistService(
        get_test_config("typo", access_control="allowlst"), None
    )
    assert svc.mode == "allowlist"
    assert svc.enforcing


@pytest.mark.unit
def test_not_enforcing_when_no_provider_is_enabled():
    """With no external providers there are no external identities to gate."""
    svc = UserAllowlistService(
        get_test_config("noproviders", providers_enabled=False), None
    )
    assert svc.mode == "allowlist"
    assert not svc.enforcing


@pytest.mark.asyncio
async def test_open_mode_clears_everyone():
    svc = await make_auth_service("open_clears", access_control="open")
    try:
        assert await svc.allowlist.is_cleared(email="anyone@example.com")
    finally:
        await svc.close()


# ---------------------------------------------------------------------------
# Empty means deny
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_allowlist_clears_nobody(auth_service):
    """The inverse of the blacklist: an empty rule set admits no one."""
    assert not await auth_service.allowlist.is_cleared(
        email="anyone@example.com", username="entra:whoever"
    )


@pytest.mark.asyncio
async def test_rule_clears_matching_identity(auth_service):
    await auth_service.allowlist.add_rule("*@corp.example.com", "email")

    assert await auth_service.allowlist.is_cleared(email="alice@corp.example.com")
    assert not await auth_service.allowlist.is_cleared(email="alice@other.example.com")


@pytest.mark.asyncio
async def test_rule_clears_by_provider_subject(auth_service):
    await auth_service.allowlist.add_rule("entra:approved-*", "username")

    assert await auth_service.allowlist.is_cleared(username="entra:approved-1")
    assert not await auth_service.allowlist.is_cleared(username="entra:random-1")


# ---------------------------------------------------------------------------
# Implicit clearance via admin_users
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_users_email_is_implicitly_cleared():
    """An operator must not have to restate the same approval in two places."""
    svc = await make_auth_service(
        "implicit_email", admin_users=["Boss@Example.com"]
    )
    try:
        assert await svc.allowlist.is_cleared(email="boss@example.com")
        assert not await svc.allowlist.is_cleared(email="someone@example.com")
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_admin_users_subject_is_implicitly_cleared():
    svc = await make_auth_service(
        "implicit_subject", admin_users=["entra:the-admin-sub"]
    )
    try:
        assert await svc.allowlist.is_cleared(username="entra:the-admin-sub")
        assert not await svc.allowlist.is_cleared(username="entra:other-sub")
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_allowlisted_admin_can_still_be_provisioned():
    """The lockout guard that matters: the operator's own SSO login survives
    turning enforcement on with zero rules written."""
    svc = await make_auth_service("implicit_provision", admin_users=["boss@example.com"])
    try:
        user = await svc._find_or_create_external_user("auth0", "boss-sub", "boss@example.com")
        assert user is not None
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_implicit_subject_match_is_case_sensitive():
    """OIDC subjects are case-sensitive. An `entra:AdminSub` entry must not
    clear the *different* identity `entra:adminsub`, which would otherwise
    inherit whatever panel role an operator assigned to it."""
    svc = await make_auth_service(
        "implicit_case", admin_users=["entra:AdminSub"]
    )
    try:
        assert await svc.allowlist.is_cleared(username="entra:AdminSub")
        assert not await svc.allowlist.is_cleared(username="entra:adminsub")
        assert not await svc.allowlist.is_cleared(username="entra:ADMINSUB")
        # The provider prefix is normalized, only the subject is exact.
        assert await svc.allowlist.is_cleared(username="ENTRA:AdminSub")
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_implicit_email_match_stays_case_insensitive():
    """Emails are not case-sensitive, so folding them is correct."""
    svc = await make_auth_service("implicit_email_case", admin_users=["Boss@Example.com"])
    try:
        assert await svc.allowlist.is_cleared(email="BOSS@EXAMPLE.COM")
        assert await svc.allowlist.is_cleared(email="boss@example.com")
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_colonless_admin_users_entry_is_not_treated_as_a_subject():
    """A bare value without a provider prefix is an email, and must not be
    matched against the username dimension."""
    svc = await make_auth_service("implicit_bare", admin_users=["someone"])
    try:
        assert not await svc.allowlist.is_cleared(username="someone")
        assert not await svc.allowlist.is_cleared(username="entra:someone")
    finally:
        await svc.close()


# ---------------------------------------------------------------------------
# Configured collection names
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_collection_names_follow_mongo_config():
    """Revocation scans must use the configured collections, or a Mongo
    deployment with custom names revokes nothing while reporting success."""
    from services.user_blacklist_service import UserBlacklistService

    config = get_test_config("mongo_names")
    config['internal_services'] = {
        'backend': {'type': 'mongodb'},
        'mongodb': {
            'users_collection': 'orbit_users',
            'sessions_collection': 'orbit_sessions',
        },
    }
    for cls in (UserAllowlistService, UserBlacklistService):
        svc = cls(config, None)
        assert svc.users_collection_name == 'orbit_users', cls.__name__
        assert svc.sessions_collection_name == 'orbit_sessions', cls.__name__


@pytest.mark.unit
def test_collection_names_default_for_sql_backends():
    svc = UserAllowlistService(get_test_config("sql_names"), None)
    assert svc.users_collection_name == 'users'
    assert svc.sessions_collection_name == 'sessions'


# ---------------------------------------------------------------------------
# Enforcement: provisioning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_cleared_identity_is_not_provisioned(auth_service):
    """No users row at all - the primary control."""
    user = await auth_service._find_or_create_external_user(
        "entra", "stranger-sub", "stranger@example.com"
    )
    assert user is None
    assert await auth_service.database.find_one(
        "users", {"username": "entra:stranger-sub"}
    ) is None


@pytest.mark.asyncio
async def test_cleared_identity_is_provisioned(auth_service):
    await auth_service.allowlist.add_rule("*@corp.example.com", "email")

    user = await auth_service._find_or_create_external_user(
        "entra", "employee-sub", "employee@corp.example.com"
    )
    assert user is not None
    assert user["username"] == "entra:employee-sub"
    assert user["roles"] == ["user"]


@pytest.mark.asyncio
async def test_sso_provisioning_is_gated_too(auth_service):
    """provision_sso_user goes through the same hook, so an SSO login by a
    non-cleared identity creates nothing either."""
    assert await auth_service.provision_sso_user(
        "auth0", "stranger-sub", "stranger@example.com", is_admin=False
    ) is None


# ---------------------------------------------------------------------------
# Enforcement: per request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_removing_a_rule_denies_an_existing_user(auth_service):
    """Clearance is re-checked per request, so revoking approval takes effect
    for a user who was already provisioned."""
    rule = await auth_service.allowlist.add_rule("*@corp.example.com", "email")
    user = await auth_service._find_or_create_external_user(
        "entra", "employee-sub", "employee@corp.example.com"
    )
    assert await auth_service._is_cleared(user)

    assert await auth_service.allowlist.delete_rule(str(rule["_id"]))
    assert not await auth_service._is_cleared(user)


@pytest.mark.asyncio
async def test_removing_a_rule_denies_an_opaque_sso_session(auth_service):
    """Admin SSO mints an *opaque* session, not a JWT, so it resolves through
    the session branch of validate_token. A callback that lands after
    revocation (or on a worker with a stale rule cache) must not leave a
    usable session behind until expiry."""
    rule = await auth_service.allowlist.add_rule("*@corp.example.com", "email")
    user = await auth_service._find_or_create_external_user(
        "auth0", "employee-sub", "employee@corp.example.com"
    )
    token = await auth_service.create_session(user)
    valid, _ = await auth_service.validate_token(token)
    assert valid is True

    # Withdraw clearance without touching the session row, mimicking a session
    # created after _revoke_uncleared already ran.
    assert await auth_service.allowlist.delete_rule(str(rule["_id"]))

    valid, resolved = await auth_service.validate_token(token)
    assert valid is False
    assert resolved is None
    # The session row is still there - it is the per-request check that denies.
    assert await auth_service.database.find_one("sessions", {"token": token}) is not None


@pytest.mark.asyncio
async def test_opaque_session_survives_while_still_cleared(auth_service):
    """The new check must not break the ordinary case."""
    await auth_service.allowlist.add_rule("*@corp.example.com", "email")
    user = await auth_service._find_or_create_external_user(
        "auth0", "employee-sub", "employee@corp.example.com"
    )
    token = await auth_service.create_session(user)

    valid, resolved = await auth_service.validate_token(token)
    assert valid is True
    assert resolved["username"] == "auth0:employee-sub"


# ---------------------------------------------------------------------------
# Local users are never gated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_password_user_is_never_gated(auth_service):
    """Enforcing with zero rules must not lock out the bootstrap admin."""
    ok, token, user_info = await auth_service.authenticate_user("admin", "admin12345")
    assert ok is True
    assert token

    valid, resolved = await auth_service.validate_token(token)
    assert valid is True
    assert resolved["username"] == "admin"


@pytest.mark.asyncio
async def test_created_local_user_is_cleared(auth_service):
    await auth_service.create_user("localuser", "password123", role="user")
    user = await auth_service.database.find_one("users", {"username": "localuser"})

    assert not user.get("provider")
    assert await auth_service.allowlist.is_user_cleared(user)


# ---------------------------------------------------------------------------
# Precedence against the blacklist
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blacklist_wins_over_allowlist(auth_service):
    """A deny rule must beat an allow rule covering the same identity."""
    await auth_service.allowlist.add_rule("*@corp.example.com", "email")
    await auth_service.blacklist.add_rule("abuser@corp.example.com", "email")

    assert await auth_service._find_or_create_external_user(
        "entra", "abuser-sub", "abuser@corp.example.com"
    ) is None
    # A colleague on the same allowed domain is unaffected.
    assert await auth_service._find_or_create_external_user(
        "entra", "colleague-sub", "colleague@corp.example.com"
    ) is not None


# ---------------------------------------------------------------------------
# Separation from the blacklist rule set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rule_sets_are_stored_separately(auth_service):
    await auth_service.allowlist.add_rule("*@corp.example.com", "email")

    assert auth_service.allowlist.collection_name == "user_allowlist"
    assert auth_service.blacklist.collection_name == "user_blacklist"
    assert await auth_service.blacklist.list_rules() == []
    assert len(await auth_service.allowlist.list_rules()) == 1


@pytest.mark.asyncio
async def test_identical_pattern_allowed_in_both_sets(auth_service):
    """The unique index is per collection, so the same pattern can appear in
    both rule sets (deny still wins)."""
    await auth_service.allowlist.add_rule("*@corp.example.com", "email")
    await auth_service.blacklist.add_rule("*@corp.example.com", "email")

    assert len(await auth_service.allowlist.list_rules()) == 1
    assert len(await auth_service.blacklist.list_rules()) == 1


@pytest.mark.asyncio
async def test_error_message_names_the_allowlist(auth_service):
    """The inherited duplicate error must not say 'blacklist'."""
    from services.user_allowlist_service import AllowlistRuleError

    await auth_service.allowlist.add_rule("*@corp.example.com", "email")
    with pytest.raises(AllowlistRuleError, match="allowlist"):
        await auth_service.allowlist.add_rule("*@corp.example.com", "email")
