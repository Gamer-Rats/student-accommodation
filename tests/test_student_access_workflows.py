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
from app.routers import router as browser_router, static_files
from app.routers import accommodation
from app.services import listings
from app.utilities.security import create_access_token


@pytest.fixture
def student_workflow(test_session, monkeypatch):
    """Create an isolated website, API and test database."""

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
        users.get,
    )

    monkeypatch.setattr(
        accommodation.auth,
        "get_user",
        users.get,
    )

    current = {"id": 3}

    def browser_user():
        actor = users[current["id"]]

        return SimpleNamespace(
            id=actor["id"],
            role=actor["role"],
            username="StudentWorkflowTester",
        )

    test_app = FastAPI()

    test_app.add_middleware(
        SessionMiddleware,
        secret_key="task48-test-secret",
    )

    test_app.include_router(browser_router)

    test_app.include_router(
        accommodation.router,
        prefix="/api",
    )

    test_app.mount(
        "/static",
        static_files,
        name="static",
    )

    test_app.dependency_overrides[
        get_current_user
    ] = browser_user

    def create_listing(
        title="Available Apartment",
        status="active",
        area="st_augustine",
        price=2500,
        amenities="wifi,parking",
        admin_hold=False,
        requires_reverification=False,
    ):
        listing = Listing(
            landlord_id=2,
            title=title,
            area=area,
            price=price,
            amenities=amenities,
            contact_phone="555-1234",
            contact_email="landlord@example.com",
            photos="",
            created_at="2026-11-25T10:00:00+00:00",
            status=status,
            admin_hold=admin_hold,
            requires_reverification=requires_reverification,
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def authorization(user_id):
        token = create_access_token(
            {"sub": str(user_id)}
        )

        return {
            "Authorization": f"Bearer {token}"
        }

    def select_browser_user(user_id):
        current["id"] = user_id

    def saved_messages():
        test_session.expire_all()

        return test_session.exec(
            select(Message).order_by(Message.id)
        ).all()

    with TestClient(
        test_app,
        follow_redirects=False,
    ) as client:
        def csrf_token(listing_id):
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

        yield {
            "client": client,
            "create": create_listing,
            "headers": authorization,
            "sign_in": select_browser_user,
            "messages": saved_messages,
            "csrf": csrf_token,
        }


def test_complete_student_browse_and_message_journey(
    student_workflow,
):
    setup = student_workflow
    client = setup["client"]

    listing_id = setup["create"](
        title="Campus Apartment"
    )

    setup["create"](
        title="Hidden Pending Apartment",
        status="pending",
    )

    browse = client.get("/app/listings")

    assert browse.status_code == 200
    assert "Campus Apartment" in browse.text
    assert "Hidden Pending Apartment" not in browse.text

    details = client.get(
        f"/app/listings/{listing_id}"
    )

    assert details.status_code == 200
    assert "Campus Apartment" in details.text
    assert "Send Message to Landlord" in details.text

    token = setup["csrf"](listing_id)

    response = client.post(
        f"/app/listings/{listing_id}/message",
        data={
            "csrf_token": token,
            "body": "  Can I arrange a viewing?  ",
        },
    )

    assert response.status_code == 303

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].listing_id == listing_id
    assert messages[0].student_id == 3
    assert messages[0].body == (
        "Can I arrange a viewing?"
    )


