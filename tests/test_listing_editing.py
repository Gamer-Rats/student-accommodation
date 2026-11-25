
"""Task #31: Ownership-protected listing editing tests."""

import pytest

from app.models.listing import Listing
from app.services import listings


@pytest.fixture
def editing_setup(test_session, monkeypatch):
    users = {
        1: {"id": 1, "role": "landlord"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "student"},
        4: {"id": 4, "role": "admin"},
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

    def make_listing(owner=1, status="pending"):
        row = Listing(
            landlord_id=owner,
            title="Original listing",
            area="st_augustine",
            price=2000,
            amenities="wifi",
            contact_phone="5551234",
            contact_email="owner@example.com",
            created_at="2026-11-24T10:00:00+00:00",
            status=status,
        )

        test_session.add(row)
        test_session.commit()
        test_session.refresh(row)

        return row.id

    def get_listing(listing_id):
        test_session.expire_all()
        return test_session.get(Listing, listing_id)

    return make_listing, get_listing


def test_owner_can_edit_pending_listing(editing_setup):
    make, get = editing_setup
    listing_id = make()

    result = listings.update_listing(
        1,
        listing_id,
        title="Updated apartment",
        area="mount_hope",
        price=2500,
        amenities="wifi, parking",
        contact_phone="5559876",
        contact_email="new@example.com",
    )

    assert result["ok"] is True

    row = get(listing_id)

    assert row.title == "Updated apartment"
    assert row.area == "mount_hope"
    assert row.price == 2500
    assert row.amenities == "wifi, parking"
    assert row.contact_email == "new@example.com"
    assert row.status == "pending"
    assert row.landlord_id == 1


def test_rejected_listing_stays_rejected(editing_setup):
    make, get = editing_setup

    listing_id = make(status="rejected")

    result = listings.update_listing(
        1,
        listing_id,
        title="Corrected listing",
    )

    assert result["ok"] is True
    assert get(listing_id).title == "Corrected listing"
    assert get(listing_id).status == "rejected"


def test_other_landlord_cannot_edit(editing_setup):
    make, get = editing_setup

    listing_id = make(owner=2)

    result = listings.update_listing(
        1,
        listing_id,
        price=999,
    )

    assert result["ok"] is False
    assert get(listing_id).price == 2000


@pytest.mark.parametrize("actor_id", [3, 4, 999])
def test_non_landlord_cannot_edit(editing_setup, actor_id):
    make, get = editing_setup

    listing_id = make()

    result = listings.update_listing(
        actor_id,
        listing_id,
        title="Unauthorized edit",
    )

    assert result["ok"] is False
    assert get(listing_id).title == "Original listing"


@pytest.mark.parametrize(
    "status",
    ["provisional", "approved", "active", "inactive"],
)
def test_reviewed_listings_cannot_be_edited(
    editing_setup,
    status,
):
    make, get = editing_setup

    listing_id = make(status=status)

    result = listings.update_listing(
        1,
        listing_id,
        title="Unreviewed edit",
    )

    assert result["ok"] is False
    assert get(listing_id).title == "Original listing"
    assert get(listing_id).status == status


@pytest.mark.parametrize(
    "changes",
    [
        {"area": "port_of_spain"},
        {"price": 0},
        {"price": -100},
        {"price": "2000"},
        {"title": " "},
        {"contact_email": "not-email"},
        {"title": "Valid change", "price": -9},
    ],
)
def test_invalid_updates_do_not_change_database(
    editing_setup,
    changes,
):
    make, get = editing_setup

    listing_id = make()

    result = listings.update_listing(
        1,
        listing_id,
        **changes,
    )

    assert result["ok"] is False

    row = get(listing_id)

    assert row.title == "Original listing"
    assert row.price == 2000
    assert row.area == "st_augustine"


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "active"),
        ("landlord_id", 2),
        ("admin_hold", False),
        ("review_feedback", ""),
        ("created_at", "tomorrow"),
    ],
)
def test_protected_fields_cannot_be_edited(
    editing_setup,
    field,
    value,
):
    make, get = editing_setup

    listing_id = make()

    result = listings.update_listing(
        1,
        listing_id,
        **{field: value},
    )

    assert result["ok"] is False
    assert get(listing_id).status == "pending"
    assert get(listing_id).landlord_id == 1


def test_unknown_listing_cannot_be_edited(editing_setup):
    result = listings.update_listing(
        1,
        99999,
        title="Does not exist",
    )

    assert result == {
        "ok": False,
        "error": "listing not found",
    }


def test_no_changes_rejected(editing_setup):
    make, get = editing_setup

    listing_id = make()

    result = listings.update_listing(1, listing_id)

    assert result["ok"] is False
    assert get(listing_id).title == "Original listing"
