import datetime
import secrets
import time
from typing import Any

import jwt


class TokenAuthError(Exception):
    """Base exception for authentication failures."""


class TokenExpiredError(TokenAuthError):
    """Raised when token is expired."""


class TokenInvalidError(TokenAuthError):
    """Raised when token signature or payload is invalid."""


class AuthManager:
    """Authentication and token lifecycle manager (FR-WEB-03, NFR-09)."""

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret or secrets.token_hex(32)
        self.algorithm = "HS256"
        self._failure_counts: dict[str, int] = {}

    def create_token(self, username: str, ttl_seconds: int = 3600) -> str:
        """Create signed JWT token with explicit expiration time (FR-WEB-03)."""
        now = int(time.time())
        payload = {
            "sub": username,
            "iat": now,
            "exp": now + ttl_seconds,
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify token integrity and expiration without leaking token (NFR-09)."""
        if not token:
            raise TokenInvalidError("Missing token")
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[self.algorithm],
                options={"require": ["exp", "sub"]},
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except jwt.PyJWTError:
            raise TokenInvalidError("Invalid token")

    def record_failure(self, identifier: str) -> int:
        """Increment and return failed login counter for an identifier."""
        cnt = self._failure_counts.get(identifier, 0) + 1
        self._failure_counts[identifier] = cnt
        return cnt

    def get_failure_count(self, identifier: str) -> int:
        """Get current count of failed login attempts."""
        return self._failure_counts.get(identifier, 0)

    def clear_failures(self, identifier: str | None = None) -> None:
        """Clear failure counts."""
        if identifier:
            self._failure_counts.pop(identifier, None)
        else:
            self._failure_counts.clear()


auth_manager = AuthManager()
