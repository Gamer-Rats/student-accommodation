
"""Tests for messaging restrictions on accommodation listings."""

import pytest

from fastapi import HTTPException
from sqlmodel import select

from app.models.listing import Listing
from app.models.message import Message
from app.routers.accommodation import (
    MessageBody,
    message as message_route,
)
from app.services import listings


@pytest.fixture
def messaging_setup(test_session, monkeypatch):
    """Use an isolated database and mocked users."""

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
            "student_id": None,
            "provisional": 1,
        },
        5: {
            "id": 5,
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
        lambda user_id: users.get(user_id),
    )

    def create(
        *,
        status="active",
        area="st_augustine",
        admin_hold=False,
        requires_reverification=False,
    ):
        listing = Listing(
            landlord_id=2,
            title="Test Accommodation",
            area=area,
            price=2500,
            amenities="wifi,parking",
            contact_phone="555-1234",
            contact_email="landlord@example.com",
            created_at="2026-11-23T10:00:00+00:00",
            status=status,
            admin_hold=admin_hold,
            requires_reverification=requires_reverification,
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def message_count():
        return len(
            test_session.exec(
                select(Message)
            ).all()
        )

    return {
        "create": create,
        "session": test_session,
        "message_count": message_count,
    }


@pytest.mark.parametrize("student_id", [3, 4])
def test_eligible_students_can_message_active_listing(
    messaging_setup,
    student_id,
):
    create = messaging_setup["create"]
    listing_id = create()

    result = listings.send_message(
        student_id,
        listing_id,
        "Is this accommodation available?",
    )

    assert result["ok"] is True
    assert result["message_id"] is not None
    assert messaging_setup["message_count"]() == 1

    messages = messaging_setup["session"].exec(
        select(Message)
    ).all()

    assert messages[0].student_id == student_id
    assert messages[0].listing_id == listing_id


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "provisional",
        "approved",
        "inactive",
        "rejected",
        "unknown",
    ],
)
def test_unavailable_status_blocks_messaging(
    messaging_setup,
    status,
):
    listing_id = messaging_setup["create"](
        status=status
    )

    result = listings.send_message(
        3,
        listing_id,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == "listing not available"
    assert messaging_setup["message_count"]() == 0


@pytest.mark.parametrize(
    "admin_hold,requires_reverification",
    [
        (True, False),
        (False, True),
        (True, True),
    ],
)
def test_restricted_active_listing_blocks_messaging(
    messaging_setup,
    admin_hold,
    requires_reverification,
):
    listing_id = messaging_setup["create"](
        status="active",
        admin_hold=admin_hold,
        requires_reverification=requires_reverification,
    )

    result = listings.send_message(
        3,
        listing_id,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == "listing not available"
    assert messaging_setup["message_count"]() == 0


@pytest.mark.parametrize(
    "area",
    [
        "Arima",
        "Curepe",
        "",
    ],
)
def test_out_of_area_listing_blocks_messaging(
    messaging_setup,
    area,
):
    listing_id = messaging_setup["create"](
        area=area
    )

    result = listings.send_message(
        3,
        listing_id,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == "listing not available"
    assert messaging_setup["message_count"]() == 0


@pytest.mark.parametrize(
    "area",
    [
        "st_augustine",
        "mount_hope",
        "St. Augustine",
    ],
)
def test_valid_locations_allow_messaging(
    messaging_setup,
    area,
):
    listing_id = messaging_setup["create"](
        area=area
    )

    result = listings.send_message(
        3,
        listing_id,
        "Hello",
    )

    assert result["ok"] is True
    assert messaging_setup["message_count"]() == 1


@pytest.mark.parametrize(
    "student_id,expected_error",
    [
        (5, "student eligibility required"),
        (2, "students only"),
        (1, "students only"),
        (999, "students only"),
    ],
)
def test_ineligible_users_cannot_send_messages(
    messaging_setup,
    student_id,
    expected_error,
):
    listing_id = messaging_setup["create"]()

    result = listings.send_message(
        student_id,
        listing_id,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == expected_error
    assert messaging_setup["message_count"]() == 0


def test_missing_listing_is_rejected(
    messaging_setup,
):
    result = listings.send_message(
        3,
        99999,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == "listing not found"
    assert messaging_setup["message_count"]() == 0


@pytest.mark.parametrize(
    "body",
    [
        "",
        " ",
        "\n \t",
    ],
)
def test_empty_message_is_rejected(
    messaging_setup,
    body,
):
    listing_id = messaging_setup["create"]()

    result = listings.send_message(
        3,
        listing_id,
        body,
    )

    assert result["ok"] is False
    assert result["error"] == "body required"
    assert messaging_setup["message_count"]() == 0


def test_deactivated_listing_cannot_receive_messages(
    messaging_setup,
):
    listing_id = messaging_setup["create"](
        status="active"
    )

    transition = listings.transition(
        2,
        listing_id,
        "deactivate",
    )

    assert transition["ok"] is True
    assert transition["listing"]["status"] == "inactive"

    result = listings.send_message(
        3,
        listing_id,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == "listing not available"
    assert messaging_setup["message_count"]() == 0


def test_force_deactivated_listing_cannot_receive_messages(
    messaging_setup,
):
    listing_id = messaging_setup["create"](
        status="active"
    )

    transition = listings.transition(
        1,
        listing_id,
        "force_deactivate",
    )

    assert transition["ok"] is True
    assert transition["listing"]["status"] == "inactive"
    assert transition["listing"]["admin_hold"] is True

    result = listings.send_message(
        3,
        listing_id,
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == "listing not available"
    assert messaging_setup["message_count"]() == 0


def test_api_rejects_message_to_unavailable_listing(
    messaging_setup,
):
    listing_id = messaging_setup["create"](
        status="pending"
    )

    body = MessageBody(
        listing_id=listing_id,
        body="Hello",
    )

    with pytest.raises(HTTPException) as exc:
        message_route(
            body=body,
            x_user_id="3",
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "listing not available"
    assert messaging_setup["message_count"]() == 0


def test_api_accepts_message_to_active_listing(
    messaging_setup,
):
    listing_id = messaging_setup["create"](
        status="active"
    )

    body = MessageBody(
        listing_id=listing_id,
        body="Is this available?",
    )

    result = message_route(
        body=body,
        x_user_id="3",
    )

    assert result["ok"] is True
    assert result["message_id"] is not None
    assert messaging_setup["message_count"]() == 1
