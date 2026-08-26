"""
Admin Panel SSO Service
=======================

Server-side OAuth 2.0 Authorization Code + PKCE flow that lets administrators
sign in to ORBIT's admin panel with Microsoft Entra ID or Auth0. Unlike the
bearer-token validation in ``oidc_validator.py`` (where a client presents an
already-issued access token), this component *initiates* the login: it builds
the authorize redirect, exchanges the returned code for tokens, validates the
resulting id_token, and decides admin eligibility via a config allowlist.

The route layer (``admin_panel_routes.py``) drives the flow and, on success,
mints the same ``dashboard_token`` cookie the password login uses.

Requires the ``auth-providers`` profile (PyJWT[crypto]); ``httpx`` for the token
exchange is always available.
"""

import asyncio
import base64
import hashlib
import logging
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

from services.oidc_validator import (
    _PYJWT_AVAILABLE,
    auth0_endpoints,
    entra_endpoints,
)

if _PYJWT_AVAILABLE:
    import jwt
    from jwt import PyJWKClient

logger = logging.getLogger(__name__)

DEFAULT_SCOPES = "openid profile email"


class AdminSSOService:
    """Drives browser SSO for the admin panel across the ``entra``/``auth0`` providers."""

    def __init__(self, providers_config: Dict[str, Any]):
        if not _PYJWT_AVAILABLE:
            raise RuntimeError(
                "auth.providers.admin_sso is enabled but PyJWT is not installed. "
                "Install the 'auth-providers' profile: "
                "./install/setup.sh --profile auth-providers"
            )

        admin_sso = providers_config.get('admin_sso', {})
        self.base_url = (admin_sso.get('base_url') or '').rstrip('/')
        # Split allowlist entries: emails match case-insensitively; "provider:subject"
        # entries match exactly, since OIDC `sub` values are case-sensitive. The
        # provider prefix is normalized to lowercase, the subject part is preserved.
        self._admin_emails: set = set()
        self._admin_subjects: set = set()
        for raw in admin_sso.get('admin_users', []):
            if not raw:
                continue
            entry = str(raw).strip()
            if entry.lower().startswith(("entra:", "auth0:")):
                prov, subject = entry.split(":", 1)
                self._admin_subjects.add(f"{prov.lower()}:{subject}")
            else:
                self._admin_emails.add(entry.lower())

        # provider_name -> metadata
        self._providers: Dict[str, Dict[str, Any]] = {}

        entra = providers_config.get('entra', {})
        if entra.get('enabled') and entra.get('tenant_id') and entra.get('client_id'):
            ep = entra_endpoints(entra['tenant_id'])
            # Entra id_tokens don't carry `email_verified`, and the address comes
            # from the directory rather than user self-assertion, so requiring the
            # claim here would break a path that isn't attacker-controlled.
            self._providers['entra'] = self._build(
                entra, ep, label="Microsoft", verified_email_default=False
            )

        auth0 = providers_config.get('auth0', {})
        if auth0.get('enabled') and auth0.get('domain') and auth0.get('client_id'):
            ep = auth0_endpoints(auth0['domain'])
            self._providers['auth0'] = self._build(
                auth0, ep, label="Auth0", verified_email_default=True
            )

        if self._providers:
            logger.info("Admin SSO enabled for providers: %s", ", ".join(sorted(self._providers)))

    def _build(
        self,
        cfg: Dict[str, Any],
        ep: Dict[str, str],
        label: str,
        verified_email_default: bool,
    ) -> Dict[str, Any]:
        require_verified = cfg.get('require_verified_email')
        if require_verified is None:
            require_verified = verified_email_default
        return {
            "label": label,
            "require_verified_email": bool(require_verified),
            "client_id": cfg['client_id'],
            "client_secret": cfg.get('client_secret') or None,
            "scopes": cfg.get('scopes') or DEFAULT_SCOPES,
            "issuer": ep["issuer"],
            "authorize_url": ep["authorize_url"],
            "token_url": ep["token_url"],
            "jwks_client": PyJWKClient(ep["jwks_uri"], cache_keys=True),
        }

    @property
    def enabled(self) -> bool:
        return bool(self._providers)

    def provider_enabled(self, provider: str) -> bool:
        return provider in self._providers

    def provider_labels(self) -> Dict[str, str]:
        """Enabled provider -> display label, for rendering login buttons."""
        return {name: entry["label"] for name, entry in self._providers.items()}

    def redirect_uri(self, provider: str, request_base_url: str) -> str:
        """Callback URL to send to the IdP; must match the registered redirect URI."""
        base = self.base_url or request_base_url.rstrip('/')
        return f"{base}/admin/auth/{provider}/callback"

    def build_authorize_url(
        self, provider: str, redirect_uri: str
    ) -> Tuple[str, str, str, str]:
        """Return (authorize_url, state, code_verifier, nonce) for a login redirect."""
        entry = self._providers[provider]
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).decode("ascii").rstrip("=")

        params = {
            "client_id": entry["client_id"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": entry["scopes"],
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
        return f"{entry['authorize_url']}?{urlencode(params)}", state, code_verifier, nonce

    async def exchange_code(
        self, provider: str, code: str, code_verifier: str, redirect_uri: str
    ) -> Optional[Dict[str, Any]]:
        """Exchange an authorization code for tokens. Returns None on failure."""
        entry = self._providers[provider]
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": entry["client_id"],
            "code_verifier": code_verifier,
        }
        if entry["client_secret"]:
            data["client_secret"] = entry["client_secret"]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(entry["token_url"], data=data)
            if resp.status_code != 200:
                logger.warning("Token exchange failed for %s: %s %s",
                               provider, resp.status_code, resp.text[:200])
                return None
            return resp.json()
        except Exception as e:
            logger.warning("Token exchange error for %s: %s", provider, e)
            return None

    async def validate_id_token(
        self, provider: str, id_token: str, nonce: str
    ) -> Optional[Dict[str, Any]]:
        """Validate an id_token (audience == client_id) and the nonce. Fails closed."""
        entry = self._providers[provider]
        try:
            claims = await asyncio.to_thread(self._verify_id_token_sync, id_token, entry)
        except Exception as e:
            logger.warning("id_token validation failed for %s: %s", provider, e)
            return None

        if not claims.get("sub"):
            return None
        if nonce and claims.get("nonce") != nonce:
            logger.warning("nonce mismatch on %s id_token", provider)
            return None
        return claims

    def _verify_id_token_sync(self, id_token: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        signing_key = entry["jwks_client"].get_signing_key_from_jwt(id_token)
        return jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=entry["client_id"],
            issuer=entry["issuer"],
            leeway=60,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )

    def requires_verified_email(self, provider: str) -> bool:
        """Whether an ``email``-type allowlist match needs a verified address.

        Unknown providers fail closed (verification required), so a caller that
        somehow reaches here off the enabled-provider path can't match by email.
        """
        entry = self._providers.get(provider)
        return True if entry is None else entry["require_verified_email"]

    def is_admin(
        self,
        email: Optional[str],
        provider: str,
        subject: str,
        email_verified: Optional[bool] = None,
    ) -> bool:
        """True when the identity is on the admin allowlist.

        Email is matched case-insensitively, but only when the provider's
        id_token actually vouches for the address: where the provider lets a
        user self-assert an email (``require_verified_email``), an unverified
        claim must not match, or anyone able to register an allowlisted address
        at the IdP would be promoted to ``admin``.

        The provider subject is matched exactly (case-sensitive), since OIDC
        `sub` values are case-sensitive. It is IdP-assigned and unspoofable, so
        it is never gated on email verification and is the stronger form to use
        in ``admin_users``.
        """
        if email and email.strip().lower() in self._admin_emails:
            if not self.requires_verified_email(provider) or email_verified is True:
                return True
            logger.warning(
                "Admin allowlist email match for %s rejected: %s is not a verified "
                "address on this id_token (email_verified=%r). Use \"%s:%s\" in "
                "admin_users to allowlist this identity by subject instead.",
                provider, email, email_verified, provider, subject,
            )
        return f"{provider}:{subject}" in self._admin_subjects
