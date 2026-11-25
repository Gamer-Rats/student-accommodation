"""Task #38: Admin provisional approval and force deactivation tests."""

import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router as browser_router, static_files
from app.services import listings
from app.services.lifecycle import visible_to_students


@pytest.fixture
def admin38_setup(test_session, monkeypatch):
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
            username="Admin38Tester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task38-test-secret",
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

    def create(listing_status="pending"):
        row = Listing(
            landlord_id=2,
            title="Task 38 Test Apartment",
            area="st_augustine",
            price=2500,
            amenities="wifi",
            contact_phone="5551234",
            contact_email="landlord@example.com",
            photos="",
            created_at="2026-11-24T10:00:00+00:00",
            status=listing_status,
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

        pattern = r'name="csrf_token"\s+value="([^"]+)"'
        match = re.search(pattern, response.text)

        # Some listing states have no available review form.
        if match is None:
            create("pending")
            response = client.get("/admin/listings")
            assert response.status_code == 200
            match = re.search(pattern, response.text)

        assert match is not None
        return match.group(1)

    def submit(listing_id, action, token):
        return client.post(
            f"/admin/listings/{listing_id}/review",
            data={
                "action": action,
                "csrf_token": token,
            },
        )

    def sign_in(user_id):
        current["id"] = user_id

    return {
        "client": client,
        "create": create,
        "stored": stored,
        "csrf_token": csrf_token,
        "submit": submit,
        "sign_in": sign_in,
    }


def test_pending_shows_provisional_button(admin38_setup):
    setup = admin38_setup
    setup["create"]("pending")

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Provisionally Accept" in response.text
    assert 'value="provisionally_accept"' in response.text
    assert "Verify Listing" in response.text
    assert "Reject Listing" in response.text
    assert "Force Deactivate" not in response.text


def test_active_shows_force_deactivate_button(admin38_setup):
    setup = admin38_setup
    setup["create"]("active")

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Force Deactivate" in response.text
    assert 'value="force_deactivate"' in response.text
    assert "Provisionally Accept" not in response.text


def test_provisional_shows_verify_only(admin38_setup):
    setup = admin38_setup
    setup["create"]("provisional")

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Verify Listing" in response.text
    assert "Provisionally Accept" not in response.text
    assert "Force Deactivate" not in response.text
    assert "Reject Listing" not in response.text


def test_admin_can_provisionally_accept(admin38_setup):
    setup = admin38_setup
    listing_id = setup["create"]("pending")
    token = setup["csrf_token"]()

    response = setup["submit"](
        listing_id,
        "provisionally_accept",
        token,
    )

    assert response.status_code == 303

    saved = setup["stored"](listing_id)

    assert saved["status"] == "provisional"
    assert saved["admin_hold"] is False
    assert visible_to_students(saved) is False


def test_provisional_listing_can_be_verified(admin38_setup):
    setup = admin38_setup
    listing_id = setup["create"]("pending")
    token = setup["csrf_token"]()

    first = setup["submit"](
        listing_id,
        "provisionally_accept",
        token,
    )

    assert first.status_code == 303
    assert setup["stored"](listing_id)["status"] == "provisional"

    second = setup["submit"](
        listing_id,
        "verify",
        token,
    )

    assert second.status_code == 303
    assert setup["stored"](listing_id)["status"] == "approved"


def test_admin_can_force_deactivate_active_listing(
    admin38_setup,
):
    setup = admin38_setup
    listing_id = setup["create"]("active")
    token = setup["csrf_token"]()

    response = setup["submit"](
        listing_id,
        "force_deactivate",
        token,
    )

    assert response.status_code == 303

    saved = setup["stored"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is True
    assert visible_to_students(saved) is False


def test_forced_deactivation_blocks_reactivation(
    admin38_setup,
):
    setup = admin38_setup
    listing_id = setup["create"]("active")
    token = setup["csrf_token"]()

    setup["submit"](
        listing_id,
        "force_deactivate",
        token,
    )

    # Landlord attempts to reactivate the held listing.
    result = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert result["ok"] is False

    saved = setup["stored"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is True


@pytest.mark.parametrize(
    "initial_status",
    ["provisional", "approved", "active"],
)
def test_provisional_accept_rejects_invalid_states(
    admin38_setup,
    initial_status,
):
    setup = admin38_setup
    listing_id = setup["create"](initial_status)
    token = setup["csrf_token"]()

    response = setup["submit"](
        listing_id,
        "provisionally_accept",
        token,
    )

    assert response.status_code == 303
    assert (
        setup["stored"](listing_id)["status"]
        == initial_status
    )


@pytest.mark.parametrize(
    "initial_status",
    ["pending", "provisional", "inactive"],
)
def test_force_deactivate_rejects_invalid_states(
    admin38_setup,
    initial_status,
):
    setup = admin38_setup
    listing_id = setup["create"](initial_status)
    token = setup["csrf_token"]()

    response = setup["submit"](
        listing_id,
        "force_deactivate",
        token,
    )

    assert response.status_code == 303

    saved = setup["stored"](listing_id)

    assert saved["status"] == initial_status
    assert saved["admin_hold"] is False


@pytest.mark.parametrize(
    "listing_status,action",
    [
        ("pending", "provisionally_accept"),
        ("active", "force_deactivate"),
    ],
)
def test_invalid_csrf_blocks_new_actions(
    admin38_setup,
    listing_status,
    action,
):
    setup = admin38_setup
    listing_id = setup["create"](listing_status)

    setup["csrf_token"]()

    response = setup["submit"](
        listing_id,
        action,
        "invalid-token",
    )

    assert response.status_code == 403
    assert (
        setup["stored"](listing_id)["status"]
        == listing_status
    )


@pytest.mark.parametrize("user_id", [2, 3])
def test_non_admin_cannot_use_new_actions(
    admin38_setup,
    user_id,
):
    setup = admin38_setup
    listing_id = setup["create"]("pending")
    token = setup["csrf_token"]()

    setup["sign_in"](user_id)

    response = setup["submit"](
        listing_id,
        "provisionally_accept",
        token,
    )

    assert response.status_code == 401
    assert setup["stored"](listing_id)["status"] == "pending"

    active_id = setup["create"]("active")

    response = setup["submit"](
        active_id,
        "force_deactivate",
        token,
    )

    assert response.status_code == 401
    assert setup["stored"](active_id)["status"] == "active"


def test_admin_hold_appears_on_dashboard(admin38_setup):
    setup = admin38_setup
    listing_id = setup["create"]("active")
    token = setup["csrf_token"]()

    setup["submit"](
        listing_id,
        "force_deactivate",
        token,
    )

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "On administrative hold" in response.text
    assert "Task 38 Test Apartment" in response.text