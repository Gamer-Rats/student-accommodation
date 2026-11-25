
"""Task #34: Landlord browser editing and resubmission tests."""

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
def edit_setup(test_session, monkeypatch):
    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {"id": 4, "role": "student"},
    }

    monkeypatch.setattr(listings, "engine", test_session.bind)
    monkeypatch.setattr(listings, "get_user", users.get)

    current_actor = {"id": 2, "role": "landlord"}

    def authenticated_user():
        return SimpleNamespace(
            id=current_actor["id"],
            role=current_actor["role"],
            username="testuser",
        )

    test_app = FastAPI()
    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task34-test-session",
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
        owner=2,
        status="rejected",
        feedback="Please correct the listing.",
    ):
        row = Listing(
            landlord_id=owner,
            title="Original Apartment",
            area="st_augustine",
            price=2000,
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

    def sign_in(user_id):
        current_actor["id"] = user_id
        current_actor["role"] = users[user_id]["role"]

    def csrf_for(listing_id):
        response = client.get(
            f"/app/landlord/listings/{listing_id}/edit"
        )

        assert response.status_code == 200

        match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"',
            response.text,
        )

        assert match is not None
        return match.group(1)

    def form_data(token, **changes):
        data = {
            "csrf_token": token,
            "title": "Updated Apartment",
            "area": "mount_hope",
            "price": "2700",
            "amenities": "wifi, parking",
            "contact_phone": "5559876",
            "contact_email": "new@example.com",
            "photos": "",
        }

        data.update(changes)
        return data

    return {
        "client": client,
        "create": create,
        "stored": stored,
        "sign_in": sign_in,
        "csrf_for": csrf_for,
        "form_data": form_data,
    }


def test_landlord_can_open_rejected_listing(edit_setup):
    listing_id = edit_setup["create"]()

    response = edit_setup["client"].get(
        f"/app/landlord/listings/{listing_id}/edit"
    )

    assert response.status_code == 200
    assert "Original Apartment" in response.text
    assert "Please correct the listing." in response.text
    assert "Resubmit for Administrator Review" in response.text


def test_landlord_can_edit_pending_listing(edit_setup):
    listing_id = edit_setup["create"](
        status="pending",
        feedback="",
    )

    token = edit_setup["csrf_for"](listing_id)

    response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/edit",
        data=edit_setup["form_data"](token),
    )

    assert response.status_code == 303

    saved = edit_setup["stored"](listing_id)

    assert saved["title"] == "Updated Apartment"
    assert saved["price"] == 2700
    assert saved["area"] == "mount_hope"
    assert saved["status"] == "pending"


def test_rejected_listing_can_be_corrected_and_resubmitted(
    edit_setup,
):
    listing_id = edit_setup["create"]()
    token = edit_setup["csrf_for"](listing_id)

    edit_response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/edit",
        data=edit_setup["form_data"](token),
    )

    assert edit_response.status_code == 303

    saved = edit_setup["stored"](listing_id)

    assert saved["title"] == "Updated Apartment"
    assert saved["status"] == "rejected"
    assert saved["review_feedback"] == (
        "Please correct the listing."
    )

    response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/resubmit",
        data={"csrf_token": token},
    )

    assert response.status_code == 303

    saved = edit_setup["stored"](listing_id)

    assert saved["status"] == "pending"
    assert saved["review_feedback"] == ""
    assert saved["title"] == "Updated Apartment"


def test_other_landlord_cannot_open_edit_page(edit_setup):
    listing_id = edit_setup["create"](owner=3)

    response = edit_setup["client"].get(
        f"/app/landlord/listings/{listing_id}/edit"
    )

    assert response.status_code == 404


@pytest.mark.parametrize("user_id", [1, 4])
def test_non_landlords_cannot_open_edit_page(
    edit_setup,
    user_id,
):
    listing_id = edit_setup["create"]()
    edit_setup["sign_in"](user_id)

    response = edit_setup["client"].get(
        f"/app/landlord/listings/{listing_id}/edit"
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "listing_status",
    ["approved", "active", "inactive", "provisional"],
)
def test_reviewed_listings_cannot_be_edited(
    edit_setup,
    listing_status,
):
    listing_id = edit_setup["create"](
        status=listing_status,
    )

    response = edit_setup["client"].get(
        f"/app/landlord/listings/{listing_id}/edit"
    )

    assert response.status_code == 409


def test_resubmitting_pending_listing_is_blocked(edit_setup):
    listing_id = edit_setup["create"](
        status="pending",
        feedback="",
    )

    token = edit_setup["csrf_for"](listing_id)

    response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/resubmit",
        data={"csrf_token": token},
    )

    assert response.status_code == 409
    assert edit_setup["stored"](listing_id)["status"] == "pending"


def test_invalid_price_does_not_modify_listing(edit_setup):
    listing_id = edit_setup["create"]()
    token = edit_setup["csrf_for"](listing_id)

    response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/edit",
        data=edit_setup["form_data"](
            token,
            price="-50",
        ),
    )

    assert response.status_code == 303

    saved = edit_setup["stored"](listing_id)

    assert saved["price"] == 2000
    assert saved["title"] == "Original Apartment"


def test_invalid_location_does_not_modify_listing(edit_setup):
    listing_id = edit_setup["create"]()
    token = edit_setup["csrf_for"](listing_id)

    response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/edit",
        data=edit_setup["form_data"](
            token,
            area="arima",
        ),
    )

    assert response.status_code == 303

    saved = edit_setup["stored"](listing_id)

    assert saved["area"] == "st_augustine"
    assert saved["title"] == "Original Apartment"


def test_invalid_csrf_token_is_rejected(edit_setup):
    listing_id = edit_setup["create"]()
    edit_setup["csrf_for"](listing_id)

    response = edit_setup["client"].post(
        f"/app/landlord/listings/{listing_id}/edit",
        data=edit_setup["form_data"]("invalid-token"),
    )

    assert response.status_code == 403
    assert edit_setup["stored"](listing_id)["title"] == (
        "Original Apartment"
    )


def test_rejected_listing_page_has_edit_link(edit_setup):
    listing_id = edit_setup["create"]()

    response = edit_setup["client"].get(
        "/app/landlord/rejections"
    )

    assert response.status_code == 200
    assert (
        f"/app/landlord/listings/{listing_id}/edit"
        in response.text
    )


def test_feedback_is_html_escaped(edit_setup):
    listing_id = edit_setup["create"](
        feedback="<script>alert('bad')</script>",
    )

    response = edit_setup["client"].get(
        f"/app/landlord/listings/{listing_id}/edit"
    )

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text
