
"""Task #49: Admin-hold release and reverification policy tests."""

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
from app.services.admin_hold_policy import (
    release_admin_hold,
    complete_reverification,
)
from app.services.lifecycle import visible_to_students


@pytest.fixture
def hold_setup(test_session, monkeypatch):
    """Use a disposable test database and browser application."""

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {
            "id": 4,
            "role": "student",
            "student_id": "202012345",
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

    current = {"id": 1}

    def authenticated_user():
        actor = users[current["id"]]

        return SimpleNamespace(
            id=actor["id"],
            role=actor["role"],
            username="AdminHoldTester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task49-test-secret",
    )

    test_app.include_router(browser_router)

    test_app.mount(
        "/static",
        static_files,
        name="static",
    )

    test_app.dependency_overrides[
        get_current_user
    ] = authenticated_user

    def create(
        status="inactive",
        admin_hold=False,
        requires_reverification=False,
        **changes,
    ):
        data = {
            "landlord_id": 2,
            "title": "Test Accommodation",
            "area": "st_augustine",
            "price": 2500,
            "amenities": "wifi,parking",
            "contact_phone": "555-1234",
            "contact_email": "landlord@example.com",
            "created_at": "2026-11-25T10:00:00+00:00",
            "status": status,
            "admin_hold": admin_hold,
            "requires_reverification": requires_reverification,
        }

        data.update(changes)

        listing = Listing(**data)

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def stored(listing_id):
        test_session.expire_all()

        listing = test_session.get(
            Listing,
            listing_id,
        )

        assert listing is not None

        return listing.model_dump()

    def sign_in(user_id):
        current["id"] = user_id

    with TestClient(
        test_app,
        follow_redirects=False,
    ) as client:

        def csrf_token():
            response = client.get("/admin/listings")

            assert response.status_code == 200

            match = re.search(
                r'name="csrf_token"\s+value="([^"]+)"',
                response.text,
            )

            if match is None:
                # Render an existing review form to obtain
                # the session's real security token.
                create(status="pending")

                response = client.get("/admin/listings")

                match = re.search(
                    r'name="csrf_token"\s+value="([^"]+)"',
                    response.text,
                )

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

        yield {
            "client": client,
            "create": create,
            "stored": stored,
            "sign_in": sign_in,
            "csrf": csrf_token,
            "submit": submit,
        }


def test_force_deactivation_places_listing_on_hold(
    hold_setup,
):
    setup = hold_setup

    listing_id = setup["create"](status="active")

    result = listings.transition(
        1,
        listing_id,
        "force_deactivate",
    )

    assert result["ok"] is True

    saved = setup["stored"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is True
    assert visible_to_students(saved) is False


def test_admin_can_release_hold(hold_setup):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    result = release_admin_hold(
        1,
        listing_id,
    )

    assert result["ok"] is True

    saved = setup["stored"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is False
    assert saved["requires_reverification"] is True
    assert visible_to_students(saved) is False


def test_release_does_not_allow_immediate_reactivation(
    hold_setup,
):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    assert release_admin_hold(
        1,
        listing_id,
    )["ok"] is True

    result = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert result["ok"] is False

    saved = setup["stored"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["requires_reverification"] is True


def test_admin_can_complete_reverification(hold_setup):
    setup = hold_setup

    listing_id = setup["create"](
        requires_reverification=True,
    )

    result = complete_reverification(
        1,
        listing_id,
    )

    assert result["ok"] is True

    saved = setup["stored"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is False
    assert saved["requires_reverification"] is False
    assert visible_to_students(saved) is False


def test_landlord_can_reactivate_after_reverification(
    hold_setup,
):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    released = release_admin_hold(
        1,
        listing_id,
    )

    assert released["ok"] is True

    verified = complete_reverification(
        1,
        listing_id,
    )

    assert verified["ok"] is True

    activated = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert activated["ok"] is True

    saved = setup["stored"](listing_id)

    assert saved["status"] == "active"
    assert saved["admin_hold"] is False
    assert saved["requires_reverification"] is False
    assert visible_to_students(saved) is True


def test_reverification_cannot_bypass_admin_hold(
    hold_setup,
):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
        requires_reverification=True,
    )

    result = complete_reverification(
        1,
        listing_id,
    )

    assert result["ok"] is False

    saved = setup["stored"](listing_id)

    assert saved["admin_hold"] is True
    assert saved["requires_reverification"] is True


@pytest.mark.parametrize(
    "actor_id",
    [2, 3, 4, 999],
)
def test_non_admin_cannot_release_hold(
    hold_setup,
    actor_id,
):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    result = release_admin_hold(
        actor_id,
        listing_id,
    )

    assert result == {
        "ok": False,
        "error": "admin only",
    }

    assert setup["stored"](listing_id)["admin_hold"] is True


@pytest.mark.parametrize(
    "actor_id",
    [2, 3, 4, 999],
)
def test_non_admin_cannot_complete_reverification(
    hold_setup,
    actor_id,
):
    setup = hold_setup

    listing_id = setup["create"](
        requires_reverification=True,
    )

    result = complete_reverification(
        actor_id,
        listing_id,
    )

    assert result == {
        "ok": False,
        "error": "admin only",
    }

    assert setup["stored"](
        listing_id
    )["requires_reverification"] is True


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "provisional",
        "approved",
        "active",
        "rejected",
    ],
)
def test_hold_release_requires_inactive_listing(
    hold_setup,
    status,
):
    setup = hold_setup

    listing_id = setup["create"](
        status=status,
        admin_hold=True,
    )

    result = release_admin_hold(
        1,
        listing_id,
    )

    assert result["ok"] is False

    saved = setup["stored"](listing_id)

    assert saved["status"] == status
    assert saved["admin_hold"] is True


def test_cannot_release_nonexistent_hold(hold_setup):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=False,
    )

    result = release_admin_hold(
        1,
        listing_id,
    )

    assert result["ok"] is False
    assert setup["stored"](listing_id)["admin_hold"] is False


def test_cannot_complete_unneeded_reverification(
    hold_setup,
):
    setup = hold_setup

    listing_id = setup["create"](
        requires_reverification=False,
    )

    result = complete_reverification(
        1,
        listing_id,
    )

    assert result["ok"] is False

    assert setup["stored"](
        listing_id
    )["requires_reverification"] is False


@pytest.mark.parametrize(
    "status",
    ["pending", "approved", "active"],
)
def test_reverification_requires_inactive_listing(
    hold_setup,
    status,
):
    setup = hold_setup

    listing_id = setup["create"](
        status=status,
        requires_reverification=True,
    )

    result = complete_reverification(
        1,
        listing_id,
    )

    assert result["ok"] is False

    saved = setup["stored"](listing_id)

    assert saved["status"] == status
    assert saved["requires_reverification"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"area": "arima"},
        {"price": 0},
        {"title": ""},
        {"contact_phone": ""},
        {"contact_email": ""},
    ],
)
def test_invalid_details_block_reverification(
    hold_setup,
    changes,
):
    setup = hold_setup

    listing_id = setup["create"](
        requires_reverification=True,
        **changes,
    )

    result = complete_reverification(
        1,
        listing_id,
    )

    assert result["ok"] is False

    saved = setup["stored"](listing_id)

    assert saved["requires_reverification"] is True
    assert saved["status"] == "inactive"


