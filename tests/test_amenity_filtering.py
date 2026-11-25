import pytest

from app.models.listing import Listing
from app.routers.accommodation import browse as browse_route
from app.services import listings


@pytest.fixture
def amenity_setup(test_session, monkeypatch):
    users = {
        100: {
            "id": 100,
            "role": "student",
            "student_id": "202012345",
            "provisional": 0,
        },
        101: {
            "id": 101,
            "role": "student",
            "student_id": None,
            "provisional": 1,
        },
        102: {
            "id": 102,
            "role": "student",
            "student_id": None,
            "provisional": 0,
        },
        200: {
            "id": 200,
            "role": "landlord",
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
        title,
        amenities,
        *,
        area="st_augustine",
        price=2500,
        status="active",
        admin_hold=False,
    ):
        listing = Listing(
            landlord_id=200,
            title=title,
            area=area,
            price=price,
            amenities=amenities,
            contact_phone="555-1234",
            contact_email="landlord@example.com",
            created_at="2026-11-23T10:00:00+00:00",
            status=status,
            admin_hold=admin_hold,
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    ids = {
        "wifi_only": create(
            "WiFi Only", "WiFi"
        ),
        "wifi_parking": create(
            "WiFi Parking", "wifi, PARKING"
        ),
        "pool_parking": create(
            "Pool Parking", "Pool, Parking"
        ),
        "air_wifi": create(
            "Air Conditioning WiFi",
            "Air Conditioning, WiFi",
        ),
        "partial_only": create(
            "Different Amenities",
            "wifi_extender,parking_lot",
        ),
        "no_amenities": create(
            "No Amenities", ""
        ),
    }

    return {
        "create": create,
        "ids": ids,
    }


def browse_ids(student_id=100, **filters):
    result = listings.browse_for_students(
        student_id, **filters
    )

    assert result["ok"] is True

    return {
        item["id"]
        for item in result["listings"]
    }


@pytest.mark.parametrize(
    "query,expected_keys",
    [
        (
            "wifi",
            {
                "wifi_only",
                "wifi_parking",
                "air_wifi",
            },
        ),
        (
            "  WIFI  ",
            {
                "wifi_only",
                "wifi_parking",
                "air_wifi",
            },
        ),
        (
            "parking",
            {
                "wifi_parking",
                "pool_parking",
            },
        ),
        (
            "POOL",
            {"pool_parking"},
        ),
        (
            "air conditioning",
            {"air_wifi"},
        ),
        (
            "parking_lot",
            {"partial_only"},
        ),
    ],
)
def test_exact_case_insensitive_filter(
    amenity_setup,
    query,
    expected_keys,
):
    ids = amenity_setup["ids"]

    expected = {
        ids[key]
        for key in expected_keys
    }

    assert browse_ids(amenity=query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "fi",
        "park",
        "air",
        "parking l",
        "wifi_",
    ],
)
def test_partial_names_do_not_match(
    amenity_setup,
    query,
):
    assert browse_ids(amenity=query) == set()


def test_nonexistent_amenity_returns_no_listings(
    amenity_setup,
):
    assert browse_ids(amenity="jacuzzi") == set()


@pytest.mark.parametrize(
    "filter_value",
    [None, "", "   "],
)
def test_empty_filter_returns_all_active_listings(
    amenity_setup,
    filter_value,
):
    ids = amenity_setup["ids"]

    assert browse_ids(
        amenity=filter_value
    ) == set(ids.values())


def test_empty_comma_entries_are_ignored(
    amenity_setup,
):
    create = amenity_setup["create"]

    new_id = create(
        "Extra Spaces",
        " , WiFi, , ",
    )

    assert new_id in browse_ids(amenity="wifi")
    assert new_id not in browse_ids(
        amenity="parking"
    )


def test_filter_works_with_location_price_and_status(
    amenity_setup,
):
    create = amenity_setup["create"]
    ids = amenity_setup["ids"]

    create(
        "Other Area",
        "wifi",
        area="mount_hope",
    )

    create(
        "Too Expensive",
        "wifi",
        price=4000,
    )

    create(
        "Pending Unit",
        "wifi",
        status="pending",
    )

    create(
        "Held Unit",
        "wifi",
        admin_hold=True,
    )

    expected = {
        ids["wifi_only"],
        ids["wifi_parking"],
        ids["air_wifi"],
    }

    assert browse_ids(
        area="St. Augustine",
        max_price=2500,
        amenity="WiFi",
    ) == expected


def test_provisional_student_can_filter(
    amenity_setup,
):
    ids = amenity_setup["ids"]

    assert browse_ids(
        101, amenity="pool"
    ) == {ids["pool_parking"]}


def test_ineligible_student_cannot_filter(
    amenity_setup,
):
    result = listings.browse_for_students(
        102, amenity="wifi"
    )

    assert result["ok"] is False
    assert result["error"] == (
        "student eligibility required"
    )


def test_submission_still_preserves_amenities(
    amenity_setup,
):
    result = listings.submit_listing(
        200,
        title="New Accommodation",
        area="Mount Hope",
        price=2500,
        amenities="WiFi, PARKING",
        contact_phone="555-1234",
        contact_email="landlord@example.com",
    )

    assert result["ok"] is True
    assert result["listing"]["status"] == "pending"
    assert result["listing"]["area"] == "mount_hope"
    assert result["listing"]["amenities"] == (
        "WiFi, PARKING"
    )


def test_api_uses_correct_amenity_filter(
    amenity_setup,
):
    ids = amenity_setup["ids"]

    result = browse_route(
        area=None,
        max_price=None,
        amenity="PARKING",
        actor={"id": 100, "role": "student"},
    )

    assert result["ok"] is True

    returned_ids = {
        item["id"]
        for item in result["listings"]
    }

    assert returned_ids == {
        ids["wifi_parking"],
        ids["pool_parking"],
    }
