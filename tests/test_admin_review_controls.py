"""Task #37: Administrator verify/reject browser tests."""

import re
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router as browser_router, static_files
from app.services import listings


@pytest.fixture
def admin_review_setup(test_session, monkeypatch):
    """Create an isolated app and database for admin testing."""

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "student"},
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

    current = {"id": 1}

    def authenticated_user():
        user = users[current["id"]]

        return SimpleNamespace(
            id=user["id"],
            role=user["role"],
            username="ReviewTester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task37-test-secret",
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

    client = TestClient(
        test_app,
        follow_redirects=False,
    )

    def create(
        listing_status="pending",
        title="Test Apartment",
        feedback="",
    ):
        row = Listing(
            landlord_id=2,
            title=title,
            area="st_augustine",
            price=2500,
            amenities="wifi",
            contact_phone="5551234",
            contact_email="landlord@example.com",
            photos="",
            created_at="2026-11-24T10:00:00+00:00",
            status=listing_status,
            review_feedback=feedback,
        )

        test_session.add(row)
        test_session.commit()
        test_session.refresh(row)

        return row.id

    
    def stored(listing_id):
        test_session.expire_all()
        row = test_session.get(Listing, listing_id)
        assert row is not None
        return row.model_dump()


    
    def csrf_token():
        response = client.get("/admin/listings")

        assert response.status_code == 200

        # The page creates a token even when no review
        # buttons are displayed.
        token = client.cookies.get("session")

        if token is None:
            raise AssertionError("Session cookie was not created")

        # Get the actual CSRF token from a pending listing form.
        match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"',
            response.text,
        )

        if match:
            return match.group(1)

        # When all listings are already reviewed, create a
        # pending listing so the form renders a token.
        create(
            listing_status="pending",
            title="CSRF Test Listing",
        )

        response = client.get("/admin/listings")

        match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"',
            response.text,
        )

        assert match is not None
        return match.group(1)


    def sign_in(user_id):
        current["id"] = user_id

    return {
        "client": client,
        "create": create,
        "stored": stored,
        "csrf_token": csrf_token,
        "sign_in": sign_in,
    }


def test_admin_can_view_review_controls(admin_review_setup):
    create = admin_review_setup["create"]
    client = admin_review_setup["client"]

    create()

    response = client.get("/admin/listings")

    assert response.status_code == 200
    assert "Test Apartment" in response.text
    assert "Verify Listing" in response.text
    assert "Reject Listing" in response.text
    assert "Rejection Reason" in response.text


@pytest.mark.parametrize(
    "initial_status",
    ["pending", "provisional"],
)
def test_admin_can_verify_valid_listing(
    admin_review_setup,
    initial_status,
):
    setup = admin_review_setup
    listing_id = setup["create"](
        listing_status=initial_status,
    )

    token = setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "verify",
            "csrf_token": token,
        },
    )

    assert response.status_code == 303

    saved = setup["stored"](listing_id)
    assert saved["status"] == "approved"


def test_admin_can_reject_with_feedback(admin_review_setup):
    setup = admin_review_setup
    listing_id = setup["create"]()

    token = setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "reject",
            "csrf_token": token,
            "review_feedback": (
                "  Please update the property details.  "
            ),
        },
    )

    assert response.status_code == 303

    saved = setup["stored"](listing_id)

    assert saved["status"] == "rejected"
    assert saved["review_feedback"] == (
        "Please update the property details."
    )


@pytest.mark.parametrize(
    "feedback",
    ["", "   ", "\n\t"],
)
def test_rejection_requires_feedback(
    admin_review_setup,
    feedback,
):
    setup = admin_review_setup
    listing_id = setup["create"]()

    token = setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "reject",
            "csrf_token": token,
            "review_feedback": feedback,
        },
    )

    assert response.status_code == 303

    saved = setup["stored"](listing_id)

    assert saved["status"] == "pending"
    assert saved["review_feedback"] == ""


@pytest.mark.parametrize(
    "initial_status",
    ["provisional", "approved"],
)
def test_invalid_rejection_does_not_change_state(
    admin_review_setup,
    initial_status,
):
    setup = admin_review_setup
    listing_id = setup["create"](
        listing_status=initial_status,
    )

    token = setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "reject",
            "csrf_token": token,
            "review_feedback": "Not permitted",
        },
    )

    assert response.status_code == 303
    assert (
        setup["stored"](listing_id)["status"]
        == initial_status
    )


def test_unsupported_review_action_is_blocked(
    admin_review_setup,
):
    setup = admin_review_setup
    listing_id = setup["create"]()

    token = setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "activate",
            "csrf_token": token,
        },
    )

    assert response.status_code == 400
    assert setup["stored"](listing_id)["status"] == "pending"


def test_invalid_csrf_token_is_blocked(admin_review_setup):
    setup = admin_review_setup
    listing_id = setup["create"]()

    setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "verify",
            "csrf_token": "invalid-token",
        },
    )

    assert response.status_code == 403
    assert setup["stored"](listing_id)["status"] == "pending"


@pytest.mark.parametrize("user_id", [2, 3])
def test_non_admin_cannot_review_listings(
    admin_review_setup,
    user_id,
):
    setup = admin_review_setup
    listing_id = setup["create"]()

    setup["csrf_token"]()
    setup["sign_in"](user_id)

    get_response = setup["client"].get("/admin/listings")

    assert get_response.status_code == 401

    post_response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "verify",
            "csrf_token": "invalid-token",
        },
    )

    assert post_response.status_code == 401
    assert setup["stored"](listing_id)["status"] == "pending"


def test_approved_listing_has_no_review_buttons(
    admin_review_setup,
):
    setup = admin_review_setup
    setup["create"](listing_status="approved")

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Verify Listing" not in response.text
    assert "Reject Listing" not in response.text


def test_rejection_feedback_is_visible_and_escaped(
    admin_review_setup,
):
    setup = admin_review_setup

    setup["create"](
        listing_status="rejected",
        feedback="<script>alert('bad')</script>",
    )

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Rejection reason:" in response.text
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_success_message_is_displayed(admin_review_setup):
    setup = admin_review_setup
    listing_id = setup["create"]()

    token = setup["csrf_token"]()

    response = setup["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={
            "action": "verify",
            "csrf_token": token,
        },
    )

    assert response.status_code == 303

    page = setup["client"].get("/admin/listings")

    assert page.status_code == 200
    assert "verified and approved successfully" in page.text