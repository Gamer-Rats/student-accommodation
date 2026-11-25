
"""Task #51: Landlord and administrator accessibility checks."""

from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.models.message import Message
from app.models.user import User
from app.routers import router, static_files
from app.services import listings


class MarkupParser(HTMLParser):
    """Collect HTML start tags and attributes."""

    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def elements(html, tag):
    parser = MarkupParser()
    parser.feed(html)
    return [
        attrs
        for name, attrs in parser.elements
        if name == tag
    ]


@pytest.fixture
def workflow_setup(test_session, monkeypatch):
    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "student"},
    }

    current = {"id": 2}

    monkeypatch.setattr(
        listings,
        "engine",
        test_session.bind,
    )

    monkeypatch.setattr(
        listings,
        "get_user",
        users.get,
    )

    def authenticated_user():
        actor = users[current["id"]]

        return SimpleNamespace(
            id=actor["id"],
            role=actor["role"],
            username="AccessibilityTester",
        )

    def test_database():
        yield test_session

    app = FastAPI()

    app.add_middleware(
        SessionMiddleware,
        secret_key="task51-workflow-test-secret",
    )

    app.include_router(router)

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
    ] = test_database

    def create_listing(status="pending", **changes):
        data = {
            "landlord_id": 2,
            "title": "Accessible Apartment",
            "area": "st_augustine",
            "price": 2500,
            "amenities": "wifi",
            "contact_phone": "555-0100",
            "contact_email": "landlord@example.com",
            "created_at": "2026-11-25T10:00:00+00:00",
            "status": status,
        }

        data.update(changes)

        row = Listing(**data)
        test_session.add(row)
        test_session.commit()
        test_session.refresh(row)

        return row.id

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        def sign_in(user_id):
            current["id"] = user_id

        yield {
            "client": client,
            "sign_in": sign_in,
            "create_listing": create_listing,
            "session": test_session,
        }


def test_landlord_form_has_accessible_labels(
    workflow_setup,
):
    response = workflow_setup["client"].get(
        "/app/landlord/listings/new"
    )

    assert response.status_code == 200

    labels = {
        item.get("for")
        for item in elements(response.text, "label")
    }

    assert {
        "title",
        "area",
        "price",
        "amenities",
        "contact_phone",
        "contact_email",
        "photos",
    }.issubset(labels)

    inputs = elements(response.text, "input")

    assert any(
        item.get("name") == "csrf_token"
        and item.get("type") == "hidden"
        for item in inputs
    )

    assert any(
        item.get("id") == "title"
        and "required" in item
        for item in inputs
    )

    assert "Property Details" in response.text
    assert "Contact Information" in response.text


def test_dashboard_has_keyboard_scrollable_table(
    workflow_setup,
):
    setup = workflow_setup

    setup["create_listing"]()

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200

    regions = elements(response.text, "div")

    assert any(
        item.get("role") == "region"
        and item.get("tabindex") == "0"
        and item.get("aria-label")
        == "Your accommodation listings and available actions"
        for item in regions
    )

    captions = elements(response.text, "caption")
    assert len(captions) == 1

    headers = elements(response.text, "th")
    assert len(headers) == 5
    assert all(
        item.get("scope") == "col"
        for item in headers
    )


def test_dashboard_has_accessible_action_links(
    workflow_setup,
):
    setup = workflow_setup

    listing_id = setup["create_listing"](
        status="pending"
    )

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200

    links = elements(response.text, "a")

    assert any(
        item.get("href", "").endswith(
            f"/app/landlord/listings/{listing_id}/edit"
        )
        and item.get("aria-label")
        == "Edit listing Accessible Apartment"
        for item in links
    )


@pytest.mark.parametrize(
    "status,action",
    [
        ("approved", "activate"),
        ("active", "deactivate"),
        ("inactive", "activate"),
    ],
)
def test_lifecycle_buttons_have_accessible_names(
    workflow_setup,
    status,
    action,
):
    setup = workflow_setup

    setup["create_listing"](status=status)

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200

    buttons = elements(response.text, "button")
    hidden_inputs = elements(response.text, "input")

    assert any(
        item.get("name") == "action"
        and item.get("value") == action
        for item in hidden_inputs
    )

    assert any(
        item.get("aria-label")
        in {
            "Activate listing Accessible Apartment",
            "Deactivate listing Accessible Apartment",
            "Reactivate listing Accessible Apartment",
        }
        for item in buttons
    )


