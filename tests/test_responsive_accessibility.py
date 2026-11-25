
"""Task #51: Responsive markup and accessibility tests."""

from pathlib import Path
from types import SimpleNamespace
from html.parser import HTMLParser

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


class ElementParser(HTMLParser):
    """Collect HTML elements and their attributes."""

    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def parse_elements(html):
    parser = ElementParser()
    parser.feed(html)
    return parser.elements


def find_elements(html, tag):
    return [
        attrs
        for element_tag, attrs in parse_elements(html)
        if element_tag == tag
    ]


@pytest.fixture
def accessibility_setup(monkeypatch):
    """Create an isolated website for accessibility checks."""

    current = {"role": "student"}
    state = {
        "listings": [
            {
                "id": 81,
                "title": "Accessible Test Flat",
                "area": "st_augustine",
                "price": 2500,
                "amenities": "wifi, parking",
                "contact_phone": "555-0100",
                "contact_email": "landlord@example.com",
            }
        ],
        "error": None,
    }

    def authenticated_user():
        return SimpleNamespace(
            id=7,
            username="AccessibilityTester",
            role=current["role"],
        )

    def fake_browse(student_id, **filters):
        if state["error"]:
            return {
                "ok": False,
                "error": state["error"],
            }

        return {
            "ok": True,
            "listings": state["listings"],
        }

    monkeypatch.setattr(
        user_home,
        "browse_for_students",
        fake_browse,
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
        admin_home.listings,
        "list_all",
        lambda status=None: [],
    )

    app = FastAPI()

    app.add_middleware(
        SessionMiddleware,
        secret_key="task51-accessibility-test-secret",
    )

    app.include_router(browser_router)

    app.mount(
        "/static",
        static_files,
        name="static",
    )

    app.dependency_overrides[
        get_current_user
    ] = authenticated_user

    app.dependency_overrides[
        get_session
    ] = lambda: None

    with TestClient(app) as client:
        yield {
            "client": client,
            "current": current,
            "state": state,
        }


@pytest.mark.parametrize(
    "role,path",
    [
        ("student", "/app"),
        ("landlord", "/app"),
        ("admin", "/admin"),
    ],
)
def test_skip_link_and_main_landmark(
    accessibility_setup,
    role,
    path,
):
    setup = accessibility_setup
    setup["current"]["role"] = role

    response = setup["client"].get(path)

    assert response.status_code == 200

    links = find_elements(response.text, "a")
    mains = find_elements(response.text, "main")

    assert any(
        link.get("href") == "#main-content"
        and "skip-link" in link.get("class", "").split()
        for link in links
    )

    assert any(
        main.get("id") == "main-content"
        for main in mains
    )


@pytest.mark.parametrize(
    "role,path",
    [
        ("student", "/app"),
        ("landlord", "/app"),
        ("admin", "/admin"),
    ],
)
def test_mobile_navigation_has_accessible_toggle(
    accessibility_setup,
    role,
    path,
):
    setup = accessibility_setup
    setup["current"]["role"] = role

    response = setup["client"].get(path)

    assert response.status_code == 200

    buttons = find_elements(response.text, "button")
    panels = find_elements(response.text, "div")

    assert any(
        button.get("aria-controls")
        == "primary-navigation"
        and button.get("aria-expanded") == "false"
        and button.get("aria-label")
        == "Toggle main navigation"
        for button in buttons
    )

    assert any(
        panel.get("id") == "primary-navigation"
        for panel in panels
    )


def test_accessibility_stylesheet_is_loaded(
    accessibility_setup,
):
    response = accessibility_setup["client"].get("/app")

    assert response.status_code == 200
    assert "css/accessibility.css" in response.text

    css_response = accessibility_setup["client"].get(
        "/static/css/accessibility.css"
    )

    assert css_response.status_code == 200
    assert ":focus-visible" in css_response.text
    assert "prefers-reduced-motion" in css_response.text


def test_student_filter_form_is_accessible(
    accessibility_setup,
):
    response = accessibility_setup["client"].get(
        "/app/listings"
    )

    assert response.status_code == 200

    forms = find_elements(response.text, "form")
    labels = find_elements(response.text, "label")
    inputs = find_elements(response.text, "input")
    selects = find_elements(response.text, "select")

    assert any(
        form.get("role") == "search"
        and form.get("aria-label")
        == "Search accommodation listings"
        for form in forms
    )

    label_targets = {
        label.get("for")
        for label in labels
    }

    assert {
        "area",
        "max_price",
        "amenity",
    }.issubset(label_targets)

    assert any(
        element.get("id") == "area"
        for element in selects
    )

    assert any(
        element.get("id") == "max_price"
        and element.get("type") == "number"
        for element in inputs
    )

    assert any(
        element.get("id") == "amenity"
        and element.get("type") == "search"
        for element in inputs
    )


def test_student_results_have_accessible_cards(
    accessibility_setup,
):
    response = accessibility_setup["client"].get(
        "/app/listings"
    )

    assert response.status_code == 200

    headings = find_elements(response.text, "h3")
    articles = find_elements(response.text, "article")
    links = find_elements(response.text, "a")

    assert any(
        heading.get("id") == "listing-title-81"
        for heading in headings
    )

    assert any(
        article.get("aria-labelledby")
        == "listing-title-81"
        for article in articles
    )

    assert any(
        link.get("href", "").endswith("/app/listings/81")
        and link.get("aria-label")
        == "View Details for Accessible Test Flat"
        for link in links
    )


def test_empty_results_have_recovery_link(
    accessibility_setup,
):
    setup = accessibility_setup
    setup["state"]["listings"] = []

    response = setup["client"].get("/app/listings")

    assert response.status_code == 200
    assert "No matching accommodation" in response.text
    assert "Show All Listings" in response.text
    assert "No student listings are available right now." in (
        response.text
    )


def test_search_error_is_announced(
    accessibility_setup,
):
    setup = accessibility_setup
    setup["state"]["error"] = "Test access restriction"

    response = setup["client"].get("/app/listings")

    assert response.status_code == 403

    assert "Test access restriction" in response.text

    alerts = find_elements(response.text, "div")

    assert any(
        element.get("role") == "alert"
        and "alert-warning" in element.get(
            "class", ""
        ).split()
        for element in alerts
    )


def test_search_filter_values_are_preserved(
    accessibility_setup,
):
    response = accessibility_setup["client"].get(
        "/app/listings",
        params={
            "area": "st_augustine",
            "max_price": "4000",
            "amenity": "wifi",
        },
    )

    assert response.status_code == 200

    inputs = find_elements(response.text, "input")
    options = find_elements(response.text, "option")

    assert any(
        element.get("id") == "max_price"
        and element.get("value") == "4000"
        for element in inputs
    )

    assert any(
        element.get("id") == "amenity"
        and element.get("value") == "wifi"
        for element in inputs
    )

    assert any(
        option.get("value") == "st_augustine"
        and "selected" in option
        for option in options
    )
