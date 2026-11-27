"""Demo login (T4.2, FR-08, ADR-0006): hash, signed cookie, attempt limit and 401."""

import logging
import time

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from clinical_deid.adapters.disabled_llm import DisabledVerifier
from clinical_deid.adapters.fakes import FakeDetector
from clinical_deid.api import auth
from clinical_deid.api.app import app, get_cascade
from clinical_deid.cascade import Cascade
from clinical_deid.config import Settings

pytestmark = pytest.mark.security

USERNAME = "demo"
PASSWORD = "contraseña-de-prueba-123"
SECRET = "test-session-secret-0123456789abcdef"
NOTE = "Paciente Lucía Fernández ingresó en Teruel."

PASSWORD_HASH = PasswordHasher().hash(PASSWORD)


@pytest.fixture
def settings(monkeypatch) -> Settings:
    configured = Settings(
        demo_username=USERNAME, demo_password_hash=PASSWORD_HASH, session_secret=SECRET
    )
    monkeypatch.setattr(auth, "get_settings", lambda: configured)
    return configured


@pytest.fixture(autouse=True)
def isolated_app(settings):
    """Fake model, empty attempt counters and no overrides left behind."""
    cascade = Cascade(FakeDetector([]), DisabledVerifier(), threshold=0.85, max_llm_calls=0)
    app.dependency_overrides[get_cascade] = lambda: cascade
    auth.login_attempts.reset()
    yield
    app.dependency_overrides.clear()
    auth.login_attempts.reset()


@pytest.fixture
def client() -> TestClient:
    # https: the browser (and httpx) only send a Secure cookie over HTTPS.
    return TestClient(app, base_url="https://testserver")


def _login(client: TestClient, username: str = USERNAME, password: str = PASSWORD, **kwargs):
    return client.post("/api/login", json={"username": username, "password": password}, **kwargs)


# ---------- Happy path ----------


def test_login_sets_a_signed_secure_cookie(client):
    response = _login(client)

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{auth.COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie or "SameSite=Strict" in cookie
    assert f"Max-Age={auth.SESSION_TTL_S}" in cookie
    assert PASSWORD not in cookie


def test_logged_in_user_reaches_protected_routes(client):
    _login(client)

    assert client.post("/api/deidentify", json={"text": NOTE}).status_code == 200
    assert client.get("/api/comparison").status_code == 200


def test_logout_ends_the_session(client):
    _login(client)

    assert client.post("/api/logout").status_code == 200
    assert client.post("/api/deidentify", json={"text": NOTE}).status_code == 401


# ---------- 401 ----------


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/deidentify"), ("get", "/api/comparison"), ("post", "/api/logout")],
)
def test_protected_routes_return_401_without_a_session(client, method, path):
    kwargs = {"json": {"text": NOTE}} if path == "/api/deidentify" else {}

    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.parametrize("path", ["/", "/api/health", "/static/app.js"])
def test_public_routes_need_no_session(client, path):
    assert client.get(path).status_code == 200


def test_tampered_cookie_is_rejected(client):
    expires = int(time.time()) + 600
    token = auth.sign_session(expires, SECRET)
    forged = f"{expires + 10_000}.{token.split('.', 1)[1]}"
    client.cookies.set(auth.COOKIE_NAME, forged)

    assert client.get("/api/comparison").status_code == 401


def test_cookie_signed_with_another_secret_is_rejected(client):
    client.cookies.set(auth.COOKIE_NAME, auth.sign_session(int(time.time()) + 600, "other"))

    assert client.get("/api/comparison").status_code == 401


def test_expired_cookie_is_rejected(client):
    client.cookies.set(auth.COOKIE_NAME, auth.sign_session(int(time.time()) - 1, SECRET))

    assert client.get("/api/comparison").status_code == 401


@pytest.mark.parametrize("value", ["", "garbage", "abc.def", "1.2.3"])
def test_malformed_cookie_is_rejected(client, value):
    client.cookies.set(auth.COOKIE_NAME, value)

    assert client.get("/api/comparison").status_code == 401


def test_wrong_password_and_unknown_user_get_the_same_generic_401(client):
    wrong_password = _login(client, password="otra")
    unknown_user = _login(client, username="admin")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json() == {"detail": "Invalid credentials"}
    assert "set-cookie" not in wrong_password.headers


def test_login_fails_closed_when_secrets_are_not_configured(client, monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: Settings(demo_username=USERNAME))

    assert _login(client).status_code == 401


def test_invalid_login_body_is_400(client):
    response = client.post("/api/login", json={"username": USERNAME})

    assert response.status_code == 400


# ---------- Attempt limit ----------


def test_too_many_failures_lock_out_even_the_right_password(client):
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        assert _login(client, password="otra").status_code == 401

    response = _login(client)

    assert response.status_code == 429
    assert "set-cookie" not in response.headers


def test_lockout_is_per_client(client):
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        _login(client, password="otra")

    other = TestClient(app, base_url="https://testserver", client=("203.0.113.7", 50000))

    assert _login(other).status_code == 200


def test_lockout_expires_after_the_window(client, monkeypatch):
    now = time.time()
    monkeypatch.setattr(auth.time, "time", lambda: now)
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        _login(client, password="otra")

    monkeypatch.setattr(auth.time, "time", lambda: now + auth.LOCKOUT_WINDOW_S + 1)

    assert _login(client).status_code == 200


def test_successful_login_clears_previous_failures(client):
    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        _login(client, password="otra")
    _login(client)

    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        assert _login(client, password="otra").status_code == 401


# ---------- Privacy ----------


def test_logs_never_contain_the_credentials(client, caplog):
    with caplog.at_level(logging.DEBUG):
        _login(client, username="usuario-secreto", password="clave-secreta")
        _login(client)

    logged = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "usuario-secreto" not in logged
    assert "clave-secreta" not in logged
    assert PASSWORD not in logged
    assert "login failed" in logged
    assert "login ok" in logged
