"""
OIDC Token Validator
====================

Validates access tokens (JWTs) issued by external identity providers
(Microsoft Entra ID and Auth0) so they can be used as bearer tokens against
ORBIT on top of the built-in opaque session tokens.

This is a validation-only component: clients perform the OAuth login and send
the resulting access token as ``Authorization: Bearer <jwt>``. ORBIT verifies
the JWT signature against the provider's JWKS and checks issuer, audience and
expiry. It never initiates an OAuth flow itself.

Only the ``cryptography``-backed ``PyJWT`` package is required; it is installed
via the ``auth-providers`` dependency profile.
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import jwt
    from jwt import PyJWKClient
    _PYJWT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when dependency missing
    _PYJWT_AVAILABLE = False


# Provider endpoint derivations, shared by OIDCValidator (bearer JWT validation)
# and AdminSSOService (browser SSO). Keeping these in one place ensures both
# paths agree on issuer/JWKS/authorize/token URLs for a given provider config.

def entra_endpoints(tenant_id: str) -> dict[str, Any]:
    base = f"https://login.microsoftonline.com/{tenant_id}"
    v2_issuer = f"{base}/v2.0"
    return {
        "issuer": v2_issuer,
        # Entra can mint either v2.0-format or legacy v1.0-format access tokens
        # for the same resource/audience, depending on the app registration's
        # accessTokenAcceptedVersion manifest setting — not something a caller
        # controls per-request. OIDCValidator (bearer access-token validation)
        # accepts both issuer shapes rather than requiring every deployer to
        # find and flip that manifest field. AdminSSOService (ID tokens from
        # the v2.0 token endpoint) only ever sees the v2.0 issuer, so it keeps
        # using the singular "issuer" key above.
        "issuers": [v2_issuer, f"https://sts.windows.net/{tenant_id}/"],
        "jwks_uri": f"{base}/discovery/v2.0/keys",
        "authorize_url": f"{base}/oauth2/v2.0/authorize",
        "token_url": f"{base}/oauth2/v2.0/token",
    }


def auth0_endpoints(domain: str) -> dict[str, str]:
    domain = domain.rstrip('/')
    return {
        "issuer": f"https://{domain}/",
        "jwks_uri": f"https://{domain}/.well-known/jwks.json",
        "authorize_url": f"https://{domain}/authorize",
        "token_url": f"https://{domain}/oauth/token",
    }


class OIDCValidator:
    """Validates external-provider JWTs for the ``entra`` and ``auth0`` providers.

    One :class:`PyJWKClient` is created per enabled provider and reused across
    requests so signing keys are fetched from the provider's JWKS endpoint at
    most once per key rotation (in-memory cached).
    """

    # Providers are selected by matching the token's ``iss`` claim, so tokens
    # are always routed to the JWKS/audience of the issuer that minted them.
    def __init__(self, providers_config: dict[str, Any]):
        if not _PYJWT_AVAILABLE:
            raise RuntimeError(
                "auth.providers is enabled but PyJWT is not installed. "
                "Install the 'auth-providers' profile: "
                "./install/setup.sh --profile auth-providers"
            )

        self.default_role = providers_config.get('default_role', 'user')

        # provider_name -> {issuer, audiences, jwks_client}
        self._providers: dict[str, dict[str, Any]] = {}

        entra = providers_config.get('entra', {})
        if entra.get('enabled'):
            self._providers['entra'] = self._build_entra(entra)

        auth0 = providers_config.get('auth0', {})
        if auth0.get('enabled'):
            self._providers['auth0'] = self._build_auth0(auth0)

        if self._providers:
            logger.info("OIDC validator enabled for providers: %s",
                        ", ".join(sorted(self._providers)))

    @property
    def enabled(self) -> bool:
        """True when at least one external provider is configured."""
        return bool(self._providers)

    def _build_entra(self, cfg: dict[str, Any]) -> dict[str, Any]:
        tenant_id = cfg.get('tenant_id')
        client_id = cfg.get('client_id')
        if not tenant_id or not client_id:
            raise ValueError(
                "auth.providers.entra is enabled but requires 'tenant_id' and 'client_id'"
            )
        ep = entra_endpoints(tenant_id)
        return {
            "issuers": ep["issuers"],
            # Entra access tokens carry either the bare app id or the api:// URI.
            "audiences": [client_id, f"api://{client_id}"],
            "jwks_client": PyJWKClient(ep["jwks_uri"], cache_keys=True),
            # Entra access tokens include `preferred_username` by default (see the
            # fallback chain in validate()), so this is rarely needed — but exposed
            # for parity with auth0 in case a tenant's token shape omits it.
            "email_claim": cfg.get('email_claim', 'email'),
        }

    def _build_auth0(self, cfg: dict[str, Any]) -> dict[str, Any]:
        domain = cfg.get('domain')
        audience = cfg.get('audience')
        if not domain or not audience:
            raise ValueError(
                "auth.providers.auth0 is enabled but requires 'domain' and 'audience'"
            )
        ep = auth0_endpoints(domain)
        return {
            "issuers": [ep["issuer"]],
            "audiences": [audience],
            "jwks_client": PyJWKClient(ep["jwks_uri"], cache_keys=True),
            # Auth0 access tokens issued against a custom API audience carry only
            # bare OAuth claims (sub/aud/exp/scope/...) — email is never included
            # unless an Auth0 Action injects it as a namespaced custom claim
            # (Auth0 requires custom claim keys to be URIs, e.g. "https://your-api/email").
            # Configurable since the namespace is whatever the admin's Action uses.
            "email_claim": cfg.get('email_claim', 'email'),
        }

    async def validate(self, token: str) -> tuple[bool, Optional[dict[str, Any]]]:
        """Validate a provider JWT.

        Returns ``(True, {provider, external_id, email})`` on success, or
        ``(False, None)`` for any invalid, expired, mis-issued or mis-audienced
        token. Fails closed: never raises.
        """
        try:
            # Read the issuer without verifying, only to route to the right
            # provider. The token is fully verified below before we trust it.
            unverified = jwt.decode(token, options={"verify_signature": False})
            issuer = unverified.get("iss")
        except Exception:
            return False, None

        provider = self._match_provider(issuer)
        if provider is None:
            return False, None

        try:
            claims = await asyncio.to_thread(self._verify_sync, token, provider)
        except Exception as e:
            logger.warning("Rejected %s token: %s", provider, e)
            return False, None

        subject = claims.get("sub")
        if not subject:
            return False, None

        entry = self._providers[provider]
        email_claim = entry.get("email_claim", "email")
        # preferred_username/upn/unique_name are all well-known Entra claims that
        # carry the user's email/UPN depending on token version and audience;
        # checked unconditionally since they're safe regardless of provider.
        email = (
            claims.get(email_claim)
            or claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("unique_name")
        )
        return True, {
            "provider": provider,
            "external_id": subject,
            "email": email,
        }

    def _match_provider(self, issuer: Optional[str]) -> Optional[str]:
        if not issuer:
            return None
        for name, entry in self._providers.items():
            if issuer in entry["issuers"]:
                return name
        return None

    def _verify_sync(self, token: str, provider: str) -> dict[str, Any]:
        """Fetch the signing key (blocking, cached) and verify the JWT.

        Runs inside ``asyncio.to_thread`` because PyJWKClient uses blocking
        urllib for the JWKS fetch.
        """
        entry = self._providers[provider]
        signing_key = entry["jwks_client"].get_signing_key_from_jwt(token)
        # A provider may accept more than one issuer shape (e.g. Entra's v1.0
        # and v2.0-format tokens for the same audience — see entra_endpoints()).
        # PyJWT's built-in `issuer` check only supports a single string, so it's
        # disabled here and membership is checked manually below instead.
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=entry["audiences"],
            leeway=60,
            options={"require": ["exp", "iss", "aud", "sub"], "verify_iss": False},
        )
        if claims.get("iss") not in entry["issuers"]:
            raise jwt.InvalidIssuerError(f"Issuer not in {entry['issuers']}")
        return claims
