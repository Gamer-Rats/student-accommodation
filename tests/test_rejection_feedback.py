
"""Task #33: Administrator rejection feedback tests."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import (
    accommodation,
    router as browser_router,
    static_files,
)
from app.services import listings
from app.utilities.security import create_access_token


@pytest.fixture
def feedback_setup(test_session, monkeypatch):
    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {"id": 4, "role": "student"},
    }

    monkeypatch.setattr(
        listings, "engine", test_session.bind
    )
    monkeypatch.setattr(
        listings, "get_user", users.get
    )
    monkeypatch.setattr(
        accommodation.auth, "get_user", users.get
    )

    def create(
        owner=2,
        status="pending",
        feedback="",
    ):
        row = Listing(
            landlord_id=owner,
            title="Test Accommodation",
            area="st_augustine",
            price=2500,
            amenities="wifi",
            contact_phone="5551234",
            contact_email="owner@example.com",
            photos="",
            created_at="2026-11-24T10:00:00+00:00",
            status=status,
            review_feedback=feedback,
        )

        test_session.add(row)
        test_session.commit()
        test_session.refresh(row)

        return row.id

    def stored(listing_id):
        with Session(test_session.bind) as session:
            row = session.get(Listing, listing_id)
            return row.model_dump()

    return {
        "create": create,
        "stored": stored,
    }


def test_admin_rejection_saves_feedback(feedback_setup):
    listing_id = feedback_setup["create"]()

    result = listings.transition(
        1,
        listing_id,
        "reject",
        review_feedback="  Please correct the address.  ",
    )

    assert result["ok"] is True
    assert result["listing"]["status"] == "rejected"

    saved = feedback_setup["stored"](listing_id)

    assert saved["status"] == "rejected"
    assert saved["review_feedback"] == (
        "Please correct the address."
    )


@pytest.mark.parametrize(
    "feedback",
    [None, "", "  ", "\n\t"],
)
def test_blank_feedback_is_rejected(
    feedback_setup,
    feedback,
):
    listing_id = feedback_setup["create"]()

    result = listings.transition(
        1,
        listing_id,
        "reject",
        review_feedback=feedback,
    )

    assert result["ok"] is False

    saved = feedback_setup["stored"](listing_id)

    assert saved["status"] == "pending"
    assert saved["review_feedback"] == ""


def test_excessively_long_feedback_is_rejected(
    feedback_setup,
):
    listing_id = feedback_setup["create"]()

    result = listings.transition(
        1,
        listing_id,
        "reject",
        review_feedback="x" * 1001,
    )

    assert result["ok"] is False
    assert feedback_setup["stored"](listing_id)["status"] == "pending"


@pytest.mark.parametrize("actor_id", [2, 3, 4, 999])
def test_non_admin_cannot_reject_with_feedback(
    feedback_setup,
    actor_id,
):
    listing_id = feedback_setup["create"]()

    result = listings.transition(
        actor_id,
        listing_id,
        "reject",
        review_feedback="Unauthorized rejection",
    )

    assert result["ok"] is False
    assert feedback_setup["stored"](listing_id)["status"] == "pending"


def test_invalid_transition_does_not_save_feedback(
    feedback_setup,
):
    listing_id = feedback_setup["create"](status="approved")

    result = listings.transition(
        1,
        listing_id,
        "reject",
        review_feedback="Should not be saved",
    )

    assert result["ok"] is False

    saved = feedback_setup["stored"](listing_id)

    assert saved["status"] == "approved"
    assert saved["review_feedback"] == ""


def test_feedback_not_allowed_on_other_actions(
    feedback_setup,
):
    listing_id = feedback_setup["create"]()

    result = listings.transition(
        1,
        listing_id,
        "verify",
        review_feedback="Unexpected feedback",
    )

    assert result["ok"] is False
    assert feedback_setup["stored"](listing_id)["status"] == "pending"


def test_resubmission_clears_old_rejection_reason(
    feedback_setup,
):
    listing_id = feedback_setup["create"](
        status="rejected",
        feedback="Correct the contact information",
    )

    result = listings.transition(
        2,
        listing_id,
        "resubmit",
    )

    assert result["ok"] is True

    saved = feedback_setup["stored"](listing_id)

    assert saved["status"] == "pending"
    assert saved["review_feedback"] == ""


def test_landlord_only_receives_own_feedback(
    feedback_setup,
):
    own_id = feedback_setup["create"](
        owner=2,
        status="rejected",
        feedback="Your listing needs correction",
    )

    feedback_setup["create"](
        owner=3,
        status="rejected",
        feedback="Private feedback for another landlord",
    )

    result = listings.list_for_landlord(2)

    assert result["ok"] is True
    assert len(result["listings"]) == 1
    assert result["listings"][0]["id"] == own_id
    assert result["listings"][0]["review_feedback"] == (
        "Your listing needs correction"
    )


def test_landlord_cannot_directly_edit_feedback(
    feedback_setup,
):
    listing_id = feedback_setup["create"](
        status="rejected",
        feedback="Original administrator feedback",
    )

    result = listings.update_listing(
        2,
        listing_id,
        review_feedback="Changed by landlord",
    )

    assert result["ok"] is False
    assert feedback_setup["stored"](listing_id)["review_feedback"] == (
        "Original administrator feedback"
    )


def test_api_accepts_administrator_rejection_feedback(
    feedback_setup,
):
    listing_id = feedback_setup["create"]()

    test_app = FastAPI()
    test_app.include_router(
        accommodation.router,
        prefix="/api",
    )

    client = TestClient(test_app)

    token = create_access_token({"sub": "1"})

    response = client.post(
        f"/api/listings/{listing_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "action": "reject",
            "review_feedback": "Missing property details",
        },
    )

    assert response.status_code == 200

    saved = feedback_setup["stored"](listing_id)

    assert saved["status"] == "rejected"
    assert saved["review_feedback"] == "Missing property details"


def test_api_rejects_missing_feedback(
    feedback_setup,
):
    listing_id = feedback_setup["create"]()

    test_app = FastAPI()
    test_app.include_router(
        accommodation.router,
        prefix="/api",
    )

    client = TestClient(test_app)

    token = create_access_token({"sub": "1"})

    response = client.post(
        f"/api/listings/{listing_id}/transition",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "reject"},
    )

    assert response.status_code == 400
    assert feedback_setup["stored"](listing_id)["status"] == "pending"


def test_landlord_feedback_page_is_owner_scoped(
    feedback_setup,
):
    feedback_setup["create"](
        owner=2,
        status="rejected",
        feedback="Correct your property details",
    )

    feedback_setup["create"](
        owner=3,
        status="rejected",
        feedback="Another landlord's private feedback",
    )

    test_app = FastAPI()
    test_app.add_middleware(
        SessionMiddleware,
        secret_key="test-session-secret",
    )
    test_app.include_router(browser_router)
    test_app.mount(
        "/static",
        static_files,
        name="static",
    )

    test_app.dependency_overrides[get_current_user] = (
        lambda: SimpleNamespace(
            id=2,
            role="landlord",
            username="testlandlord",
        )
    )

    client = TestClient(test_app)

    response = client.get(
        "/app/landlord/rejections"
    )

    assert response.status_code == 200
    assert "Correct your property details" in response.text
    assert (
        "Another landlord's private feedback"
        not in response.text
    )
