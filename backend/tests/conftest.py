import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base
from app.main import create_app
from app.models import AuditEvent  # noqa: F401  (ensure all models are registered on Base.metadata)

PASSWORD = "Correct-Horse-42!"


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from sqlalchemy import event

    @event.listens_for(eng, "connect")
    def _fk(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def settings():
    return Settings(
        env="test",
        database_url="sqlite://",
        cookie_secure=False,
        cors_origins=["http://localhost:3000"],
        login_rate_limit=100,
        login_rate_window_seconds=900,
        scheduler_enabled=False,
        # A throwaway key per test, so tests never touch the developer's key file.
        credential_encryption_key=Fernet.generate_key().decode("ascii"),
    )


@pytest.fixture()
def app(engine, settings):
    return create_app(settings=settings, engine=engine)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


class Account:
    """Helper that owns a TestClient cookie jar and tracks the CSRF token for one user."""

    def __init__(self, app, email: str, full_name: str = "Test User"):
        self.client = TestClient(app)
        self.email = email
        self.full_name = full_name
        self.csrf = None
        self.user_id = None

    def register(self):
        r = self.client.post(
            "/api/v1/auth/register",
            json={"email": self.email, "full_name": self.full_name, "password": PASSWORD},
        )
        assert r.status_code == 201, r.text
        self._absorb(r.json())
        return r

    def login(self):
        r = self.client.post("/api/v1/auth/login", json={"email": self.email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self._absorb(r.json())
        return r

    def _absorb(self, body):
        self.csrf = body["csrf_token"]
        self.user_id = body["user"]["id"]

    def headers(self):
        return {"X-CSRF-Token": self.csrf}

    def post(self, url, **kw):
        return self.client.post(url, headers=self.headers(), **kw)

    def patch(self, url, **kw):
        return self.client.patch(url, headers=self.headers(), **kw)

    def delete(self, url, **kw):
        return self.client.delete(url, headers=self.headers(), **kw)

    def get(self, url, **kw):
        return self.client.get(url, **kw)


@pytest.fixture()
def make_account(app):
    def _make(email: str, full_name: str = "Test User", register: bool = True) -> Account:
        acct = Account(app, email, full_name)
        if register:
            acct.register()
        return acct

    return _make
