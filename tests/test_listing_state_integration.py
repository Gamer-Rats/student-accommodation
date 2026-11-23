import pytest

from app.models.listing import Listing
from app.services import listings
from app.services.lifecycle import (
    apply_action,
    visible_to_students,
)


@pytest.fixture
def setup_listings(test_session, monkeypatch):
    """Use the existing isolated test database."""

    monkeypatch.setattr(
        listings,
        "engine",
        test_session.bind,
    )

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {"id": 4, "role": "student", "student_id": "202012345", "provisional": 0},
    }

    monkeypatch.setattr(
        listings,
        "get_user",
        lambda user_id: users.get(user_id),
    )

    def create(status="pending", **changes):
        data = {
            "landlord_id": 2,
            "title": "Test Accommodation",
            "area": "st_augustine",
            "price": 2500,
            "amenities": "wifi,parking",
            "contact_phone": "555-1234",
            "contact_email": "landlord@example.com",
            "created_at": "2026-11-23T10:00:00+00:00",
            "status": status,
        }

        data.update(changes)

        listing = Listing(**data)

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    return create


@pytest.mark.parametrize(
    "initial,action,actor_id,expected",
    [
        ("pending", "verify", 1, "approved"),
        ("pending", "provisionally_accept", 1, "provisional"),
        ("pending", "reject", 1, "rejected"),
        ("provisional", "verify", 1, "approved"),
        ("approved", "activate", 2, "active"),
        ("active", "deactivate", 2, "inactive"),
        ("active", "force_deactivate", 1, "inactive"),
        ("inactive", "activate", 2, "active"),
        ("rejected", "resubmit", 2, "pending"),
    ],
)
def test_valid_state_transitions(
    setup_listings,
    initial,
    action,
    actor_id,
    expected,
):
    listing_id = setup_listings(initial)

    result = listings.transition(
        actor_id,
        listing_id,
        action,
    )

    assert result["ok"] is True
    assert result["listing"]["status"] == expected


@pytest.mark.parametrize(
    "initial,action,actor_id",
    [
        ("pending", "activate", 2),
        ("rejected", "verify", 1),
        ("approved", "reject", 1),
        ("provisional", "activate", 2),
    ],
)
def test_invalid_transitions_are_rejected(
    setup_listings,
    initial,
    action,
    actor_id,
):
    listing_id = setup_listings(initial)

    result = listings.transition(
        actor_id,
        listing_id,
        action,
    )

    assert result["ok"] is False


def test_force_deactivation_adds_admin_hold(
    setup_listings,
):
    listing_id = setup_listings("active")

    result = listings.transition(
        1,
        listing_id,
        "force_deactivate",
    )

    assert result["ok"] is True
    assert result["listing"]["status"] == "inactive"
    assert result["listing"]["admin_hold"] is True

    reactivate = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert reactivate["ok"] is False


def test_reverification_blocks_reactivation(
    setup_listings,
):
    listing_id = setup_listings(
        "inactive",
        requires_reverification=True,
    )

    result = listings.transition(
        2,
        listing_id,
        "activate",
    )

    assert result["ok"] is False


def test_visibility_uses_state_pattern():
    assert visible_to_students(
        {"status": "active"}
    ) is True

    for status in (
        "pending",
        "provisional",
        "approved",
        "inactive",
        "rejected",
    ):
        assert visible_to_students(
            {"status": status}
        ) is False

    assert visible_to_students(
        {
            "status": "active",
            "admin_hold": True,
        }
    ) is False

    assert visible_to_students(
        {
            "status": "active",
            "requires_reverification": True,
        }
    ) is False


def test_submit_listing_uses_single_status(
    setup_listings,
):
    result = listings.submit_listing(
        2,
        title="New Listing",
        area="st_augustine",
        price=2500,
        amenities="wifi",
        contact_phone="555-1234",
        contact_email="landlord@example.com",
    )

    assert result["ok"] is True

    saved = result["listing"]

    assert saved["status"] == "pending"

    for flag in (
        "flag_pending",
        "flag_verified",
        "flag_active",
        "flag_rejected",
    ):
        assert flag not in saved


def test_student_browse_shows_only_visible_listings(
    setup_listings,
):
    active_id = setup_listings("active")

    setup_listings("pending")
    setup_listings("rejected")
    setup_listings("active", admin_hold=True)
    setup_listings(
        "active",
        requires_reverification=True,
    )

    result = listings.browse_for_students(4)

    assert result["ok"] is True
    assert [
        item["id"]
        for item in result["listings"]
    ] == [active_id]


def test_only_admin_can_verify(setup_listings):
    listing_id = setup_listings("pending")

    result = listings.transition(
        2,
        listing_id,
        "verify",
    )

    assert result["ok"] is False
    assert result["error"] == "admin only"


def test_unknown_action_is_rejected():
    result = apply_action(
        {"id": 1, "status": "pending"},
        "invalid_action",
    )

    assert result["ok"] is False
