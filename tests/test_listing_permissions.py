
import pytest

from sqlmodel import Session

from app.models.listing import Listing
from app.services import listings


@pytest.fixture
def setup_permissions(test_session, monkeypatch):
    """Create listings in an isolated test database."""

    monkeypatch.setattr(
        listings,
        "engine",
        test_session.bind,
    )

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {"id": 4, "role": "student"},
    }

    monkeypatch.setattr(
        listings,
        "get_user",
        lambda user_id: users.get(user_id),
    )

    def create(status="pending", landlord_id=2):
        listing = Listing(
            landlord_id=landlord_id,
            title="Test Accommodation",
            area="st_augustine",
            price=2500,
            amenities="wifi,parking",
            contact_phone="555-1234",
            contact_email="landlord@example.com",
            created_at="2026-11-23T10:00:00+00:00",
            status=status,
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def get_saved(listing_id):
        with Session(test_session.bind) as session:
            return session.get(
                Listing, listing_id
            ).model_dump()

    return create, get_saved


@pytest.mark.parametrize(
    "status,action,expected",
    [
        ("approved", "activate", "active"),
        ("active", "deactivate", "inactive"),
        ("rejected", "resubmit", "pending"),
        ("inactive", "activate", "active"),
    ],
)
def test_owner_can_manage_own_listing(
    setup_permissions,
    status,
    action,
    expected,
):
    create, get_saved = setup_permissions
    listing_id = create(status)

    result = listings.transition(
        2, listing_id, action
    )

    assert result["ok"] is True
    assert result["listing"]["status"] == expected
    assert get_saved(listing_id)["status"] == expected


@pytest.mark.parametrize(
    "status,action",
    [
        ("approved", "activate"),
        ("active", "deactivate"),
        ("rejected", "resubmit"),
    ],
)
def test_other_landlord_cannot_manage_listing(
    setup_permissions,
    status,
    action,
):
    create, get_saved = setup_permissions
    listing_id = create(status)

    result = listings.transition(
        3, listing_id, action
    )

    assert result["ok"] is False
    assert result["error"] == "not listing owner"
    assert get_saved(listing_id)["status"] == status


@pytest.mark.parametrize(
    "status,action",
    [
        ("approved", "activate"),
        ("active", "deactivate"),
        ("rejected", "resubmit"),
    ],
)
def test_student_cannot_manage_listing(
    setup_permissions,
    status,
    action,
):
    create, get_saved = setup_permissions
    listing_id = create(status)

    result = listings.transition(
        4, listing_id, action
    )

    assert result["ok"] is False
    assert result["error"] == "landlord only"
    assert get_saved(listing_id)["status"] == status


@pytest.mark.parametrize(
    "status,action",
    [
        ("approved", "activate"),
        ("active", "deactivate"),
        ("rejected", "resubmit"),
    ],
)
def test_admin_cannot_use_landlord_actions(
    setup_permissions,
    status,
    action,
):
    create, get_saved = setup_permissions
    listing_id = create(status)

    result = listings.transition(
        1, listing_id, action
    )

    assert result["ok"] is False
    assert result["error"] == "landlord only"
    assert get_saved(listing_id)["status"] == status


@pytest.mark.parametrize(
    "status,action,expected",
    [
        ("pending", "verify", "approved"),
        ("pending", "reject", "rejected"),
        (
            "pending",
            "provisionally_accept",
            "provisional",
        ),
        (
            "active",
            "force_deactivate",
            "inactive",
        ),
    ],
)
def test_admin_can_perform_admin_actions(
    setup_permissions,
    status,
    action,
    expected,
):
    create, get_saved = setup_permissions
    listing_id = create(status)

    result = listings.transition(
        1, listing_id, action
    )

    assert result["ok"] is True
    assert get_saved(listing_id)["status"] == expected

    if action == "force_deactivate":
        assert get_saved(listing_id)["admin_hold"] is True


@pytest.mark.parametrize(
    "status,action,actor_id",
    [
        ("pending", "verify", 2),
        ("pending", "reject", 3),
        ("pending", "provisionally_accept", 4),
        ("active", "force_deactivate", 2),
    ],
)
def test_non_admin_cannot_perform_admin_actions(
    setup_permissions,
    status,
    action,
    actor_id,
):
    create, get_saved = setup_permissions
    listing_id = create(status)

    result = listings.transition(
        actor_id, listing_id, action
    )

    assert result["ok"] is False
    assert result["error"] == "admin only"
    assert get_saved(listing_id)["status"] == status


def test_unknown_user_cannot_transition(
    setup_permissions,
):
    create, get_saved = setup_permissions
    listing_id = create("approved")

    result = listings.transition(
        999, listing_id, "activate"
    )

    assert result["ok"] is False
    assert result["error"] == "unknown user"
    assert get_saved(listing_id)["status"] == "approved"


def test_owner_cannot_make_invalid_state_transition(
    setup_permissions,
):
    create, get_saved = setup_permissions
    listing_id = create("pending")

    result = listings.transition(
        2, listing_id, "activate"
    )

    assert result["ok"] is False
    assert get_saved(listing_id)["status"] == "pending"


def test_missing_listing_is_rejected(
    setup_permissions,
):
    result = listings.transition(
        2, 99999, "activate"
    )

    assert result["ok"] is False
    assert result["error"] == "listing not found"


def test_unknown_action_is_rejected(
    setup_permissions,
):
    create, get_saved = setup_permissions
    listing_id = create("active")

    result = listings.transition(
        2, listing_id, "unknown_action"
    )

    assert result["ok"] is False
    assert get_saved(listing_id)["status"] == "active"
