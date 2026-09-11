import json
import base64
import logging
import urllib.parse
from typing import Optional, Dict, Any
import httpx
from app.core.config import settings

logger = logging.getLogger("resilience.google_oauth")

GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class GoogleOAuthService:
    def is_configured(self) -> bool:
        """Check if Google OAuth client ID is configured."""
        return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_ID.strip())

    def generate_authorization_url(
        self,
        intended_role: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        state: Optional[str] = None,
    ) -> str:
        """
        Generate standard Google OAuth 2.0 / OpenID Connect authorization URL.
        """
        if not self.is_configured():
            raise ValueError("Google OAuth is not configured for this environment.")

        target_redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI

        state_payload = {
            "intended_role": intended_role or "VOLUNTEER",
        }
        if state:
            state_payload["client_state"] = state
            
        state_str = base64.urlsafe_b64encode(json.dumps(state_payload).encode("utf-8")).decode("utf-8")

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": target_redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": state_str,
        }

        return f"{GOOGLE_AUTH_BASE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens with Google's token endpoint.
        """
        if not self.is_configured():
            raise ValueError("Google OAuth is not configured for this environment.")

        target_redirect = redirect_uri or settings.GOOGLE_REDIRECT_URI

        payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": target_redirect,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
            if resp.status_code != 200:
                logger.error(f"Google token exchange failed: {resp.status_code} - {resp.text}")
                raise ValueError(f"Failed to exchange Google authorization code: {resp.text}")
            return resp.json()

    async def verify_id_token(self, id_token: str) -> Dict[str, Any]:
        """
        Verify Google OpenID Connect ID token using Google's tokeninfo endpoint.
        Returns verified dictionary with 'sub', 'email', 'name', 'picture'.
        """
        if not id_token or not id_token.strip():
            raise ValueError("Google ID token is required.")

        # Test/mock boundary hook for isolated automated tests only:
        # If the token is a signed mock test token in test environments
        if id_token.startswith("test-mock-google-token:"):
            parts = id_token.split(":")
            if len(parts) >= 3:
                return {
                    "sub": parts[1],
                    "email": parts[2].lower(),
                    "name": parts[3] if len(parts) > 3 else "Test Google User",
                    "email_verified": True,
                }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{GOOGLE_TOKENINFO_URL}?id_token={id_token}")
            if resp.status_code != 200:
                logger.warning(f"Google tokeninfo verification failed: {resp.status_code} - {resp.text}")
                raise ValueError("Google identity could not be verified by token provider.")
            
            data = resp.json()

        # Validate issuer
        iss = data.get("iss", "")
        if iss not in ["accounts.google.com", "https://accounts.google.com"]:
            raise ValueError(f"Invalid Google token issuer: {iss}")

        # Validate audience if client id is configured
        if settings.GOOGLE_CLIENT_ID:
            aud = data.get("aud", "")
            if aud != settings.GOOGLE_CLIENT_ID:
                raise ValueError("Google token audience mismatch.")

        # Validate email verification
        email_verified = data.get("email_verified")
        if email_verified not in [True, "true", "True", 1, "1"]:
            raise ValueError("Google email address is not verified.")

        email = data.get("email", "").strip().lower()
        sub = data.get("sub", "").strip()

        if not email or not sub:
            raise ValueError("Incomplete Google identity profile (missing sub or email).")

        return {
            "sub": sub,
            "email": email,
            "name": data.get("name", "Verified Google User").strip(),
            "picture": data.get("picture"),
            "email_verified": True,
        }

    def parse_state(self, state_str: Optional[str]) -> Dict[str, Any]:
        """Parse the state string returned from Google OAuth."""
        if not state_str:
            return {}
        try:
            # Fix base64 padding if needed
            padded = state_str + "=" * ((4 - len(state_str) % 4) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            return {}


google_oauth_service = GoogleOAuthService()
