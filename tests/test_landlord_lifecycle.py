
"""Task #43: Landlord activation and deactivation website tests."""

import re
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router, static_files
from app.services import listings
from app.services.lifecycle import visible_to_students


@pytest.fixture
def lifecycle_setup(test_session, monkeypatch):
    """Create an isolated website and database for lifecycle testing."""

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "student"},
        4: {"id": 4, "role": "landlord"},
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
            username="TestUser",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task43-test-secret",
    )

    test_app.include_router(router)

    test_app.mount(
        "/static",
        static_files,
        name="static",
    )

    test_app.dependency_overrides[
        get_current_user
    ] = authenticated_user

    def create_listing(
        listing_status="approved",
        owner=2,
        admin_hold=False,
        requires_reverification=False,
    ):
        listing = Listing(
            landlord_id=owner,
            title="Test Accommodation",
            area="st_augustine",
            price=2500,
            amenities="wifi, parking",
            contact_phone="868-555-1234",
            contact_email="landlord@example.com",
            photos="",
            status=listing_status,
            admin_hold=admin_hold,
            requires_reverification=requires_reverification,
            review_feedback="",
            created_at="2026-11-24T10:00:00+00:00",
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def get_listing(listing_id):
        test_session.expire_all()

        listing = test_session.get(
            Listing,
            listing_id,
        )

        assert listing is not None

        return listing.model_dump()

    with TestClient(
        test_app,
        follow_redirects=False,
    ) as client:

        def sign_in(user_id):
            current["id"] = user_id

        def get_csrf():
            response = client.get(
                "/app/landlord/listings"
            )

            assert response.status_code == 200

            match = re.search(
                r'name="csrf_token"\s+value="([^"]+)"',
                response.text,
            )

            if match is None:
                create_listing(
                    listing_status="approved",
                )

                response = client.get(
                    "/app/landlord/listings"
                )

                match = re.search(
                    r'name="csrf_token"\s+value="([^"]+)"',
                    response.text,
                )

            assert match is not None

            return match.group(1)

        def perform_action(
            listing_id,
            action,
            csrf_token,
        ):
            return client.post(
                f"/app/landlord/listings/{listing_id}/lifecycle",
                data={
                    "action": action,
                    "csrf_token": csrf_token,
                },
            )

        yield {
            "client": client,
            "sign_in": sign_in,
            "create": create_listing,
            "stored": get_listing,
            "csrf": get_csrf,
            "action": perform_action,
        }


def test_approved_listing_shows_activate_button(
    lifecycle_setup,
):
    setup = lifecycle_setup

    setup["create"](
        listing_status="approved",
    )

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200
    assert "Activate Listing" in response.text


def test_landlord_can_activate_approved_listing(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 303

    listing = setup["stored"](listing_id)

    assert listing["status"] == "active"
    assert visible_to_students(listing) is True


def test_landlord_can_deactivate_active_listing(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="active",
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "deactivate",
        token,
    )

    assert response.status_code == 303

    listing = setup["stored"](listing_id)

    assert listing["status"] == "inactive"
    assert visible_to_students(listing) is False


def test_landlord_can_reactivate_inactive_listing(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="inactive",
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 303

    assert setup["stored"](
        listing_id
    )["status"] == "active"


def test_landlord_cannot_modify_another_landlords_listing(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
        owner=4,
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 404

    assert setup["stored"](
        listing_id
    )["status"] == "approved"


def test_student_cannot_activate_listing(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
    )

    token = setup["csrf"]()

    setup["sign_in"](3)

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 403

    assert setup["stored"](
        listing_id
    )["status"] == "approved"


def test_missing_csrf_token_is_rejected(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
    )

    response = setup["action"](
        listing_id,
        "activate",
        "",
    )

    assert response.status_code == 403

    assert setup["stored"](
        listing_id
    )["status"] == "approved"


def test_invalid_csrf_token_is_rejected(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
    )

    setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        "invalid-token",
    )

    assert response.status_code == 403

    assert setup["stored"](
        listing_id
    )["status"] == "approved"


def test_invalid_action_is_rejected(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "verify",
        token,
    )

    assert response.status_code == 400

    assert setup["stored"](
        listing_id
    )["status"] == "approved"


def test_pending_listing_cannot_be_activated(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="pending",
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 303

    assert setup["stored"](
        listing_id
    )["status"] == "pending"


def test_admin_hold_prevents_reactivation(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="inactive",
        admin_hold=True,
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 303

    listing = setup["stored"](listing_id)

    assert listing["status"] == "inactive"
    assert listing["admin_hold"] is True


def test_reverification_requirement_blocks_activation(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="inactive",
        requires_reverification=True,
    )

    token = setup["csrf"]()

    response = setup["action"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 303

    assert setup["stored"](
        listing_id
    )["status"] == "inactive"


def test_dashboard_hides_activation_under_admin_hold(
    lifecycle_setup,
):
    setup = lifecycle_setup

    setup["create"](
        listing_status="inactive",
        admin_hold=True,
    )

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200

    assert "Reactivation blocked by administrator" in response.text
    assert "Reactivate Listing" not in response.text


def test_dashboard_shows_correct_lifecycle_buttons(
    lifecycle_setup,
):
    setup = lifecycle_setup

    setup["create"](listing_status="approved")
    setup["create"](listing_status="active")
    setup["create"](listing_status="inactive")
    setup["create"](listing_status="pending")

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200

    assert "Activate Listing" in response.text
    assert "Deactivate Listing" in response.text
    assert "Reactivate Listing" in response.text
    assert "Edit Listing" in response.text


def test_listing_status_persists_after_page_refresh(
    lifecycle_setup,
):
    setup = lifecycle_setup

    listing_id = setup["create"](
        listing_status="approved",
    )

    token = setup["csrf"]()

    setup["action"](
        listing_id,
        "activate",
        token,
    )

    response = setup["client"].get(
        "/app/landlord/listings"
    )

    assert response.status_code == 200
    assert "Deactivate Listing" in response.text

    assert setup["stored"](
        listing_id
    )["status"] == "active"
