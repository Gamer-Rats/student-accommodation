
"""Task #36: Landlord My Listings dashboard tests."""

import re
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.dependencies.session import get_session
from app.models.listing import Listing
from app.routers import router as browser_router, static_files
from app.services import listings


@pytest.fixture
def dashboard_setup(test_session, monkeypatch):
    """Create an isolated browser app and test listings."""

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {"id": 4, "role": "student"},
    }

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

    current = {"id": 2}

    def authenticated_user():
        user = users[current["id"]]

        return SimpleNamespace(
            id=user["id"],
            role=user["role"],
            username="DashboardTester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="dashboard-test-secret",
    )

    test_app.include_router(browser_router)
    test_app.mount("/static", static_files, name="static")

    test_app.dependency_overrides[get_current_user] = (
        authenticated_user
    )

    test_app.dependency_overrides[get_session] = (
        lambda: None
    )

    client = TestClient(test_app)

    def create(
        title="Test Apartment",
        owner=2,
        status="pending",
        feedback="",
    ):
        listing = Listing(
            landlord_id=owner,
            title=title,
            area="st_augustine",
            price=2500,
            amenities="wifi",
            contact_phone="5551234",
            contact_email="landlord@example.com",
            photos="",
            created_at="2026-11-24T10:00:00+00:00",
            status=status,
            review_feedback=feedback,
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def sign_in(user_id):
        current["id"] = user_id

    return {
        "client": client,
        "create": create,
        "sign_in": sign_in,
    }


def test_landlord_dashboard_loads(dashboard_setup):
    client = dashboard_setup["client"]

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200
    assert "My Listings" in response.text
    assert "Your Properties" in response.text


def test_empty_dashboard(dashboard_setup):
    client = dashboard_setup["client"]

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200
    assert "No Listings Yet" in response.text

    assert re.search(
        r'id="count-total"[^>]*>\s*0\s*</strong>',
        response.text,
    )


def test_landlord_sees_only_own_listings(dashboard_setup):
    create = dashboard_setup["create"]
    client = dashboard_setup["client"]

    create(title="My Own Apartment", owner=2)
    create(title="Someone Else's Apartment", owner=3)

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200
    assert "My Own Apartment" in response.text
    assert "Someone Else's Apartment" not in response.text

    assert re.search(
        r'id="count-total"[^>]*>\s*1\s*</strong>',
        response.text,
    )


def test_dashboard_shows_all_listing_statuses(dashboard_setup):
    create = dashboard_setup["create"]
    client = dashboard_setup["client"]

    statuses = [
        "pending",
        "provisional",
        "approved",
        "active",
        "inactive",
        "rejected",
    ]

    for listing_status in statuses:
        create(
            title=f"Property {listing_status}",
            status=listing_status,
        )

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200

    for listing_status in statuses:
        assert (
            f"Property {listing_status}"
            in response.text
        )


def test_dashboard_summary_counts(dashboard_setup):
    create = dashboard_setup["create"]
    client = dashboard_setup["client"]

    create(status="pending")
    create(status="pending")
    create(status="active")
    create(status="rejected")
    create(status="approved")

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200

    expected = {
        "total": 5,
        "pending": 2,
        "active": 1,
        "rejected": 1,
    }

    for name, number in expected.items():
        assert re.search(
            rf'id="count-{name}"[^>]*>\s*{number}\s*</strong>',
            response.text,
        )


def test_rejected_listing_displays_feedback(dashboard_setup):
    create = dashboard_setup["create"]
    client = dashboard_setup["client"]

    create(
        title="Rejected Property",
        status="rejected",
        feedback="Please correct the phone number.",
    )

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200
    assert "Rejected Property" in response.text
    assert "Please correct the phone number." in response.text
    assert "Edit and Resubmit" in response.text


def test_only_editable_listings_have_edit_links(
    dashboard_setup,
):
    create = dashboard_setup["create"]
    client = dashboard_setup["client"]

    pending_id = create(status="pending")
    rejected_id = create(status="rejected")
    active_id = create(status="active")
    approved_id = create(status="approved")

    response = client.get("/app/landlord/listings")

    assert response.status_code == 200

    assert (
        f"/app/landlord/listings/{pending_id}/edit"
        in response.text
    )

    assert (
        f"/app/landlord/listings/{rejected_id}/edit"
        in response.text
    )

    assert (
        f"/app/landlord/listings/{active_id}/edit"
        not in response.text
    )

    assert (
        f"/app/landlord/listings/{approved_id}/edit"
        not in response.text
    )


@pytest.mark.parametrize("user_id", [1, 4])
def test_non_landlords_cannot_access_dashboard(
    dashboard_setup,
    user_id,
):
    dashboard_setup["sign_in"](user_id)

    response = dashboard_setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 403


def test_dashboard_link_in_landlord_navigation(
    dashboard_setup,
):
    response = dashboard_setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200
    assert "My Listings" in response.text
    assert 'aria-current="page"' in response.text


def test_dashboard_feedback_is_html_escaped(
    dashboard_setup,
):
    dashboard_setup["create"](
        status="rejected",
        feedback="<script>alert('bad')</script>",
    )

    response = dashboard_setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