def test_browser_and_api_apply_same_search_filters(
    student_workflow,
):
    setup = student_workflow

    wanted_id = setup["create"](
        title="Matching Apartment",
        area="mount_hope",
        price=2400,
        amenities="WiFi, Parking",
    )

    setup["create"](
        title="Too Expensive",
        area="mount_hope",
        price=4000,
    )

    setup["create"](
        title="Wrong Area",
        area="st_augustine",
        price=2400,
    )

    setup["create"](
        title="Wrong Amenity",
        area="mount_hope",
        price=2400,
        amenities="pool",
    )

    filters = {
        "area": "Mount Hope",
        "max_price": 2500,
        "amenity": "WIFI",
    }

    browser = setup["client"].get(
        "/app/listings",
        params=filters,
    )

    assert browser.status_code == 200
    assert "Matching Apartment" in browser.text
    assert "Too Expensive" not in browser.text
    assert "Wrong Area" not in browser.text
    assert "Wrong Amenity" not in browser.text

    api = setup["client"].get(
        "/api/student/listings",
        params=filters,
        headers=setup["headers"](3),
    )

    assert api.status_code == 200

    ids = {
        listing["id"]
        for listing in api.json()["listings"]
    }

    assert ids == {wanted_id}


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "provisional",
        "approved",
        "inactive",
        "rejected",
    ],
)
def test_unavailable_listing_hidden_across_workflows(
    student_workflow,
    status,
):
    setup = student_workflow

    listing_id = setup["create"](
        title="Restricted Apartment",
        status=status,
    )

    browser = setup["client"].get("/app/listings")

    assert browser.status_code == 200
    assert "Restricted Apartment" not in browser.text

    details = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert details.status_code == 404

    api = setup["client"].get(
        "/api/student/listings",
        headers=setup["headers"](3),
    )

    assert api.status_code == 200
    assert api.json()["listings"] == []

    message = setup["client"].post(
        "/api/student/messages",
        headers=setup["headers"](3),
        json={
            "listing_id": listing_id,
            "body": "Is it available?",
        },
    )

    assert message.status_code == 400
    assert message.json()["detail"] == (
        "listing not available"
    )
    assert setup["messages"]() == []


@pytest.mark.parametrize(
    "restrictions",
    [
        {"admin_hold": True},
        {"requires_reverification": True},
        {"area": "arima"},
    ],
)
def test_restricted_active_listing_is_not_available(
    student_workflow,
    restrictions,
):
    setup = student_workflow

    listing_id = setup["create"](
        title="Restricted Active Property",
        **restrictions,
    )

    browse = setup["client"].get("/app/listings")

    assert browse.status_code == 200
    assert "Restricted Active Property" not in browse.text

    details = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert details.status_code == 404

    api = setup["client"].get(
        "/api/student/listings",
        headers=setup["headers"](3),
    )

    assert api.status_code == 200
    assert api.json()["listings"] == []


