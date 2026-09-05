"""
Two-Factor Authentication (TOTP) Tests
=======================================

Covers enrollment, login gating, and recovery codes on MfaService/AuthService
against a real SQLite backend.
"""

import base64
import os
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

import pyotp
import pytest
import pytest_asyncio

SERVER_DIR = Path(__file__).parent.parent.parent.absolute()
sys.path.append(str(SERVER_DIR))

os.environ.setdefault(
    "ORBIT_MFA_ENCRYPTION_KEY", base64.b64encode(secrets.token_bytes(32)).decode()
)

from services.auth_service import AuthService
from services.sqlite_service import SQLiteService

TEMP_DIR = None


def setup_module(module):
    global TEMP_DIR
    TEMP_DIR = tempfile.mkdtemp()


def teardown_module(module):
    if TEMP_DIR:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


def get_test_config(name, **two_factor_overrides):
    return {
        'general': {},
        'auth': {
            'default_admin_username': 'admin',
            'default_admin_password': 'admin12345',
            'account_lockout': {'enabled': False},
            'two_factor': {
                'enabled': True,
                'required_for_roles': ['admin'],
                'issuer_name': 'ORBIT-TEST',
                'recovery_codes_count': 3,
                'remember_device_days': 30,
                'rate_limit': {'enabled': False},
                **two_factor_overrides,
            },
        },
        'internal_services': {
            'backend': {
                'type': 'sqlite',
                'sqlite': {
                    'database_path': os.path.join(TEMP_DIR, f"mfa_{name}_{os.getpid()}.db")
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


async def _create_user(auth_service, username="alice", password="Sup3r$ecretPass!", roles=None):
    user_id = await auth_service.create_user(username, password, roles=roles or ["user"])
    assert user_id is not None
    return user_id


# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _decode_qr_payload(data_uri: str) -> str:
    """Decode a `data:image/png;base64,...` QR code back to its text payload.

    opencv-python isn't a declared ORBIT dependency (2FA only needs `qrcode`
    to render, not decode), so this skips rather than fails where it's
    unavailable - it strengthens the assertion when a decoder happens to be
    installed without requiring one.
    """
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    png_bytes = base64.b64decode(data_uri.split(",", 1)[1])
    assert png_bytes[:8] == _PNG_SIGNATURE, "not a valid PNG"

    array = np.frombuffer(png_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    payload, _points, _ = cv2.QRCodeDetector().detectAndDecode(image)
    return payload


@pytest.mark.integration
@pytest.mark.asyncio
async def test_confirm_enrollment_requires_valid_code(auth_service):
    user_id = await _create_user(auth_service)

    enrollment = await auth_service.mfa.begin_enrollment(user_id, "alice")
    assert "secret" in enrollment and "otpauth_uri" in enrollment
    assert enrollment["qr_code_data_uri"].startswith("data:image/png;base64,")
    assert _decode_qr_payload(enrollment["qr_code_data_uri"]) == enrollment["otpauth_uri"]

    # An invalid code leaves the account without 2FA.
    result = await auth_service.mfa.confirm_enrollment(user_id, "000000")
    assert result is None
    assert not await auth_service.mfa.is_enabled(user_id)

    # A valid code confirms enrollment and issues recovery codes.
    valid_code = pyotp.TOTP(enrollment["secret"]).now()
    recovery_codes = await auth_service.mfa.confirm_enrollment(user_id, valid_code)
    assert recovery_codes is not None
    assert len(recovery_codes) == 3
    assert await auth_service.mfa.is_enabled(user_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_begin_enrollment_rejected_when_already_enabled(auth_service):
    user_id = await _create_user(auth_service)
    enrollment = await auth_service.mfa.begin_enrollment(user_id, "alice")
    valid_code = pyotp.TOTP(enrollment["secret"]).now()
    await auth_service.mfa.confirm_enrollment(user_id, valid_code)

    from services.mfa_service import MfaError
    with pytest.raises(MfaError):
        await auth_service.mfa.begin_enrollment(user_id, "alice")


# ---------------------------------------------------------------------------
# Login gating
# ---------------------------------------------------------------------------

async def _enroll(auth_service, user_id, username):
    enrollment = await auth_service.mfa.begin_enrollment(user_id, username)
    valid_code = pyotp.TOTP(enrollment["secret"]).now()
    recovery_codes = await auth_service.mfa.confirm_enrollment(user_id, valid_code)
    return enrollment["secret"], recovery_codes


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_with_no_or_incorrect_totp_does_not_issue_session(auth_service):
    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)
    secret, _ = await _enroll(auth_service, user_id, "alice")

    success, pending_token, user_info = await auth_service.authenticate_user("alice", password)
    assert success is True
    assert user_info["mfa_required"] is True

    # Incorrect TOTP does not complete the login.
    ok, token, info, device_token = await auth_service.complete_2fa_login(
        pending_token, "000000"
    )
    assert ok is False
    assert token is None

    # Correct TOTP completes it and mints a real session.
    valid_code = pyotp.TOTP(secret).now()
    ok, token, info, device_token = await auth_service.complete_2fa_login(
        pending_token, valid_code
    )
    assert ok is True
    is_valid, _ = await auth_service.validate_token(token)
    assert is_valid is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_role_requiring_2fa_rejects_self_disable(auth_service):
    """A user whose role requires 2FA must not be able to disable their own
    enrollment via POST /auth/mfa/disable - that would leave every future
    password login blocked with no way back short of out-of-band recovery."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.auth_routes import auth_router

    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, username="carol", password=password, roles=["admin"])
    await _enroll(auth_service, user_id, "carol")

    user = await auth_service.database.find_one(
        auth_service.users_collection_name, {"username": "carol"}
    )
    token = await auth_service.create_session(user)

    app = FastAPI()
    app.state.auth_service = auth_service
    app.include_router(auth_router)
    client = TestClient(app)

    response = client.post(
        "/auth/mfa/disable",
        json={"current_password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert await auth_service.mfa.is_enabled(user_id) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_role_requiring_2fa_blocks_unenrolled_login(auth_service):
    password = "Sup3r$ecretPass!"
    await _create_user(auth_service, username="bob", password=password, roles=["admin"])

    failure_context = {}
    success, token, user_info = await auth_service.authenticate_user(
        "bob", password, failure_context
    )
    assert success is False
    assert token is None
    assert failure_context["reason"] == "mfa_enrollment_required"


# ---------------------------------------------------------------------------
# Recovery codes
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_recovery_code_is_single_use(auth_service):
    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)
    _, recovery_codes = await _enroll(auth_service, user_id, "alice")
    code = recovery_codes[0]

    success, pending_token, _ = await auth_service.authenticate_user("alice", password)
    assert success is True

    ok, token, _, _ = await auth_service.complete_2fa_login(pending_token, code)
    assert ok is True
    assert token is not None

    # A second login attempt with the same recovery code is rejected.
    success, pending_token2, _ = await auth_service.authenticate_user("alice", password)
    ok2, token2, _, _ = await auth_service.complete_2fa_login(pending_token2, code)
    assert ok2 is False
    assert token2 is None


# ---------------------------------------------------------------------------
# Admin reset
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_reset_disables_2fa(auth_service):
    user_id = await _create_user(auth_service)
    await _enroll(auth_service, user_id, "alice")
    assert await auth_service.mfa.is_enabled(user_id)

    reset = await auth_service.mfa.admin_reset(user_id)
    assert reset is True
    assert not await auth_service.mfa.is_enabled(user_id)


# ---------------------------------------------------------------------------
# Pending-token identity (rate-limit keying) and expired-token cleanup
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_peek_mfa_pending_user_id_resolves_and_expires(auth_service):
    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)
    await _enroll(auth_service, user_id, "alice")

    success, pending_token, _ = await auth_service.authenticate_user("alice", password)
    assert success is True

    resolved = await auth_service.peek_mfa_pending_user_id(pending_token)
    assert resolved == str(user_id)

    assert await auth_service.peek_mfa_pending_user_id("not-a-real-token") is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fresh_pending_tokens_share_the_same_rate_limit_identity(auth_service):
    """A fresh pending token is minted on every password check, but the
    account-derived identity used for MFA throttling must stay stable across
    them - otherwise an attacker who knows the password gets a brand new
    guessing budget on every request."""
    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)
    await _enroll(auth_service, user_id, "alice")

    success1, pending_token1, _ = await auth_service.authenticate_user("alice", password)
    success2, pending_token2, _ = await auth_service.authenticate_user("alice", password)
    assert success1 and success2
    assert pending_token1 != pending_token2

    identity1 = await auth_service.peek_mfa_pending_user_id(pending_token1)
    identity2 = await auth_service.peek_mfa_pending_user_id(pending_token2)
    assert identity1 == identity2 == str(user_id)


# ---------------------------------------------------------------------------
# Concurrent recovery-code consumption
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_recovery_code_use_only_succeeds_once(auth_service):
    import asyncio

    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)
    _, recovery_codes = await _enroll(auth_service, user_id, "alice")
    code = recovery_codes[0]

    results = await asyncio.gather(
        auth_service.mfa.verify_recovery_code(user_id, code),
        auth_service.mfa.verify_recovery_code(user_id, code),
    )
    assert sorted(results) == [False, True]


# ---------------------------------------------------------------------------
# Missing/invalid ORBIT_MFA_ENCRYPTION_KEY surfaces clearly, not as a 500 or
# a misleading "invalid code"
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_encryption_key_raises_on_enrollment(auth_service, monkeypatch):
    monkeypatch.delenv("ORBIT_MFA_ENCRYPTION_KEY", raising=False)
    user_id = await _create_user(auth_service)

    from services.file_storage.encryption import FileEncryptionError
    with pytest.raises(FileEncryptionError):
        await auth_service.mfa.begin_enrollment(user_id, "alice")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_encryption_key_returns_503_not_bare_500(auth_service):
    """The route must translate FileEncryptionError into a clear, actionable
    client-facing error - not let it propagate as an opaque 500."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.auth_routes import auth_router

    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)

    user = await auth_service.database.find_one(
        auth_service.users_collection_name, {"username": "alice"}
    )
    token = await auth_service.create_session(user)

    app = FastAPI()
    app.state.auth_service = auth_service
    app.include_router(auth_router)
    client = TestClient(app, raise_server_exceptions=False)

    saved_key = os.environ.pop("ORBIT_MFA_ENCRYPTION_KEY", None)
    try:
        response = client.post(
            "/auth/mfa/enroll", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        if saved_key is not None:
            os.environ["ORBIT_MFA_ENCRYPTION_KEY"] = saved_key

    assert response.status_code == 503
    assert "misconfigured" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_encryption_key_on_login_2fa_is_not_reported_as_invalid_code(
    auth_service, request,
):
    """complete_2fa_login must re-raise FileEncryptionError rather than
    swallowing it into the generic "invalid code" failure path - otherwise a
    server misconfiguration is indistinguishable from a wrong TOTP guess.

    ``MfaService`` caches its ``FileEncryptor`` for the process's lifetime
    (realistic: a real deployment doesn't unset the env var mid-run), so this
    simulates the scenario that actually matters - the key is already
    missing when the *process starts* - by building a fresh AuthService
    against the same database, the same way a server restart would.
    """
    password = "Sup3r$ecretPass!"
    user_id = await _create_user(auth_service, password=password)
    await _enroll(auth_service, user_id, "alice")

    success, pending_token, _ = await auth_service.authenticate_user("alice", password)
    assert success is True

    saved_key = os.environ.pop("ORBIT_MFA_ENCRYPTION_KEY", None)
    try:
        fresh_auth_service = AuthService(get_test_config(request.node.name + "_fresh"), auth_service.database)
        # Reuse the already-initialized database (same file); re-running
        # initialize() would be redundant but harmless - skip it and just
        # build the MFA service the same way AuthService.initialize() does.
        from services.mfa_service import MfaService
        fresh_auth_service.mfa = MfaService(fresh_auth_service.config, auth_service.database)
        fresh_auth_service.users_collection_name = auth_service.users_collection_name
        fresh_auth_service.mfa_pending_collection_name = auth_service.mfa_pending_collection_name
        fresh_auth_service.sessions_collection_name = auth_service.sessions_collection_name

        from services.file_storage.encryption import FileEncryptionError
        with pytest.raises(FileEncryptionError):
            await fresh_auth_service.complete_2fa_login(pending_token, "000000")
    finally:
        if saved_key is not None:
            os.environ["ORBIT_MFA_ENCRYPTION_KEY"] = saved_key
