"""Task #39: Student listing details page tests."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router as browser_router, static_files
from app.services import listings


@pytest.fixture
def details_setup(test_session, monkeypatch):
    """Create an isolated application and database."""

    users = {
        1: {
            "id": 1,
            "role": "admin",
        },
        2: {
            "id": 2,
            "role": "landlord",
        },
        4: {
            "id": 4,
            "role": "student",
            "student_id": "202012345",
            "provisional": 0,
        },
        5: {
            "id": 5,
            "role": "student",
            "student_id": None,
            "provisional": 1,
        },
        6: {
            "id": 6,
            "role": "student",
            "student_id": None,
            "provisional": 0,
        },
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

    current = {"id": 4}

    def authenticated_user():
        actor = users[current["id"]]

        return SimpleNamespace(
            id=actor["id"],
            role=actor["role"],
            username="StudentDetailsTester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task39-test-secret",
    )

    test_app.include_router(browser_router)
    test_app.mount("/static", static_files, name="static")

    test_app.dependency_overrides[get_current_user] = (
        authenticated_user
    )

    client = TestClient(
        test_app,
        follow_redirects=False,
    )

    def create(
        title="Student Apartment",
        listing_status="active",
        area="st_augustine",
        amenities="wifi, parking",
        photos="",
        admin_hold=False,
        requires_reverification=False,
    ):
        listing = Listing(
            landlord_id=2,
            title=title,
            area=area,
            price=3500,
            amenities=amenities,
            contact_phone="555-0100",
            contact_email="landlord@example.com",
            photos=photos,
            created_at="2026-11-24T10:00:00+00:00",
            status=listing_status,
            admin_hold=admin_hold,
            requires_reverification=requires_reverification,
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


def test_active_listing_details_load(details_setup):
    setup = details_setup
    listing_id = setup["create"]()

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 200
    assert "Student Apartment" in response.text
    assert "St Augustine" in response.text
    assert "3,500" in response.text
    assert "wifi" in response.text
    assert "parking" in response.text
    assert "555-0100" in response.text
    assert "landlord@example.com" in response.text
    assert "Back to Listings" in response.text


def test_browse_page_has_view_details_link(details_setup):
    setup = details_setup
    listing_id = setup["create"]()

    response = setup["client"].get("/app/listings")

    assert response.status_code == 200
    assert "View Details" in response.text
    assert (
        f"/app/listings/{listing_id}"
        in response.text
    )


@pytest.mark.parametrize(
    "listing_status",
    [
        "pending",
        "provisional",
        "approved",
        "inactive",
        "rejected",
    ],
)
def test_unavailable_statuses_are_hidden(
    details_setup,
    listing_status,
):
    setup = details_setup
    listing_id = setup["create"](
        listing_status=listing_status
    )

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 404
    assert "Student Apartment" not in response.text


@pytest.mark.parametrize(
    "restrictions",
    [
        {"admin_hold": True},
        {"requires_reverification": True},
    ],
)
def test_restricted_active_listings_are_hidden(
    details_setup,
    restrictions,
):
    setup = details_setup
    listing_id = setup["create"](**restrictions)

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 404


def test_invalid_location_is_hidden(details_setup):
    setup = details_setup
    listing_id = setup["create"](
        area="arima",
    )

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 404


def test_missing_listing_returns_404(details_setup):
    response = details_setup["client"].get(
        "/app/listings/999999"
    )

    assert response.status_code == 404


@pytest.mark.parametrize("user_id", [1, 2])
def test_non_students_cannot_view_details(
    details_setup,
    user_id,
):
    setup = details_setup
    listing_id = setup["create"]()

    setup["sign_in"](user_id)

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 403


def test_unverified_student_cannot_view_details(
    details_setup,
):
    setup = details_setup
    listing_id = setup["create"]()

    setup["sign_in"](6)

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 403


def test_eligible_provisional_student_can_view_details(
    details_setup,
):
    setup = details_setup
    listing_id = setup["create"]()

    setup["sign_in"](5)

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 200
    assert "Student Apartment" in response.text


def test_listing_text_is_html_escaped(details_setup):
    setup = details_setup

    listing_id = setup["create"](
        title="<script>alert('bad')</script>",
        amenities="<b>wifi</b>, parking",
        photos="javascript:alert(1)",
    )

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
    assert "&lt;b&gt;wifi&lt;/b&gt;" in response.text
    assert 'src="javascript:' not in response.text


def test_valid_photo_url_is_displayed(details_setup):
    setup = details_setup

    listing_id = setup["create"](
        photos="https://example.org/room.jpg",
    )

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 200
    assert (
        'src="https://example.org/room.jpg"'
        in response.text
    )
    assert "Property Photos" in response.text


def test_browse_does_not_expose_hidden_listings(
    details_setup,
):
    setup = details_setup

    active_id = setup["create"](
        title="Visible Property",
        listing_status="active",
    )

    hidden_id = setup["create"](
        title="Hidden Property",
        listing_status="pending",
    )

    response = setup["client"].get("/app/listings")

    assert response.status_code == 200
    assert "Visible Property" in response.text
    assert "Hidden Property" not in response.text

    assert (
        f"/app/listings/{active_id}"
        in response.text
    )

    assert (
        f"/app/listings/{hidden_id}"
        not in response.text
    )