def test_admin_table_has_accessible_caption(
    workflow_setup,
):
    setup = workflow_setup
    setup["sign_in"](1)
    setup["create_listing"]()

    response = setup["client"].get(
        "/admin/listings"
    )

    assert response.status_code == 200

    regions = elements(response.text, "div")

    assert any(
        item.get("role") == "region"
        and item.get("tabindex") == "0"
        and item.get("aria-label")
        == "Accommodation listings and administrator review actions"
        for item in regions
    )

    assert len(
        elements(response.text, "caption")
    ) == 1


def test_admin_rejection_has_help_text(
    workflow_setup,
):
    setup = workflow_setup
    setup["sign_in"](1)
    listing_id = setup["create_listing"]()

    response = setup["client"].get(
        "/admin/listings"
    )

    assert response.status_code == 200

    textareas = elements(response.text, "textarea")

    assert any(
        item.get("id")
        == f"rejection-reason-{listing_id}"
        and item.get("aria-describedby")
        == f"rejection-help-{listing_id}"
        and "required" in item
        for item in textareas
    )


def test_admin_actions_still_available(
    workflow_setup,
):
    setup = workflow_setup
    setup["sign_in"](1)

    setup["create_listing"](
        status="pending"
    )
    setup["create_listing"](
        status="active"
    )
    setup["create_listing"](
        status="inactive",
        admin_hold=True,
    )
    setup["create_listing"](
        status="inactive",
        requires_reverification=True,
    )

    response = setup["client"].get(
        "/admin/listings"
    )

    assert response.status_code == 200

    action_values = {
        item.get("value")
        for item in elements(response.text, "input")
        if item.get("name") == "action"
    }

    assert {
        "verify",
        "provisionally_accept",
        "reject",
        "force_deactivate",
        "release_admin_hold",
        "complete_reverification",
    }.issubset(action_values)


def test_inbox_has_accessible_section(
    workflow_setup,
):
    response = workflow_setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200

    sections = elements(response.text, "section")

    assert any(
        item.get("aria-labelledby")
        == "inquiries-heading"
        for item in sections
    )

    assert "No Messages Yet" in response.text


def test_inbox_message_has_accessible_heading_and_time(
    workflow_setup,
):
    setup = workflow_setup
    session = setup["session"]

    student = User(
        username="student51",
        email="student51@example.com",
        password="test-password",
        role="student",
        display_name="Student Tester",
        student_id="202012345",
    )

    session.add(student)
    session.commit()
    session.refresh(student)

    listing_id = setup["create_listing"](
        status="active"
    )

    message = Message(
        listing_id=listing_id,
        student_id=student.id,
        body="Is this listing available?",
        created_at="2026-11-25T12:00:00+00:00",
    )

    session.add(message)
    session.commit()
    session.refresh(message)

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200

    articles = elements(response.text, "article")
    headings = elements(response.text, "h3")
    times = elements(response.text, "time")

    heading_id = f"message-sender-{message.id}"

    assert any(
        item.get("aria-labelledby") == heading_id
        for item in articles
    )

    assert any(
        item.get("id") == heading_id
        for item in headings
    )

    assert any(
        item.get("datetime")
        == "2026-11-25T12:00:00+00:00"
        for item in times
    )

    assert "Is this listing available?" in response.text


@pytest.mark.parametrize(
    "user_id,path,expected",
    [
        (3, "/app/landlord/listings", 403),
        (3, "/app/landlord/inbox", 403),
        (2, "/admin/listings", 401),
    ],
)
def test_role_restrictions_remain_intact(
    workflow_setup,
    user_id,
    path,
    expected,
):
    setup = workflow_setup
    setup["sign_in"](user_id)

    response = setup["client"].get(path)

    assert response.status_code == expected
