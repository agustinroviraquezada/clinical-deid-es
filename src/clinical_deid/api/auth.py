"""Demo login (FR-08, ADR-0006, design §7).

One account whose argon2 hash lives in an environment variable. A successful login sets a
signed, short-lived session cookie (``HttpOnly``, ``Secure``, ``SameSite=Strict``). Failed
attempts are counted per client IP; the counters live in memory, so with several Lambda
instances they are approximate (accepted demo limitation).
"""

import hashlib
import hmac
import logging
import threading
import time
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from fastapi import Cookie, HTTPException, Request

from clinical_deid.config import get_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

COOKIE_NAME = "deid_session"
SESSION_TTL_S = 60 * 60
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_S = 15 * 60

_hasher = PasswordHasher()
# Verified when the username is wrong, so both failures cost the same time (no user enumeration).
_DUMMY_HASH = _hasher.hash("not-the-demo-password")


class LoginAttempts:
    """Failed login timestamps per client, within a sliding window."""

    def __init__(self, limit: int = MAX_FAILED_ATTEMPTS, window_s: float = LOCKOUT_WINDOW_S):
        self._limit = limit
        self._window_s = window_s
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, client: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(client, []) if now - t < self._window_s]
        if recent:
            self._failures[client] = recent
        else:
            self._failures.pop(client, None)
        return recent

    def is_locked(self, client: str) -> bool:
        with self._lock:
            return len(self._recent(client, time.time())) >= self._limit

    def record_failure(self, client: str) -> None:
        with self._lock:
            now = time.time()
            self._recent(client, now)
            self._failures.setdefault(client, []).append(now)

    def clear(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_attempts = LoginAttempts()


def sign_session(expires_at: int, secret: str) -> str:
    """Cookie value ``<expiry>.<HMAC-SHA256(expiry)>``. It carries no user data."""
    signature = hmac.new(secret.encode(), str(expires_at).encode(), hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def is_valid_session(token: str | None) -> bool:
    """True if the token was signed with the current secret and has not expired."""
    secret = get_settings().session_secret
    if not token or secret is None:
        return False
    expiry, _, _ = token.partition(".")
    if not expiry.isdigit():
        return False
    expected = sign_session(int(expiry), secret.get_secret_value())
    return hmac.compare_digest(token, expected) and int(expiry) > time.time()


def verify_credentials(username: str, password: str) -> bool:
    """Check the demo credentials. Fails closed when the secrets are not configured."""
    settings = get_settings()
    stored = settings.demo_password_hash
    if stored is None or settings.session_secret is None:
        return False
    user_ok = hmac.compare_digest(username.encode(), settings.demo_username.encode())
    target = stored.get_secret_value() if user_ok else _DUMMY_HASH
    try:
        password_ok = _hasher.verify(target, password)
    except InvalidHashError:
        logger.error("login misconfigured: DEMO_PASSWORD_HASH is not an argon2 hash")
        return False
    except Argon2Error:
        password_ok = False
    return user_ok and password_ok


def new_session_token() -> str:
    """A fresh signed token valid for SESSION_TTL_S."""
    secret = get_settings().session_secret
    if secret is None:  # pragma: no cover - verify_credentials already refused
        raise RuntimeError("SESSION_SECRET is not configured")
    return sign_session(int(time.time()) + SESSION_TTL_S, secret.get_secret_value())


def client_id(request: Request) -> str:
    """Client IP as seen by the app (the Function URL source IP behind Mangum)."""
    return request.client.host if request.client else "unknown"


def require_session(
    session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> None:
    """Dependency for protected routes: 401 without a valid session cookie."""
    if not is_valid_session(session):
        raise HTTPException(status_code=401, detail="Not authenticated")
