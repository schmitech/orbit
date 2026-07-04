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
from typing import Any, Dict, Optional, Tuple

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

def entra_endpoints(tenant_id: str) -> Dict[str, str]:
    base = f"https://login.microsoftonline.com/{tenant_id}"
    return {
        "issuer": f"{base}/v2.0",
        "jwks_uri": f"{base}/discovery/v2.0/keys",
        "authorize_url": f"{base}/oauth2/v2.0/authorize",
        "token_url": f"{base}/oauth2/v2.0/token",
    }


def auth0_endpoints(domain: str) -> Dict[str, str]:
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
    def __init__(self, providers_config: Dict[str, Any]):
        if not _PYJWT_AVAILABLE:
            raise RuntimeError(
                "auth.providers is enabled but PyJWT is not installed. "
                "Install the 'auth-providers' profile: "
                "./install/setup.sh --profile auth-providers"
            )

        self.default_role = providers_config.get('default_role', 'user')

        # provider_name -> {issuer, audiences, jwks_client}
        self._providers: Dict[str, Dict[str, Any]] = {}

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

    def _build_entra(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = cfg.get('tenant_id')
        client_id = cfg.get('client_id')
        if not tenant_id or not client_id:
            raise ValueError(
                "auth.providers.entra is enabled but requires 'tenant_id' and 'client_id'"
            )
        ep = entra_endpoints(tenant_id)
        return {
            "issuer": ep["issuer"],
            # Entra access tokens carry either the bare app id or the api:// URI.
            "audiences": [client_id, f"api://{client_id}"],
            "jwks_client": PyJWKClient(ep["jwks_uri"], cache_keys=True),
        }

    def _build_auth0(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        domain = cfg.get('domain')
        audience = cfg.get('audience')
        if not domain or not audience:
            raise ValueError(
                "auth.providers.auth0 is enabled but requires 'domain' and 'audience'"
            )
        ep = auth0_endpoints(domain)
        return {
            "issuer": ep["issuer"],
            "audiences": [audience],
            "jwks_client": PyJWKClient(ep["jwks_uri"], cache_keys=True),
        }

    async def validate(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
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

        return True, {
            "provider": provider,
            "external_id": subject,
            "email": claims.get("email") or claims.get("preferred_username"),
        }

    def _match_provider(self, issuer: Optional[str]) -> Optional[str]:
        if not issuer:
            return None
        for name, entry in self._providers.items():
            if entry["issuer"] == issuer:
                return name
        return None

    def _verify_sync(self, token: str, provider: str) -> Dict[str, Any]:
        """Fetch the signing key (blocking, cached) and verify the JWT.

        Runs inside ``asyncio.to_thread`` because PyJWKClient uses blocking
        urllib for the JWKS fetch.
        """
        entry = self._providers[provider]
        signing_key = entry["jwks_client"].get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=entry["audiences"],
            issuer=entry["issuer"],
            leeway=60,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
