
import pytest

from sqlmodel import select

from app.models.listing import Listing
from app.models.message import Message
from app.services import listings
from app.services.student_eligibility import (
    is_eligible_student,
    student_access_error,
)


@pytest.fixture
def eligibility_setup(test_session, monkeypatch):
    users = {
        1: {
            "id": 1,
            "role": "student",
            "student_id": "202012345",
            "provisional": 0,
        },
        2: {
            "id": 2,
            "role": "student",
            "student_id": None,
            "provisional": 1,
        },
        3: {
            "id": 3,
            "role": "student",
            "student_id": None,
            "provisional": 0,
        },
        4: {
            "id": 4,
            "role": "student",
            "student_id": "   ",
            "provisional": 0,
        },
        5: {
            "id": 5,
            "role": "landlord",
            "student_id": "202012345",
            "provisional": 1,
        },
        6: {
            "id": 6,
            "role": "admin",
            "student_id": None,
            "provisional": 0,
        },
    }

    monkeypatch.setattr(
        listings,
        "get_user",
        lambda user_id: users.get(user_id),
    )

    monkeypatch.setattr(
        listings,
        "engine",
        test_session.bind,
    )

    active = Listing(
        landlord_id=5,
        title="Available Accommodation",
        area="st_augustine",
        price=2500,
        amenities="wifi,parking",
        contact_phone="555-1234",
        contact_email="landlord@example.com",
        created_at="2026-11-23T10:00:00+00:00",
        status="active",
    )

    pending = Listing(
        landlord_id=5,
        title="Pending Accommodation",
        area="mount_hope",
        price=3000,
        amenities="wifi",
        contact_phone="555-5678",
        contact_email="landlord@example.com",
        created_at="2026-11-23T11:00:00+00:00",
        status="pending",
    )

    test_session.add_all([active, pending])
    test_session.commit()
    test_session.refresh(active)
    test_session.refresh(pending)

    return {
        "users": users,
        "session": test_session,
        "active_id": active.id,
        "pending_id": pending.id,
    }


@pytest.mark.parametrize(
    "user,expected",
    [
        (
            {
                "role": "student",
                "student_id": "202012345",
                "provisional": 0,
            },
            True,
        ),
        (
            {
                "role": "student",
                "student_id": None,
                "provisional": 1,
            },
            True,
        ),
        (
            {
                "role": "student",
                "student_id": None,
                "provisional": 0,
            },
            False,
        ),
        (
            {
                "role": "student",
                "student_id": "  ",
                "provisional": 0,
            },
            False,
        ),
        (
            {
                "role": "landlord",
                "student_id": "202012345",
                "provisional": 1,
            },
            False,
        ),
        (None, False),
    ],
)
def test_eligibility_rule(user, expected):
    assert is_eligible_student(user) is expected


@pytest.mark.parametrize("student_id", [1, 2])
def test_eligible_students_can_browse(
    eligibility_setup, student_id
):
    result = listings.browse_for_students(student_id)

    assert result["ok"] is True
    assert len(result["listings"]) == 1
    assert (
        result["listings"][0]["id"]
        == eligibility_setup["active_id"]
    )


@pytest.mark.parametrize(
    "student_id,expected_error",
    [
        (3, "student eligibility required"),
        (4, "student eligibility required"),
        (5, "students only"),
        (6, "students only"),
        (999, "students only"),
    ],
)
def test_ineligible_users_cannot_browse(
    eligibility_setup, student_id, expected_error
):
    result = listings.browse_for_students(student_id)

    assert result["ok"] is False
    assert result["error"] == expected_error
    assert "listings" not in result


@pytest.mark.parametrize("student_id", [1, 2])
def test_eligible_students_can_send_message(
    eligibility_setup, student_id
):
    result = listings.send_message(
        student_id,
        eligibility_setup["active_id"],
        "Is this accommodation available?",
    )

    assert result["ok"] is True
    assert result["message_id"] is not None


@pytest.mark.parametrize(
    "student_id,expected_error",
    [
        (3, "student eligibility required"),
        (4, "student eligibility required"),
        (5, "students only"),
        (6, "students only"),
        (999, "students only"),
    ],
)
def test_ineligible_users_cannot_send_message(
    eligibility_setup, student_id, expected_error
):
    result = listings.send_message(
        student_id,
        eligibility_setup["active_id"],
        "Hello",
    )

    assert result["ok"] is False
    assert result["error"] == expected_error

    messages = eligibility_setup["session"].exec(
        select(Message)
    ).all()

    assert messages == []


def test_pending_listings_remain_hidden(eligibility_setup):
    result = listings.browse_for_students(1)

    visible_ids = {
        item["id"]
        for item in result["listings"]
    }

    assert eligibility_setup["active_id"] in visible_ids
    assert eligibility_setup["pending_id"] not in visible_ids