def test_provisional_student_has_access(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"]()

    setup["sign_in"](4)

    browser = setup["client"].get("/app/listings")
    details = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    api = setup["client"].get(
        "/api/student/listings",
        headers=setup["headers"](4),
    )

    assert browser.status_code == 200
    assert details.status_code == 200
    assert api.status_code == 200
    assert len(api.json()["listings"]) == 1


def test_ineligible_student_is_denied_access(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"]()

    setup["sign_in"](5)

    browser = setup["client"].get("/app/listings")
    details = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    api = setup["client"].get(
        "/api/student/listings",
        headers=setup["headers"](5),
    )

    assert browser.status_code == 403
    assert details.status_code == 403
    assert api.status_code == 403
    assert api.json()["detail"] == (
        "student eligibility required"
    )


@pytest.mark.parametrize("user_id", [1, 2])
def test_other_roles_cannot_browse_student_listings(
    student_workflow,
    user_id,
):
    setup = student_workflow

    listing_id = setup["create"]()

    setup["sign_in"](user_id)

    browser = setup["client"].get("/app/listings")

    details = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    api = setup["client"].get(
        "/api/student/listings",
        headers=setup["headers"](user_id),
    )

    assert browser.status_code == 403
    assert details.status_code == 403
    assert api.status_code == 403


def test_api_requires_authentication(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"]()

    browse = setup["client"].get(
        "/api/student/listings"
    )

    message = setup["client"].post(
        "/api/student/messages",
        json={
            "listing_id": listing_id,
            "body": "Hello",
        },
    )

    assert browse.status_code == 401
    assert message.status_code == 401
    assert setup["messages"]() == []


def test_forged_user_id_header_does_not_grant_access(
    student_workflow,
):
    setup = student_workflow

    response = setup["client"].get(
        "/api/student/listings",
        headers={"X-User-Id": "3"},
    )

    assert response.status_code == 401


def test_invalid_location_filter_is_rejected(
    student_workflow,
):
    setup = student_workflow

    browser = setup["client"].get(
        "/app/listings",
        params={"area": "Arima"},
    )

    api = setup["client"].get(
        "/api/student/listings",
        params={"area": "Arima"},
        headers=setup["headers"](3),
    )

    assert browser.status_code == 400
    assert api.status_code == 400


def test_invalid_price_filter_is_rejected(
    student_workflow,
):
    setup = student_workflow

    browser = setup["client"].get(
        "/app/listings",
        params={"max_price": "not-a-number"},
    )

    api = setup["client"].get(
        "/api/student/listings",
        params={"max_price": "not-a-number"},
        headers=setup["headers"](3),
    )

    assert browser.status_code == 400
    assert api.status_code == 422


def test_api_message_is_saved_for_authenticated_student(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"]()

    response = setup["client"].post(
        "/api/student/messages",
        headers=setup["headers"](3),
        json={
            "listing_id": listing_id,
            "student_id": 999,
            "body": "Is parking available?",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True

    messages = setup["messages"]()

    assert len(messages) == 1
    assert messages[0].listing_id == listing_id
    assert messages[0].student_id == 3
    assert messages[0].body == (
        "Is parking available?"
    )


@pytest.mark.parametrize(
    "body",
    ["", "   ", "A" * 2001],
)
def test_browser_rejects_invalid_message_body(
    student_workflow,
    body,
):
    setup = student_workflow

    listing_id = setup["create"]()
    token = setup["csrf"](listing_id)

    response = setup["client"].post(
        f"/app/listings/{listing_id}/message",
        data={
            "csrf_token": token,
            "body": body,
        },
    )

    assert response.status_code == 303
    assert setup["messages"]() == []


@pytest.mark.parametrize(
    "token",
    ["", "invalid-security-token"],
)
def test_browser_rejects_invalid_csrf_token(
    student_workflow,
    token,
):
    setup = student_workflow

    listing_id = setup["create"]()

    setup["csrf"](listing_id)

    response = setup["client"].post(
        f"/app/listings/{listing_id}/message",
        data={
            "csrf_token": token,
            "body": "Hello landlord",
        },
    )

    assert response.status_code == 403
    assert setup["messages"]() == []


def test_ineligible_student_cannot_send_api_message(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"]()

    response = setup["client"].post(
        "/api/student/messages",
        headers=setup["headers"](5),
        json={
            "listing_id": listing_id,
            "body": "Hello",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "student eligibility required"
    )
    assert setup["messages"]() == []


def test_blank_api_message_is_rejected(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"]()

    response = setup["client"].post(
        "/api/student/messages",
        headers=setup["headers"](3),
        json={
            "listing_id": listing_id,
            "body": "   ",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "body required"
    assert setup["messages"]() == []


def test_missing_listing_cannot_be_viewed_or_messaged(
    student_workflow,
):
    setup = student_workflow

    response = setup["client"].get(
        "/app/listings/999999"
    )

    assert response.status_code == 404

    message = setup["client"].post(
        "/api/student/messages",
        headers=setup["headers"](3),
        json={
            "listing_id": 999999,
            "body": "Hello",
        },
    )

    assert message.status_code == 400
    assert message.json()["detail"] == (
        "listing not found"
    )
    assert setup["messages"]() == []


def test_deactivation_removes_student_access(
    student_workflow,
):
    setup = student_workflow

    listing_id = setup["create"](
        title="Soon Unavailable Apartment"
    )

    before = setup["client"].get("/app/listings")

    assert "Soon Unavailable Apartment" in before.text

    deactivated = setup["client"].post(
        f"/api/listings/{listing_id}/transition",
        headers=setup["headers"](2),
        json={"action": "deactivate"},
    )

    assert deactivated.status_code == 200
    assert deactivated.json()["listing"]["status"] == (
        "inactive"
    )

    after = setup["client"].get("/app/listings")

    assert after.status_code == 200
    assert "Soon Unavailable Apartment" not in after.text

    details = setup["client"].get(
        f"/app/listings/{listing_id}"
    )

    assert details.status_code == 404

    message = setup["client"].post(
        "/api/student/messages",
        headers=setup["headers"](3),
        json={
            "listing_id": listing_id,
            "body": "Is it still available?",
        },
    )

    assert message.status_code == 400
    assert setup["messages"]() == []