def test_missing_listing_is_rejected(hold_setup):
    assert release_admin_hold(
        1,
        999999,
    )["error"] == "listing not found"

    assert complete_reverification(
        1,
        999999,
    )["error"] == "listing not found"


def test_admin_dashboard_displays_release_button(
    hold_setup,
):
    setup = hold_setup

    setup["create"](admin_hold=True)

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Release Admin Hold" in response.text
    assert 'value="release_admin_hold"' in response.text
    assert "Complete Reverification" not in response.text


def test_admin_dashboard_displays_reverification_button(
    hold_setup,
):
    setup = hold_setup

    setup["create"](
        requires_reverification=True,
    )

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert "Complete Reverification" in response.text
    assert 'value="complete_reverification"' in response.text
    assert "Release Admin Hold" not in response.text


def test_admin_dashboard_hides_actions_when_not_needed(
    hold_setup,
):
    setup = hold_setup

    setup["create"](
        status="inactive",
        admin_hold=False,
        requires_reverification=False,
    )

    response = setup["client"].get("/admin/listings")

    assert response.status_code == 200
    assert 'value="release_admin_hold"' not in response.text
    assert 'value="complete_reverification"' not in response.text


def test_browser_complete_hold_workflow(hold_setup):
    setup = hold_setup

    listing_id = setup["create"](
        status="active",
    )

    token = setup["csrf"]()

    first = setup["submit"](
        listing_id,
        "force_deactivate",
        token,
    )

    assert first.status_code == 303

    saved = setup["stored"](listing_id)
    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is True

    second = setup["submit"](
        listing_id,
        "release_admin_hold",
        token,
    )

    assert second.status_code == 303

    saved = setup["stored"](listing_id)
    assert saved["admin_hold"] is False
    assert saved["requires_reverification"] is True

    # Landlord still cannot activate at this stage.
    blocked = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert blocked["ok"] is False

    third = setup["submit"](
        listing_id,
        "complete_reverification",
        token,
    )

    assert third.status_code == 303

    saved = setup["stored"](listing_id)
    assert saved["status"] == "inactive"
    assert saved["requires_reverification"] is False

    activated = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert activated["ok"] is True
    assert setup["stored"](listing_id)["status"] == "active"


@pytest.mark.parametrize(
    "invalid_token",
    ["", "invalid-csrf-token"],
)
def test_invalid_csrf_blocks_hold_release(
    hold_setup,
    invalid_token,
):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    setup["csrf"]()

    response = setup["submit"](
        listing_id,
        "release_admin_hold",
        invalid_token,
    )

    assert response.status_code == 403
    assert setup["stored"](listing_id)["admin_hold"] is True


@pytest.mark.parametrize(
    "user_id",
    [2, 4],
)
def test_non_admin_cannot_use_browser_hold_controls(
    hold_setup,
    user_id,
):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    token = setup["csrf"]()

    setup["sign_in"](user_id)

    response = setup["submit"](
        listing_id,
        "release_admin_hold",
        token,
    )

    assert response.status_code == 401
    assert setup["stored"](listing_id)["admin_hold"] is True


def test_admin_hold_success_feedback(hold_setup):
    setup = hold_setup

    listing_id = setup["create"](
        admin_hold=True,
    )

    token = setup["csrf"]()

    response = setup["submit"](
        listing_id,
        "release_admin_hold",
        token,
    )

    assert response.status_code == 303

    page = setup["client"].get("/admin/listings")

    assert page.status_code == 200
    assert "Administrative hold released" in page.text
    assert "Complete Reverification" in page.text
