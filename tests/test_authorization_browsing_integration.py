"""API integration tests for permissions, browsing, and messaging.

Tests use the real accommodation API router and an isolated in-memory database.
The starter project's X-User-Id header is mocked as the user lookup mechanism;
these tests do not establish that the header is secure authentication.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models.listing import Listing
from app.models.message import Message
from app.routers import accommodation
from app.services import listings


@pytest.fixture
def api_setup(test_session, monkeypatch):
    """Connect real HTTP routes to a disposable test database."""
    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
        4: {
            "id": 4, "role": "student",
            "student_id": "202012345", "provisional": 0,
        },
        5: {
            "id": 5, "role": "student",
            "student_id": None, "provisional": 1,
        },
        6: {
            "id": 6, "role": "student",
            "student_id": None, "provisional": 0,
        },
    }

    lookup_user = lambda user_id: users.get(user_id)
    monkeypatch.setattr(listings, "engine", test_session.bind)
    monkeypatch.setattr(listings, "get_user", lookup_user)
    monkeypatch.setattr(accommodation.auth, "get_user", lookup_user)

    # This uses the actual API router, but avoids starting the real app's
    # database-seeding lifespan handler against a developer database.
    test_app = FastAPI()
    test_app.include_router(accommodation.router, prefix="/api")
    client = TestClient(test_app)

    def headers(user_id):
        return {"X-User-Id": str(user_id)}

    def create_listing(**changes):
        data = {
            "landlord_id": 2,
            "title": "Test Accommodation",
            "area": "st_augustine",
            "price": 2500,
            "amenities": "wifi,parking",
            "contact_phone": "555-1234",
            "contact_email": "landlord@example.com",
            "created_at": "2026-11-23T10:00:00+00:00",
            "status": "active",
        }
        data.update(changes)
        listing = Listing(**data)
        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)
        return listing.id

    def stored_listing(listing_id):
        with Session(test_session.bind) as session:
            listing = session.get(Listing, listing_id)
            return listing.model_dump() if listing else None

    def message_count():
        with Session(test_session.bind) as session:
            return len(session.exec(select(Message)).all())

    return {
        "client": client,
        "headers": headers,
        "create": create_listing,
        "stored": stored_listing,
        "message_count": message_count,
    }


def listing_payload(**changes):
    data = {
        "title": "Student Flat",
        "area": "St. Augustine",
        "price": 2800,
        "amenities": "WiFi, Parking",
        "contact_phone": "555-0100",
        "contact_email": "landlord@example.com",
        "photos": "",
    }
    data.update(changes)
    return data


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", "/api/student/listings", None),
        ("get", "/api/admin/listings", None),
        ("post", "/api/landlord/listings", listing_payload()),
        ("post", "/api/listings/1/transition", {"action": "verify"}),
        ("post", "/api/student/messages", {"listing_id": 1, "body": "Hi"}),
    ],
)
def test_missing_user_header_is_rejected(api_setup, method, path, body):
    client = api_setup["client"]
    response = getattr(client, method)(path, **({"json": body} if body else {}))
    assert response.status_code == 401


def test_invalid_user_header_is_rejected(api_setup):
    response = api_setup["client"].get(
        "/api/student/listings", headers={"X-User-Id": "not-a-number"}
    )
    assert response.status_code == 400


@pytest.mark.parametrize("user_id", [1, 4, 5, 999])
def test_only_landlords_can_submit(api_setup, user_id):
    response = api_setup["client"].post(
        "/api/landlord/listings",
        headers=api_setup["headers"](user_id),
        json=listing_payload(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "landlords only"


@pytest.mark.parametrize(
    "area,canonical",
    [("St. Augustine", "st_augustine"), ("Mount Hope", "mount_hope")],
)
def test_landlord_submission_is_saved(api_setup, area, canonical):
    response = api_setup["client"].post(
        "/api/landlord/listings",
        headers=api_setup["headers"](2),
        json=listing_payload(area=area),
    )
    assert response.status_code == 200
    saved = response.json()["listing"]
    assert saved["status"] == "pending"
    assert saved["area"] == canonical
    assert saved["landlord_id"] == 2
    assert api_setup["stored"](saved["id"])["status"] == "pending"


@pytest.mark.parametrize(
    "changes",
    [{"area": "Arima"}, {"area": ""}, {"price": 0}, {"price": -1}],
)
def test_invalid_submission_is_rejected(api_setup, changes):
    response = api_setup["client"].post(
        "/api/landlord/listings",
        headers=api_setup["headers"](2),
        json=listing_payload(**changes),
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "user_id,status",
    [(1, 200), (2, 403), (4, 403), (999, 403)],
)
def test_admin_listing_endpoint_requires_admin(api_setup, user_id, status):
    api_setup["create"]()
    response = api_setup["client"].get(
        "/api/admin/listings", headers=api_setup["headers"](user_id)
    )
    assert response.status_code == status


def test_admin_can_filter_listings_by_status(api_setup):
    approved = api_setup["create"](status="approved")
    api_setup["create"](status="pending")
    response = api_setup["client"].get(
        "/api/admin/listings",
        params={"status": "approved"},
        headers=api_setup["headers"](1),
    )
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["listings"]] == [approved]


@pytest.mark.parametrize("student_id", [4, 5])
def test_registered_and_provisional_students_can_browse(api_setup, student_id):
    visible = api_setup["create"]()
    api_setup["create"](status="pending")
    response = api_setup["client"].get(
        "/api/student/listings", headers=api_setup["headers"](student_id)
    )
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["listings"]] == [visible]


@pytest.mark.parametrize("user_id", [1, 2, 6, 999])
def test_ineligible_users_cannot_browse(api_setup, user_id):
    api_setup["create"]()
    response = api_setup["client"].get(
        "/api/student/listings", headers=api_setup["headers"](user_id)
    )
    assert response.status_code == 403
    assert "listings" not in response.json()


def test_browse_hides_unavailable_and_out_of_area_listings(api_setup):
    visible = api_setup["create"]()
    for status in ("pending", "provisional", "approved", "inactive", "rejected"):
        api_setup["create"](status=status)
    api_setup["create"](admin_hold=True)
    api_setup["create"](requires_reverification=True)
    api_setup["create"](area="Arima")
    response = api_setup["client"].get(
        "/api/student/listings", headers=api_setup["headers"](4)
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["listings"]} == {visible}


@pytest.mark.parametrize(
    "filter_area,actual_area",
    [("St. Augustine", "st_augustine"), ("Mount Hope", "mount_hope")],
)
def test_location_filter_supports_display_names(api_setup, filter_area, actual_area):
    matching = api_setup["create"](area=actual_area)
    other = "mount_hope" if actual_area == "st_augustine" else "st_augustine"
    api_setup["create"](area=other)
    response = api_setup["client"].get(
        "/api/student/listings",
        params={"area": filter_area},
        headers=api_setup["headers"](4),
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["listings"]} == {matching}


def test_invalid_location_filter_returns_http_400(api_setup):
    response = api_setup["client"].get(
        "/api/student/listings",
        params={"area": "Arima"},
        headers=api_setup["headers"](4),
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "query,expected_count",
    [("WIFI", 1), ("parking", 1), ("park", 0)],
)
def test_amenity_filter_is_exact_and_case_insensitive(api_setup, query, expected_count):
    api_setup["create"](amenities="WiFi, Parking")
    response = api_setup["client"].get(
        "/api/student/listings",
        params={"amenity": query},
        headers=api_setup["headers"](4),
    )
    assert response.status_code == 200
    assert len(response.json()["listings"]) == expected_count


def test_combined_browse_filters(api_setup):
    wanted = api_setup["create"](area="mount_hope", price=2400, amenities="wifi,parking")
    api_setup["create"](area="mount_hope", price=4000, amenities="wifi")
    api_setup["create"](area="st_augustine", price=2400, amenities="wifi")
    api_setup["create"](area="mount_hope", price=2400, amenities="pool")
    response = api_setup["client"].get(
        "/api/student/listings",
        params={"area": "Mount Hope", "max_price": 2500, "amenity": "WIFI"},
        headers=api_setup["headers"](4),
    )
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["listings"]} == {wanted}


def test_admin_verify_then_owner_activate_is_visible(api_setup):
    listing_id = api_setup["create"](status="pending")
    client = api_setup["client"]
    headers = api_setup["headers"]
    verify = client.post(
        f"/api/listings/{listing_id}/transition",
        headers=headers(1), json={"action": "verify"},
    )
    assert verify.status_code == 200
    assert verify.json()["listing"]["status"] == "approved"
    activate = client.post(
        f"/api/listings/{listing_id}/transition",
        headers=headers(2), json={"action": "activate"},
    )
    assert activate.status_code == 200
    assert api_setup["stored"](listing_id)["status"] == "active"
    browse = client.get("/api/student/listings", headers=headers(4))
    assert {row["id"] for row in browse.json()["listings"]} == {listing_id}


def test_other_landlord_cannot_activate_listing(api_setup):
    listing_id = api_setup["create"](status="approved", landlord_id=2)
    response = api_setup["client"].post(
        f"/api/listings/{listing_id}/transition",
        headers=api_setup["headers"](3), json={"action": "activate"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "not listing owner"
    assert api_setup["stored"](listing_id)["status"] == "approved"


@pytest.mark.parametrize("user_id", [2, 3, 4, 5])
def test_non_admin_cannot_verify(api_setup, user_id):
    listing_id = api_setup["create"](status="pending")
    response = api_setup["client"].post(
        f"/api/listings/{listing_id}/transition",
        headers=api_setup["headers"](user_id), json={"action": "verify"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "admin only"
    assert api_setup["stored"](listing_id)["status"] == "pending"


def test_admin_cannot_use_landlord_activate_action(api_setup):
    listing_id = api_setup["create"](status="approved")
    response = api_setup["client"].post(
        f"/api/listings/{listing_id}/transition",
        headers=api_setup["headers"](1), json={"action": "activate"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "landlord only"
    assert api_setup["stored"](listing_id)["status"] == "approved"


def test_invalid_state_jump_keeps_original_status(api_setup):
    listing_id = api_setup["create"](status="pending")
    response = api_setup["client"].post(
        f"/api/listings/{listing_id}/transition",
        headers=api_setup["headers"](2), json={"action": "activate"},
    )
    assert response.status_code == 400
    assert api_setup["stored"](listing_id)["status"] == "pending"


@pytest.mark.parametrize("student_id", [4, 5])
def test_eligible_student_can_message_available_listing(api_setup, student_id):
    listing_id = api_setup["create"]()
    response = api_setup["client"].post(
        "/api/student/messages", headers=api_setup["headers"](student_id),
        json={"listing_id": listing_id, "body": "Is this available?"},
    )
    assert response.status_code == 200
    assert response.json()["message_id"] is not None
    assert api_setup["message_count"]() == 1


@pytest.mark.parametrize("student_id", [1, 2, 6, 999])
def test_ineligible_user_cannot_message(api_setup, student_id):
    listing_id = api_setup["create"]()
    response = api_setup["client"].post(
        "/api/student/messages", headers=api_setup["headers"](student_id),
        json={"listing_id": listing_id, "body": "Hi"},
    )
    assert response.status_code == 400
    assert api_setup["message_count"]() == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "pending"},
        {"status": "provisional"},
        {"status": "approved"},
        {"status": "inactive"},
        {"status": "rejected"},
        {"admin_hold": True},
        {"requires_reverification": True},
        {"area": "Arima"},
    ],
)
def test_unavailable_listing_cannot_be_messaged(api_setup, changes):
    listing_id = api_setup["create"](**changes)
    response = api_setup["client"].post(
        "/api/student/messages", headers=api_setup["headers"](4),
        json={"listing_id": listing_id, "body": "Hi"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "listing not available"
    assert api_setup["message_count"]() == 0


def test_missing_listing_cannot_be_messaged(api_setup):
    response = api_setup["client"].post(
        "/api/student/messages", headers=api_setup["headers"](4),
        json={"listing_id": 9999, "body": "Hi"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "listing not found"
    assert api_setup["message_count"]() == 0


def test_blank_message_is_rejected(api_setup):
    listing_id = api_setup["create"]()
    response = api_setup["client"].post(
        "/api/student/messages", headers=api_setup["headers"](4),
        json={"listing_id": listing_id, "body": "   "},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "body required"
    assert api_setup["message_count"]() == 0


def test_deactivation_removes_listing_from_browse_and_messaging(api_setup):
    listing_id = api_setup["create"]()
    headers = api_setup["headers"]
    client = api_setup["client"]
    before = client.get("/api/student/listings", headers=headers(4))
    assert listing_id in {row["id"] for row in before.json()["listings"]}
    deactivated = client.post(
        f"/api/listings/{listing_id}/transition",
        headers=headers(2), json={"action": "deactivate"},
    )
    assert deactivated.status_code == 200
    after = client.get("/api/student/listings", headers=headers(4))
    assert listing_id not in {row["id"] for row in after.json()["listings"]}
    message = client.post(
        "/api/student/messages", headers=headers(4),
        json={"listing_id": listing_id, "body": "Hi"},
    )
    assert message.status_code == 400
    assert message.json()["detail"] == "listing not available"
    assert api_setup["message_count"]() == 0
