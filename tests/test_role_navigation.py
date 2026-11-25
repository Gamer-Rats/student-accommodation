
"""Task #35: Role-based navigation tests."""

import re
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.dependencies.session import get_session

from app.routers import (
    router as browser_router,
    static_files,
    user_home,
    admin_home,
)


@pytest.fixture
def navigation_setup(monkeypatch):
    """Create an isolated browser app with selectable user roles."""

    current_user = {"role": "student"}

    def authenticated_user():
        return SimpleNamespace(
            id=1,
            username="NavigationTester",
            role=current_user["role"],
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="navigation-test-secret",
    )

    test_app.include_router(browser_router)
    test_app.mount(
        "/static",
        static_files,
        name="static",
    )

    test_app.dependency_overrides[get_current_user] = (
        authenticated_user
    )

    test_app.dependency_overrides[get_session] = (
        lambda: None
    )

    # Avoid depending on the application's actual database.
    monkeypatch.setattr(
        user_home,
        "browse_for_students",
        lambda student_id, **filters: {
            "ok": True,
            "listings": [],
        },
    )

    monkeypatch.setattr(
        user_home,
        "list_for_landlord",
        lambda landlord_id: {
            "ok": True,
            "listings": [],
        },
    )

    monkeypatch.setattr(
        admin_home,
        "list_all",
        lambda status=None: [],
    )

    client = TestClient(test_app)

    def set_role(role):
        current_user["role"] = role

    return client, set_role


def navigation_html(response):
    """Extract only the main navigation element."""

    match = re.search(
        r'<nav class="app-topnav" '
        r'aria-label="Main navigation">(.*?)</nav>',
        response.text,
        re.DOTALL,
    )

    assert match is not None

    return match.group(1)


def test_student_sees_student_navigation(navigation_setup):
    client, set_role = navigation_setup
    set_role("student")

    response = client.get("/app")

    assert response.status_code == 200

    nav = navigation_html(response)

    assert "Home" in nav
    assert "Browse listings" in nav
    assert "Sign out" in nav

    assert "/app/listings" in nav

    assert "Rejected listings" not in nav
    assert "All listings" not in nav


def test_landlord_sees_landlord_navigation(navigation_setup):
    client, set_role = navigation_setup
    set_role("landlord")

    response = client.get("/app")

    assert response.status_code == 200

    nav = navigation_html(response)

    assert "Home" in nav
    assert "Rejected listings" in nav
    assert "Sign out" in nav

    assert "/app/landlord/rejections" in nav

    assert "Browse listings" not in nav
    assert "All listings" not in nav


def test_admin_sees_admin_navigation(navigation_setup):
    client, set_role = navigation_setup
    set_role("admin")

    response = client.get("/admin")

    assert response.status_code == 200

    nav = navigation_html(response)

    assert "Home" in nav
    assert "All listings" in nav
    assert "Sign out" in nav

    assert "/admin/listings" in nav

    assert "Browse listings" not in nav
    assert "Rejected listings" not in nav


def test_student_home_link(navigation_setup):
    client, set_role = navigation_setup
    set_role("student")

    response = client.get("/app")
    nav = navigation_html(response)

    assert re.search(
        r'href="[^"]*/app"',
        nav,
    )


def test_landlord_home_link(navigation_setup):
    client, set_role = navigation_setup
    set_role("landlord")

    response = client.get("/app")
    nav = navigation_html(response)

    assert re.search(
        r'href="[^"]*/app"',
        nav,
    )


def test_admin_home_link(navigation_setup):
    client, set_role = navigation_setup
    set_role("admin")

    response = client.get("/admin")
    nav = navigation_html(response)

    assert re.search(
        r'href="[^"]*/admin"',
        nav,
    )


@pytest.mark.parametrize(
    "role,path,expected_label",
    [
        ("student", "/app/listings", "Browse listings"),
        ("landlord", "/app/landlord/rejections", "Rejected listings"),
        ("admin", "/admin/listings", "All listings"),
    ],
)
def test_role_link_highlights_current_page(
    navigation_setup,
    role,
    path,
    expected_label,
):
    client, set_role = navigation_setup
    set_role(role)

    response = client.get(path)

    assert response.status_code == 200

    nav = navigation_html(response)

    active_link = re.search(
        r'<a\b[^>]*class="is-active"'
        r'[^>]*aria-current="page"[^>]*>'
        r'\s*' + re.escape(expected_label) + r'\s*</a>',
        nav,
        re.DOTALL,
    )

    assert active_link is not None


def test_student_cannot_access_admin_page(
    navigation_setup,
):
    client, set_role = navigation_setup
    set_role("student")

    response = client.get("/admin")

    assert response.status_code == 401


def test_landlord_cannot_access_admin_page(
    navigation_setup,
):
    client, set_role = navigation_setup
    set_role("landlord")

    response = client.get("/admin")

    assert response.status_code == 401