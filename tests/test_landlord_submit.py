
"""Task #42: Landlord listing submission website tests."""

import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router, static_files
from app.services import listings


@pytest.fixture
def submit_setup(test_session, monkeypatch):
    """Create an isolated application and database."""

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
        secret_key="task42-test-secret",
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

    with TestClient(
        test_app,
        follow_redirects=False,
    ) as client:

        def sign_in(user_id):
            current["id"] = user_id

        def get_csrf():
            response = client.get(
                "/app/landlord/listings/new"
            )

            assert response.status_code == 200

            match = re.search(
                r'name="csrf_token"\s+value="([^"]+)"',
                response.text,
            )

            assert match is not None

            return match.group(1)

        def submit(
            csrf_token,
            **changes,
        ):
            data = {
                "csrf_token": csrf_token,
                "title": "Test Apartment Near UWI",
                "area": "st_augustine",
                "price": "2500",
                "amenities": "wifi, parking",
                "contact_phone": "868-555-1234",
                "contact_email": "landlord@example.com",
                "photos": "",
            }

            data.update(changes)

            return client.post(
                "/app/landlord/listings/new",
                data=data,
            )

        def stored_listings():
            test_session.expire_all()

            return test_session.exec(
                select(Listing)
            ).all()

        yield {
            "client": client,
            "sign_in": sign_in,
            "get_csrf": get_csrf,
            "submit": submit,
            "stored_listings": stored_listings,
        }


def test_landlord_can_open_submission_form(
    submit_setup,
):
    response = submit_setup["client"].get(
        "/app/landlord/listings/new"
    )

    assert response.status_code == 200

    assert "Submit Accommodation Listing" in response.text
    assert 'name="title"' in response.text
    assert 'name="area"' in response.text
    assert 'name="price"' in response.text
    assert 'name="csrf_token"' in response.text


def test_landlord_can_submit_listing(
    submit_setup,
):
    token = submit_setup["get_csrf"]()

    response = submit_setup["submit"](token)

    assert response.status_code == 303

    assert response.headers["location"].endswith(
        "/app/landlord/listings"
    )

    rows = submit_setup["stored_listings"]()

    assert len(rows) == 1

    listing = rows[0]

    assert listing.title == "Test Apartment Near UWI"
    assert listing.landlord_id == 2
    assert listing.area == "st_augustine"
    assert listing.price == 2500
    assert listing.status == "pending"
    assert listing.amenities == "wifi, parking"


def test_student_cannot_open_submission_form(
    submit_setup,
):
    submit_setup["sign_in"](3)

    response = submit_setup["client"].get(
        "/app/landlord/listings/new"
    )

    assert response.status_code == 403


def test_student_cannot_submit_listing(
    submit_setup,
):
    token = submit_setup["get_csrf"]()

    submit_setup["sign_in"](3)

    response = submit_setup["submit"](token)

    assert response.status_code == 403

    assert len(
        submit_setup["stored_listings"]()
    ) == 0


def test_missing_csrf_token_is_rejected(
    submit_setup,
):
    response = submit_setup["submit"]("")

    assert response.status_code == 403

    assert len(
        submit_setup["stored_listings"]()
    ) == 0


def test_invalid_csrf_token_is_rejected(
    submit_setup,
):
    submit_setup["get_csrf"]()

    response = submit_setup["submit"](
        "invalid-security-token"
    )

    assert response.status_code == 403

    assert len(
        submit_setup["stored_listings"]()
    ) == 0


@pytest.mark.parametrize(
    "invalid_price",
    ["abc", "0", "-100"],
)
def test_invalid_price_is_rejected(
    submit_setup,
    invalid_price,
):
    token = submit_setup["get_csrf"]()

    response = submit_setup["submit"](
        token,
        price=invalid_price,
    )

    assert response.status_code == 303

    assert response.headers["location"].endswith(
        "/app/landlord/listings/new"
    )

    assert len(
        submit_setup["stored_listings"]()
    ) == 0


def test_invalid_location_is_rejected(
    submit_setup,
):
    token = submit_setup["get_csrf"]()

    response = submit_setup["submit"](
        token,
        area="port_of_spain",
    )

    assert response.status_code == 303

    assert len(
        submit_setup["stored_listings"]()
    ) == 0


def test_listing_uses_logged_in_landlord(
    submit_setup,
):
    token = submit_setup["get_csrf"]()

    submit_setup["sign_in"](4)

    response = submit_setup["submit"](token)

    assert response.status_code == 303

    rows = submit_setup["stored_listings"]()

    assert len(rows) == 1
    assert rows[0].landlord_id == 4
    assert rows[0].status == "pending"

