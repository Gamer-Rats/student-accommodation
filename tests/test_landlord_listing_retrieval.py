
"""Task #30: landlord-only listing retrieval tests."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router as browser_router
from app.services import listings


@pytest.fixture
def landlord_setup(test_session, monkeypatch):
    """Use a disposable database and isolated browser router."""

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

    def create(landlord_id=2, status="pending"):
        row = Listing(
            landlord_id=landlord_id,
            title=f"Listing for {landlord_id}",
            area="st_augustine",
            price=2000,
            amenities="wifi",
            contact_phone="555-0000",
            contact_email="landlord@example.com",
            created_at="2026-11-24T10:00:00+00:00",
            status=status,
        )

        test_session.add(row)
        test_session.commit()
        test_session.refresh(row)

        return row.id

    test_app = FastAPI()
    test_app.include_router(browser_router)
    client = TestClient(test_app)

    def sign_in_as(user_id):
        """Simulate a server-authenticated user."""

        role = users.get(user_id, {}).get(
            "role",
            "landlord",
        )

        test_app.dependency_overrides[get_current_user] = (
            lambda: SimpleNamespace(
                id=user_id,
                role=role,
            )
        )

    return {
        "create": create,
        "client": client,
        "app": test_app,
        "sign_in_as": sign_in_as,
    }


def test_landlord_with_no_listings_gets_empty_list(
    landlord_setup,
):
    result = listings.list_for_landlord(2)

    assert result == {
        "ok": True,
        "listings": [],
    }


def test_landlord_sees_only_owned_listings(
    landlord_setup,
):
    create = landlord_setup["create"]

    first = create(
        landlord_id=2,
        status="pending",
    )

    create(
        landlord_id=3,
        status="active",
    )

    second = create(
        landlord_id=2,
        status="rejected",
    )

    result = listings.list_for_landlord(2)

    assert result["ok"] is True

    assert [
        row["id"]
        for row in result["listings"]
    ] == [first, second]

    assert all(
        row["landlord_id"] == 2
        for row in result["listings"]
    )


def test_landlord_sees_all_own_statuses(
    landlord_setup,
):
    statuses = (
        "pending",
        "provisional",
        "approved",
        "active",
        "inactive",
        "rejected",
    )

    for status in statuses:
        landlord_setup["create"](status=status)

    result = listings.list_for_landlord(2)

    assert [
        row["status"]
        for row in result["listings"]
    ] == list(statuses)


@pytest.mark.parametrize(
    "user_id",
    [1, 4, 999],
)
def test_non_landlords_cannot_get_landlord_listings(
    landlord_setup,
    user_id,
):
    landlord_setup["create"]()

    result = listings.list_for_landlord(user_id)

    assert result == {
        "ok": False,
        "error": "landlords only",
    }


def test_browser_data_endpoint_uses_authenticated_owner(
    landlord_setup,
):
    own = landlord_setup["create"](landlord_id=2)

    landlord_setup["create"](landlord_id=3)

    landlord_setup["sign_in_as"](2)

    response = landlord_setup["client"].get(
        "/app/landlord/listings/data"
    )

    assert response.status_code == 200

    assert [
        row["id"]
        for row in response.json()["listings"]
    ] == [own]


def test_other_landlord_cannot_see_first_landlords_data(
    landlord_setup,
):
    landlord_setup["create"](landlord_id=2)

    second = landlord_setup["create"](landlord_id=3)

    landlord_setup["sign_in_as"](3)

    response = landlord_setup["client"].get(
        "/app/landlord/listings/data"
    )

    assert response.status_code == 200

    assert [
        row["id"]
        for row in response.json()["listings"]
    ] == [second]


@pytest.mark.parametrize(
    "user_id",
    [1, 4, 999],
)
def test_browser_data_endpoint_rejects_non_landlords(
    landlord_setup,
    user_id,
):
    landlord_setup["create"]()

    landlord_setup["sign_in_as"](user_id)

    response = landlord_setup["client"].get(
        "/app/landlord/listings/data"
    )

    assert response.status_code == 403


def test_browser_data_endpoint_requires_login(
    landlord_setup,
):
    response = landlord_setup["client"].get(
        "/app/landlord/listings/data"
    )

    assert response.status_code == 401
