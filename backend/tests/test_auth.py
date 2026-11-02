from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit import redact
from app.main import create_app
from app.models import AuthSession, utcnow
from tests.conftest import PASSWORD


def test_register_sets_httponly_session_cookie_and_returns_csrf(make_account):
    acct = make_account("Owner@Example.com", "Olive Owner")
    assert acct.csrf
    me = acct.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@example.com"  # normalized to lower case


def test_session_cookie_is_httponly_and_samesite_lax(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "cookie@example.com", "full_name": "Cookie", "password": PASSWORD},
    )
    set_cookie = r.headers["set-cookie"]
    assert "hermes_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def test_duplicate_email_is_rejected(make_account):
    make_account("dup@example.com")
    other = make_account("dup@example.com", register=False)
    r = other.client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "full_name": "Other", "password": PASSWORD},
    )
    assert r.status_code == 409


def test_weak_password_rejected_with_policy_messages(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "full_name": "Weak", "password": "short"},
    )
    assert r.status_code == 422
    assert any("at least 12" in msg for msg in r.json()["detail"])


def test_login_failure_messages_do_not_reveal_account_existence(make_account, client):
    make_account("exists@example.com")
    wrong_password = client.post(
        "/api/v1/auth/login", json={"email": "exists@example.com", "password": "Nope-Nope-123"}
    )
    unknown = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "Nope-Nope-123"})
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json()


def test_login_success_after_logout(make_account):
    acct = make_account("relog@example.com")
    assert acct.post("/api/v1/auth/logout").status_code == 204
    assert acct.get("/api/v1/auth/me").status_code == 401
    acct.login()
    assert acct.get("/api/v1/auth/me").status_code == 200


def test_logout_requires_csrf_token(make_account):
    acct = make_account("csrf@example.com")
    r = acct.client.post("/api/v1/auth/logout")  # no X-CSRF-Token header
    assert r.status_code == 403
    assert acct.get("/api/v1/auth/me").status_code == 200


def test_wrong_csrf_token_rejected_for_state_change(make_account):
    acct = make_account("wrongcsrf@example.com")
    r = acct.client.post("/api/v1/orgs", json={"name": "Acme Co"}, headers={"X-CSRF-Token": "forged-value"})
    assert r.status_code == 403


def test_expired_session_is_rejected(make_account, engine):
    acct = make_account("expired@example.com")
    with Session(engine) as db:
        db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert acct.get("/api/v1/auth/me").status_code == 401


def test_revoked_session_is_rejected(make_account, engine):
    acct = make_account("revoked@example.com")
    with Session(engine) as db:
        db.execute(update(AuthSession).values(revoked_at=utcnow()))
        db.commit()
    assert acct.get("/api/v1/auth/me").status_code == 401


def test_session_token_is_stored_only_as_hash(make_account, engine):
    acct = make_account("hashcheck@example.com")
    cookie_value = acct.client.cookies.get("hermes_session")
    with Session(engine) as db:
        rows = db.scalars(select(AuthSession)).all()
        assert rows
        assert all(row.token_hash != cookie_value for row in rows)
        assert all(len(row.token_hash) == 64 for row in rows)


def test_login_rate_limit_blocks_after_threshold(engine, settings):
    settings.login_rate_limit = 3
    app = create_app(settings=settings, engine=engine)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.post("/api/v1/auth/register", json={"email": "rl@example.com", "full_name": "RL", "password": PASSWORD})
    statuses = [
        client.post("/api/v1/auth/login", json={"email": "rl@example.com", "password": "Wrong-Pass-999"}).status_code
        for _ in range(4)
    ]
    assert statuses[-1] == 429


def test_redact_removes_sensitive_metadata_keys():
    cleaned = redact({"role": "admin", "api_key": "x", "Password": "y", "access_token": "z", "reason": "ok"})
    assert cleaned == {"role": "admin", "reason": "ok"}


def test_security_headers_present(client):
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Request-ID"]


def test_readiness_reports_database_ok(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
