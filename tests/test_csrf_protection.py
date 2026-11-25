
"""Task #46: CSRF protection tests for browser forms."""

import importlib
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_session
from app.routers import router, static_files


login_routes = importlib.import_module("app.routers.login")
register_routes = importlib.import_module("app.routers.register")
config_routes = importlib.import_module("app.routers.server_config")


def extract_csrf_token(html: str) -> str:
    """Extract the hidden CSRF token from a rendered form."""

    match = re.search(
        r'name="csrf_token"\s+value="([^"]+)"',
        html,
    )

    assert match is not None, "CSRF token is missing"

    return match.group(1)


@pytest.fixture
def csrf_client(monkeypatch):
    """Create an isolated website with session support."""

    app = FastAPI()

    app.add_middleware(
        SessionMiddleware,
        secret_key="task46-security-test-secret",
    )

    app.include_router(router)

    app.mount(
        "/static",
        static_files,
        name="static",
    )

    def fake_session():
        yield object()

    app.dependency_overrides[get_session] = fake_session

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:
        yield client


@pytest.mark.parametrize(
    "path",
    ["/login", "/register"],
)
def test_public_forms_display_csrf_token(
    csrf_client,
    path,
):
    response = csrf_client.get(path)

    assert response.status_code == 200

    token = extract_csrf_token(response.text)

    assert len(token) >= 32


@pytest.mark.parametrize(
    "path,data",
    [
        (
            "/login",
            {
                "username": "student",
                "password": "stud-dev",
            },
        ),
        (
            "/register",
            {
                "username": "new_student",
                "email": "new@example.com",
                "password": "test-password",
                "role": "student",
                "entry_path": "incoming",
            },
        ),
    ],
)
def test_missing_csrf_token_is_rejected(
    csrf_client,
    path,
    data,
):
    response = csrf_client.post(
        path,
        data=data,
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "path,data",
    [
        (
            "/login",
            {
                "username": "student",
                "password": "stud-dev",
            },
        ),
        (
            "/register",
            {
                "username": "new_student",
                "email": "new@example.com",
                "password": "test-password",
                "role": "student",
                "entry_path": "incoming",
            },
        ),
    ],
)
def test_invalid_csrf_token_is_rejected(
    csrf_client,
    path,
    data,
):
    csrf_client.get(path)

    response = csrf_client.post(
        path,
        data={
            **data,
            "csrf_token": "invalid-security-token",
        },
    )

    assert response.status_code == 403


def test_valid_login_token_allows_authentication(
    csrf_client,
    monkeypatch,
):
    """A valid CSRF token allows normal authentication."""

    class FakeRepository:
        def __init__(self, db):
            self.db = db

        def get_by_username(self, username):
            return SimpleNamespace(
                username=username,
                role="student",
            )

    class FakeAuthService:
        def __init__(self, repo):
            self.repo = repo

        def authenticate_user(
            self,
            username,
            password,
        ):
            if (
                username == "student"
                and password == "correct-password"
            ):
                return "fake-test-access-token"

            return None

    monkeypatch.setattr(
        login_routes,
        "UserRepository",
        FakeRepository,
    )

    monkeypatch.setattr(
        login_routes,
        "AuthService",
        FakeAuthService,
    )

    page = csrf_client.get("/login")
    token = extract_csrf_token(page.text)

    response = csrf_client.post(
        "/login",
        data={
            "username": "student",
            "password": "correct-password",
            "csrf_token": token,
        },
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/app")
    assert "access_token" in response.cookies


def test_valid_registration_token_allows_registration(
    csrf_client,
    monkeypatch,
):
    """A valid token allows normal account registration."""

    registered = []

    class FakeRepository:
        def __init__(self, db):
            self.db = db

    class FakeAuthService:
        def __init__(self, repo):
            self.repo = repo

        def register_user(
            self,
            username,
            email,
            password,
            *,
            role,
            entry_path,
            student_id,
        ):
            registered.append(
                {
                    "username": username,
                    "email": email,
                    "role": role,
                }
            )

    monkeypatch.setattr(
        register_routes,
        "UserRepository",
        FakeRepository,
    )

    monkeypatch.setattr(
        register_routes,
        "AuthService",
        FakeAuthService,
    )

    page = csrf_client.get("/register")
    token = extract_csrf_token(page.text)

    response = csrf_client.post(
        "/register",
        data={
            "username": "new_student",
            "email": "new@example.com",
            "password": "test-password",
            "role": "student",
            "entry_path": "incoming",
            "csrf_token": token,
        },
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")

    assert len(registered) == 1
    assert registered[0]["username"] == "new_student"


def test_config_login_rejects_missing_token(
    csrf_client,
    monkeypatch,
):
    monkeypatch.setattr(
        config_routes,
        "_panel_enabled",
        lambda: True,
    )

    response = csrf_client.post(
        "/config/login",
        data={
            "password": "test-ops-password",
        },
    )

    assert response.status_code == 403


def test_config_login_rejects_invalid_token(
    csrf_client,
    monkeypatch,
):
    monkeypatch.setattr(
        config_routes,
        "_panel_enabled",
        lambda: True,
    )

    csrf_client.get("/config/login")

    response = csrf_client.post(
        "/config/login",
        data={
            "password": "test-ops-password",
            "csrf_token": "incorrect-token",
        },
    )

    assert response.status_code == 403


@pytest.fixture
def unlocked_config_client(
    csrf_client,
    monkeypatch,
):
    """Unlock a fake config panel without using real settings."""

    monkeypatch.setattr(
        config_routes,
        "_panel_enabled",
        lambda: True,
    )

    monkeypatch.setattr(
        config_routes,
        "get_settings",
        lambda: SimpleNamespace(
            config_password="test-ops-password",
        ),
    )

    page = csrf_client.get("/config/login")

    assert page.status_code == 200

    token = extract_csrf_token(page.text)

    response = csrf_client.post(
        "/config/login",
        data={
            "password": "test-ops-password",
            "csrf_token": token,
        },
    )

    assert response.status_code == 303

    return csrf_client


@pytest.mark.parametrize(
    "path,data",
    [
        ("/config/logout", {}),
        ("/config/actions/restart", {}),
        ("/config/actions/reinit-db", {"drop": "1"}),
        ("/config/actions/seed", {}),
        ("/config/actions/toggle-env", {}),
        (
            "/config/actions/set-env",
            {"mode": "production"},
        ),
        ("/config/actions/ping-db", {}),
        ("/config/actions/dispose-pool", {}),
        ("/config/actions/clear-cache", {}),
    ],
)
def test_config_actions_reject_missing_csrf(
    unlocked_config_client,
    path,
    data,
):
    """Missing tokens must block all config operations."""

    response = unlocked_config_client.post(
        path,
        data=data,
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "path,data",
    [
        ("/config/logout", {}),
        ("/config/actions/restart", {}),
        ("/config/actions/reinit-db", {"drop": "1"}),
        ("/config/actions/seed", {}),
        ("/config/actions/toggle-env", {}),
        (
            "/config/actions/set-env",
            {"mode": "production"},
        ),
        ("/config/actions/ping-db", {}),
        ("/config/actions/dispose-pool", {}),
        ("/config/actions/clear-cache", {}),
    ],
)
def test_config_actions_reject_invalid_csrf(
    unlocked_config_client,
    path,
    data,
):
    """Invalid tokens must block all config operations."""

    response = unlocked_config_client.post(
        path,
        data={
            **data,
            "csrf_token": "invalid-security-token",
        },
    )

    assert response.status_code == 403

