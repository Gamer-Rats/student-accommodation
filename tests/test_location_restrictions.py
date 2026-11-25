
"""Tests for accommodation location restrictions."""

import pytest

from fastapi import HTTPException
from sqlmodel import select

from app.models.listing import Listing
from app.routers.accommodation import browse as browse_route
from app.services import listings
from app.services.location_rules import (
    LOCATION_ERROR,
    normalize_area,
)


@pytest.fixture
def location_setup(test_session, monkeypatch):
    """Use an isolated database and mocked users."""

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
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

    def create(status="active", area="st_augustine"):
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
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    return {
        "create": create,
        "session": test_session,
    }


def submit_area(area):
    return listings.submit_listing(
        2,
        title="New Accommodation",
        area=area,
        price=2500,
        amenities="wifi",
        contact_phone="555-1234",
        contact_email="landlord@example.com",
    )


@pytest.mark.parametrize(
    "area,expected",
    [
        ("st_augustine", "st_augustine"),
        ("St Augustine", "st_augustine"),
        ("St. Augustine", "st_augustine"),
        ("Saint Augustine", "st_augustine"),
        ("Mount Hope", "mount_hope"),
        ("mount_hope", "mount_hope"),
    ],
)
def test_normalize_valid_areas(area, expected):
    assert normalize_area(area) == expected


@pytest.mark.parametrize(
    "area",
    [
        "",
        "Arima",
        "Curepe",
        "St. Augustine East",
        "Mount Hope North",
        None,
    ],
)
def test_normalize_rejects_invalid_areas(area):
    assert normalize_area(area) is None


@pytest.mark.parametrize(
    "area,expected",
    [
        ("st_augustine", "st_augustine"),
        ("St. Augustine", "st_augustine"),
        ("mount_hope", "mount_hope"),
        ("Mount Hope", "mount_hope"),
    ],
)
def test_submit_accepts_valid_areas(
    location_setup, area, expected
):
    result = submit_area(area)

    assert result["ok"] is True
    assert result["listing"]["area"] == expected
    assert result["listing"]["status"] == "pending"


@pytest.mark.parametrize(
    "area",
    [
        "",
        "Arima",
        "Curepe",
        "St. Augustine East",
    ],
)
def test_submit_rejects_invalid_areas(
    location_setup, area
):
    session = location_setup["session"]

    before = len(session.exec(select(Listing)).all())

    result = submit_area(area)

    after = len(session.exec(select(Listing)).all())

    assert result["ok"] is False
    assert result["error"] == LOCATION_ERROR
    assert after == before


def test_non_landlord_cannot_submit(location_setup):
    result = listings.submit_listing(
        3,
        title="Not Allowed",
        area="st_augustine",
        price=2500,
        amenities="wifi",
        contact_phone="555-1234",
        contact_email="test@example.com",
    )

    assert result["ok"] is False
    assert result["error"] == "landlords only"


def test_browse_hides_out_of_area_listings(location_setup):
    create = location_setup["create"]

    st_id = create(area="st_augustine")
    mount_id = create(area="mount_hope")

    create(area="Arima")
    create(area="Curepe")
    create(status="pending", area="st_augustine")

    result = listings.browse_for_students(3)

    assert result["ok"] is True

    ids = {
        item["id"]
        for item in result["listings"]
    }

    assert ids == {st_id, mount_id}


@pytest.mark.parametrize(
    "area,expected",
    [
        ("St. Augustine", "st_augustine"),
        ("st_augustine", "st_augustine"),
        ("Mount Hope", "mount_hope"),
        ("mount_hope", "mount_hope"),
    ],
)
def test_area_filter_accepts_valid_variants(
    location_setup, area, expected
):
    create = location_setup["create"]

    st_id = create(area="st_augustine")
    mount_id = create(area="mount_hope")

    result = listings.browse_for_students(
        3, area=area
    )

    assert result["ok"] is True

    expected_id = (
        st_id if expected == "st_augustine"
        else mount_id
    )

    assert [
        item["id"] for item in result["listings"]
    ] == [expected_id]


@pytest.mark.parametrize(
    "area",
    ["Arima", ""],
)
def test_invalid_browse_filter_is_rejected(
    location_setup, area
):
    result = listings.browse_for_students(
        3, area=area
    )

    assert result["ok"] is False
    assert result["error"] == LOCATION_ERROR


def test_invalid_area_returns_http_400(location_setup):
    with pytest.raises(HTTPException) as exc:
        browse_route(
            area="Arima",
            max_price=None,
            amenity=None,
            actor={"id": 3, "role": "student"},
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == LOCATION_ERROR


@pytest.mark.parametrize(
    "status,action,actor_id",
    [
        ("pending", "verify", 1),
        ("pending", "provisionally_accept", 1),
        ("approved", "activate", 2),
    ],
)
def test_invalid_legacy_location_cannot_progress(
    location_setup, status, action, actor_id
):
    listing_id = location_setup["create"](
        status=status,
        area="Arima",
    )

    result = listings.transition(
        actor_id, listing_id, action
    )

    assert result["ok"] is False
    assert result["error"] == LOCATION_ERROR

    saved = location_setup["session"].get(
        Listing, listing_id
    )

    assert saved.status == status


def test_ineligible_student_cannot_browse(
    location_setup,
):
    result = listings.browse_for_students(
        4, area="Arima"
    )

    assert result["ok"] is False
    assert result["error"] == "student eligibility required"
