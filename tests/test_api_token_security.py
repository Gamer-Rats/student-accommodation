
"""Task #32: Signed JWT API authentication security tests."""

from datetime import timedelta

import jwt
import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.routers import accommodation
from app.utilities.security import create_access_token


@pytest.fixture
def api_client(monkeypatch):
    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "student"},
    }

    monkeypatch.setattr(
        accommodation.auth,
        "get_user",
        users.get,
    )

    def fake_login(email, password):
        if email == "admin@example.com" and password == "secret123":
            return users[1]
        return None

    monkeypatch.setattr(
        accommodation.auth,
        "login",
        fake_login,
    )

    monkeypatch.setattr(
        accommodation.listings,
        "list_all",
        lambda status=None: [],
    )

    test_app = FastAPI()
    test_app.include_router(
        accommodation.router,
        prefix="/api",
    )

    return TestClient(test_app)


def authorization(user_id, **extra_claims):
    token = create_access_token(
        {"sub": str(user_id), **extra_claims}
    )

    return {
        "Authorization": f"Bearer {token}"
    }


def listing_body():
    return {
        "title": "Test Apartment",
        "area": "St. Augustine",
        "price": 2500,
        "amenities": "wifi",
        "contact_phone": "555-1234",
        "contact_email": "landlord@example.com",
        "photos": "",
    }


def test_login_returns_signed_access_token(api_client):
    response = api_client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "admin"
    assert "password" not in data["user"]

    settings = get_settings()

    payload = jwt.decode(
        data["access_token"],
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert payload["sub"] == "1"


def test_invalid_login_rejected(api_client):
    response = api_client.post(
        "/api/auth/login",
        json={
            "email": "admin@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == 401


def test_missing_token_rejected(api_client):
    response = api_client.get("/api/admin/listings")

    assert response.status_code == 401


def test_forged_user_id_header_rejected(api_client):
    response = api_client.get(
        "/api/admin/listings",
        headers={"X-User-Id": "1"},
    )

    assert response.status_code == 401

    response = api_client.post(
        "/api/landlord/listings",
        headers={"X-User-Id": "2"},
        json=listing_body(),
    )

    assert response.status_code == 401


def test_valid_admin_token_works(api_client):
    response = api_client.get(
        "/api/admin/listings",
        headers=authorization(1),
    )

    assert response.status_code == 200
    assert response.json() == {"listings": []}


def test_token_role_cannot_override_database_role(api_client):
    response = api_client.get(
        "/api/admin/listings",
        headers=authorization(2, role="admin"),
    )

    assert response.status_code == 403


def test_user_id_header_cannot_override_token(api_client):
    headers = authorization(3)
    headers["X-User-Id"] = "1"

    response = api_client.get(
        "/api/admin/listings",
        headers=headers,
    )

    assert response.status_code == 403


def test_unknown_user_token_rejected(api_client):
    response = api_client.get(
        "/api/admin/listings",
        headers=authorization(999),
    )

    assert response.status_code == 401


def test_expired_token_rejected(api_client):
    token = create_access_token(
        {"sub": "1"},
        expires_delta=timedelta(seconds=-10),
    )

    response = api_client.get(
        "/api/admin/listings",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 401


def test_invalid_token_rejected(api_client):
    response = api_client.get(
        "/api/admin/listings",
        headers={
            "Authorization": "Bearer not-a-valid-token"
        },
    )

    assert response.status_code == 401


def test_browser_cookie_works_for_get(api_client):
    token = create_access_token({"sub": "1"})

    api_client.cookies.set("access_token", token)

    response = api_client.get("/api/admin/listings")

    assert response.status_code == 200


def test_browser_cookie_alone_cannot_authorize_post(api_client):
    token = create_access_token({"sub": "2"})

    api_client.cookies.set("access_token", token)

    response = api_client.post(
        "/api/landlord/listings",
        json=listing_body(),
    )

    assert response.status_code == 401


def test_invalid_authorization_cannot_fall_back_to_cookie(api_client):
    token = create_access_token({"sub": "1"})

    api_client.cookies.set("access_token", token)

    response = api_client.get(
        "/api/admin/listings",
        headers={"Authorization": "Basic invalid"},
    )

    assert response.status_code == 401
