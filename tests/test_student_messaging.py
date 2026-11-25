
"""Task #44: Student messaging website tests."""

import re
from types import SimpleNamespace

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import select
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.models.message import Message
from app.routers import router, static_files
from app.services import listings


@pytest.fixture
def messaging_setup(test_session, monkeypatch):
    """Create an isolated website and database."""

    users = {
        1: {
            "id": 1,
            "role": "admin",
        },
        2: {
            "id": 2,
            "role": "landlord",
        },
        3: {
            "id": 3,
            "role": "student",
            "student_id": "202012345",
            "provisional": 0,
        },
        4: {
            "id": 4,
            "role": "student",
            "student_id": "202045678",
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

    current = {"id": 3}

    def authenticated_user():
        actor = users[current["id"]]

        return SimpleNamespace(
            id=actor["id"],
            role=actor["role"],
            username="MessagingTester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task44-test-secret",
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
        listing_status="active",
        admin_hold=False,
        requires_reverification=False,
        area="st_augustine",
    ):
        listing = Listing(
            landlord_id=2,
            title="Test Student Apartment",
            area=area,
            price=2500,
            amenities="wifi, parking",
            contact_phone="868-555-1234",
            contact_email="landlord@example.com",
            photos="",
            status=listing_status,
            admin_hold=admin_hold,
            requires_reverification=requires_reverification,
            created_at="2026-11-24T10:00:00+00:00",
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def stored_messages():
        test_session.expire_all()

        return test_session.exec(
            select(Message).order_by(Message.id)
        ).all()

    with TestClient(
        test_app,
        follow_redirects=False,
    ) as client:

        def sign_in(user_id):
            current["id"] = user_id

        def get_csrf(listing_id):
            response = client.get(
                f"/app/listings/{listing_id}"
            )

            assert response.status_code == 200

            match = re.search(
                r'name="csrf_token"\s+value="([^"]+)"',
                response.text,
            )

            assert match is not None

            return match.group(1)

        def send(
            listing_id,
            csrf_token,
            body="Is this accommodation available?",
            **extra_fields,
        ):
            data = {
                "csrf_token": csrf_token,
                "body": body,
            }

            data.update(extra_fields)

            return client.post(
                f"/app/listings/{listing_id}/message",
                data=data,
            )

        yield {
            "client": client,
            "create": create_listing,
            "sign_in": sign_in,
            "csrf": get_csrf,
            "send": send,
            "messages": stored_messages,
        }


def test_active_listing_displays_message_form(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()

    response = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert response.status_code == 200
    assert "Send Message to Landlord" in response.text
    assert 'name="body"' in response.text
    assert 'name="csrf_token"' in response.text
    assert "Send Message" in response.text


def test_student_can_send_message(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()

    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
        body="Can I arrange a viewing?",
    )

    assert response.status_code == 303

    assert response.headers["location"].endswith(
        f"/app/listings/{listing_id}"
    )

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].listing_id == listing_id
    assert messages[0].student_id == 3
    assert messages[0].body == "Can I arrange a viewing?"
    assert messages[0].created_at


def test_message_is_trimmed_before_saving(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
        body="   Is parking available?   ",
    )

    assert response.status_code == 303

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].body == "Is parking available?"


def test_student_can_send_multiple_messages(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    setup["send"](
        listing_id,
        token,
        body="First question",
    )

    setup["send"](
        listing_id,
        token,
        body="Second question",
    )

    messages = setup["messages"]()

    assert len(messages) == 2
    assert messages[0].body == "First question"
    assert messages[1].body == "Second question"


def test_message_uses_authenticated_student(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    setup["send"](
        listing_id,
        token,
        body="Hello landlord",
        student_id="999",
    )

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].student_id == 3


def test_another_verified_student_can_send_message(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()

    setup["sign_in"](4)

    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
    )

    assert response.status_code == 303

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].student_id == 4


def test_provisional_student_can_send_message(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()

    setup["sign_in"](5)

    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
    )

    assert response.status_code == 303

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].student_id == 5


@pytest.mark.parametrize(
    "user_id",
    [1, 2],
)
def test_non_student_cannot_send_message(
    messaging_setup,
    user_id,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    setup["sign_in"](user_id)

    response = setup["send"](
        listing_id,
        token,
    )

    assert response.status_code == 403
    assert len(setup["messages"]()) == 0


def test_ineligible_student_cannot_send_message(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    setup["sign_in"](6)

    response = setup["send"](
        listing_id,
        token,
    )

    assert response.status_code == 303
    assert len(setup["messages"]()) == 0


def test_missing_csrf_token_is_rejected(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()

    response = setup["send"](
        listing_id,
        "",
    )

    assert response.status_code == 403
    assert len(setup["messages"]()) == 0


def test_invalid_csrf_token_is_rejected(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()

    setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        "invalid-security-token",
    )

    assert response.status_code == 403
    assert len(setup["messages"]()) == 0


@pytest.mark.parametrize(
    "body",
    ["", "   ", "\n\t"],
)
def test_empty_message_is_rejected(
    messaging_setup,
    body,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
        body=body,
    )

    assert response.status_code == 303
    assert len(setup["messages"]()) == 0

    page = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert page.status_code == 200
    assert (
        "Please enter a message before sending."
        in page.text
    )
    assert "alert-danger" in page.text


def test_message_over_2000_characters_is_rejected(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
        body="A" * 2001,
    )

    assert response.status_code == 303
    assert len(setup["messages"]()) == 0

    page = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert page.status_code == 200
    assert (
        "Your message cannot exceed 2000 characters."
        in page.text
    )
    assert "alert-danger" in page.text


def test_message_at_2000_characters_is_allowed(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
        body="A" * 2000,
    )

    assert response.status_code == 303

    messages = setup["messages"]()

    assert len(messages) == 1
    assert len(messages[0].body) == 2000


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
def test_unavailable_listing_cannot_receive_message(
    messaging_setup,
    listing_status,
):
    setup = messaging_setup

    active_id = setup["create"]()
    token = setup["csrf"](active_id)

    hidden_id = setup["create"](
        listing_status=listing_status,
    )

    response = setup["send"](
        hidden_id,
        token,
    )

    assert response.status_code == 303

    assert response.headers["location"].endswith(
        "/app/listings"
    )

    assert len(setup["messages"]()) == 0


@pytest.mark.parametrize(
    "restrictions",
    [
        {"admin_hold": True},
        {"requires_reverification": True},
        {"area": "port_of_spain"},
    ],
)
def test_restricted_listing_cannot_receive_message(
    messaging_setup,
    restrictions,
):
    setup = messaging_setup

    active_id = setup["create"]()
    token = setup["csrf"](active_id)

    restricted_id = setup["create"](
        **restrictions
    )

    response = setup["send"](
        restricted_id,
        token,
    )

    assert response.status_code == 303
    assert len(setup["messages"]()) == 0


def test_nonexistent_listing_cannot_receive_message(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["send"](
        999999,
        token,
    )

    assert response.status_code == 303
    assert len(setup["messages"]()) == 0


def test_success_message_appears_after_redirect(
    messaging_setup,
):
    setup = messaging_setup

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["send"](
        listing_id,
        token,
        body="I would like more information.",
    )

    assert response.status_code == 303

    page = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert page.status_code == 200

    assert (
        "Your message has been sent successfully"
        in page.text
    )

    assert len(setup["messages"]()) == 1
