"""Task #40: End-to-end administrator browser workflow tests."""

import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.routers import router as browser_router, static_files
from app.services import listings
from app.services.lifecycle import visible_to_students


@pytest.fixture
def admin_browser(test_session, monkeypatch):
    """A browser client backed by an isolated in-memory database."""

    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "student"},
    }

    current = {"id": 1}

    monkeypatch.setattr(listings, "engine", test_session.bind)
    monkeypatch.setattr(listings, "get_user", users.get)

    def logged_in_user():
        actor = users[current["id"]]

        return SimpleNamespace(
            id=actor["id"],
            role=actor["role"],
            username="BrowserTester",
        )

    application = FastAPI()

    application.add_middleware(
        SessionMiddleware,
        secret_key="task40-browser-test-secret",
    )

    application.include_router(browser_router)
    application.mount("/static", static_files, name="static")

    application.dependency_overrides[get_current_user] = (
        logged_in_user
    )

    client = TestClient(
        application,
        follow_redirects=False,
    )

    def create(
        status="pending",
        title="Test Property",
        feedback="",
        hold=False,
    ):
        listing = Listing(
            landlord_id=2,
            title=title,
            area="st_augustine",
            price=2500,
            amenities="wifi,parking",
            contact_phone="555-0100",
            contact_email="landlord@example.com",
            photos="",
            created_at="2026-11-24T10:00:00+00:00",
            status=status,
            review_feedback=feedback,
            admin_hold=hold,
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def saved(listing_id):
        test_session.expire_all()

        listing = test_session.get(Listing, listing_id)

        assert listing is not None

        return listing.model_dump()

    def csrf_token():
        # Create an actionable listing before calling this helper.
        page = client.get("/admin/listings")

        assert page.status_code == 200

        match = re.search(
            r'name="csrf_token"\s+value="([^"]+)"',
            page.text,
        )

        assert match is not None, (
            "Create an actionable listing before requesting a token"
        )

        return match.group(1)

    def submit(listing_id, action, token, feedback=None):
        form = {
            "action": action,
            "csrf_token": token,
        }

        if feedback is not None:
            form["review_feedback"] = feedback

        return client.post(
            f"/admin/listings/{listing_id}/review",
            data=form,
        )

    def sign_in(user_id):
        current["id"] = user_id

    return {
        "client": client,
        "create": create,
        "saved": saved,
        "csrf": csrf_token,
        "submit": submit,
        "sign_in": sign_in,
    }


def listing_row(page_html, title):
    """Find the HTML table row for a particular property."""

    rows = re.findall(
        r"<tr\b[^>]*>.*?</tr>",
        page_html,
        re.DOTALL,
    )

    for row in rows:
        if title in row:
            return row

    raise AssertionError(
        f"Could not find table row for {title}"
    )


def test_admin_home_links_to_listing_reviews(admin_browser):
    page = admin_browser["client"].get("/admin")

    assert page.status_code == 200
    assert "Review Listings" in page.text
    assert "/admin/listings" in page.text


def test_all_listing_states_appear_on_admin_page(
    admin_browser,
):
    states = [
        "pending",
        "provisional",
        "approved",
        "active",
        "inactive",
        "rejected",
    ]

    for state in states:
        admin_browser["create"](
            status=state,
            title=f"Property {state}",
        )

    page = admin_browser["client"].get("/admin/listings")

    assert page.status_code == 200

    for state in states:
        assert f"Property {state}" in page.text


def test_status_filter_only_shows_matching_listings(
    admin_browser,
):
    admin_browser["create"](
        title="Pending Apartment",
    )

    admin_browser["create"](
        status="active",
        title="Active Apartment",
    )

    page = admin_browser["client"].get(
        "/admin/listings?status=pending"
    )

    assert page.status_code == 200
    assert "Pending Apartment" in page.text
    assert "Active Apartment" not in page.text


def test_status_filter_shows_empty_message(admin_browser):
    admin_browser["create"](status="pending")

    page = admin_browser["client"].get(
        "/admin/listings?status=active"
    )

    assert page.status_code == 200
    assert "No listings match the selected filter" in page.text


@pytest.mark.parametrize(
    "state,expected,forbidden",
    [
        (
            "pending",
            [
                "Verify Listing",
                "Provisionally Accept",
                "Reject Listing",
            ],
            ["Force Deactivate"],
        ),
        (
            "provisional",
            ["Verify Listing"],
            [
                "Provisionally Accept",
                "Reject Listing",
                "Force Deactivate",
            ],
        ),
        (
            "active",
            ["Force Deactivate"],
            [
                "Verify Listing",
                "Provisionally Accept",
                "Reject Listing",
            ],
        ),
    ],
)
def test_action_buttons_match_listing_state(
    admin_browser,
    state,
    expected,
    forbidden,
):
    admin_browser["create"](
        status=state,
        title="Target Property",
    )

    page = admin_browser["client"].get("/admin/listings")

    assert page.status_code == 200

    row = listing_row(page.text, "Target Property")

    for label in expected:
        assert label in row

    for label in forbidden:
        assert label not in row


@pytest.mark.parametrize(
    "state",
    ["approved", "rejected", "inactive"],
)
def test_nonreviewable_states_have_no_action_forms(
    admin_browser,
    state,
):
    admin_browser["create"](
        status=state,
        title="Read Only Property",
    )

    page = admin_browser["client"].get("/admin/listings")

    assert page.status_code == 200
    assert "<form" not in listing_row(
        page.text,
        "Read Only Property",
    )


def test_verify_updates_listing_and_shows_confirmation(
    admin_browser,
):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()

    response = admin_browser["submit"](
        listing_id,
        "verify",
        token,
    )

    assert response.status_code == 303

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "approved"
    )

    page = admin_browser["client"].get("/admin/listings")

    assert "verified and approved successfully" in page.text

    assert "Approved" in listing_row(
        page.text,
        "Test Property",
    )


def test_rejection_persists_feedback_and_shows_confirmation(
    admin_browser,
):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()

    response = admin_browser["submit"](
        listing_id,
        "reject",
        token,
        feedback="  Incorrect property contact  ",
    )

    assert response.status_code == 303

    saved = admin_browser["saved"](listing_id)

    assert saved["status"] == "rejected"
    assert saved["review_feedback"] == (
        "Incorrect property contact"
    )

    page = admin_browser["client"].get("/admin/listings")

    assert "Listing rejected" in page.text
    assert "Incorrect property contact" in page.text


def test_provisional_to_approved_browser_workflow(
    admin_browser,
):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()

    first = admin_browser["submit"](
        listing_id,
        "provisionally_accept",
        token,
    )

    assert first.status_code == 303

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "provisional"
    )

    second = admin_browser["submit"](
        listing_id,
        "verify",
        token,
    )

    assert second.status_code == 303

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "approved"
    )


def test_force_deactivation_creates_administrative_hold(
    admin_browser,
):
    listing_id = admin_browser["create"](
        status="active"
    )

    token = admin_browser["csrf"]()

    response = admin_browser["submit"](
        listing_id,
        "force_deactivate",
        token,
    )

    assert response.status_code == 303

    saved = admin_browser["saved"](listing_id)

    assert saved["status"] == "inactive"
    assert saved["admin_hold"] is True
    assert visible_to_students(saved) is False

    page = admin_browser["client"].get("/admin/listings")

    assert "On administrative hold" in page.text


def test_invalid_transition_shows_error_and_preserves_state(
    admin_browser,
):
    # A pending listing provides the CSRF form.
    admin_browser["create"](
        title="Token Provider",
    )

    listing_id = admin_browser["create"](
        status="active",
        title="Live Property",
    )

    token = admin_browser["csrf"]()

    response = admin_browser["submit"](
        listing_id,
        "verify",
        token,
    )

    assert response.status_code == 303

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "active"
    )

    page = admin_browser["client"].get("/admin/listings")

    assert "Cannot perform" in page.text
    assert "alert-danger" in page.text


def test_blank_rejection_reason_is_blocked(admin_browser):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()
    before = admin_browser["saved"](listing_id).copy()

    response = admin_browser["submit"](
        listing_id,
        "reject",
        token,
        feedback="   ",
    )

    assert response.status_code == 303

    assert admin_browser["saved"](listing_id) == before

    page = admin_browser["client"].get("/admin/listings")

    assert "rejection feedback is required" in page.text
    assert "alert-danger" in page.text


def test_invalid_csrf_does_not_change_listing(
    admin_browser,
):
    listing_id = admin_browser["create"]()

    admin_browser["csrf"]()

    response = admin_browser["submit"](
        listing_id,
        "verify",
        "invalid-token",
    )

    assert response.status_code == 403

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "pending"
    )


def test_missing_csrf_is_rejected(admin_browser):
    listing_id = admin_browser["create"]()

    response = admin_browser["client"].post(
        f"/admin/listings/{listing_id}/review",
        data={"action": "verify"},
    )

    assert response.status_code == 403

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "pending"
    )


def test_unlisted_browser_action_is_rejected(admin_browser):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()
    before = admin_browser["saved"](listing_id).copy()

    response = admin_browser["submit"](
        listing_id,
        "activate",
        token,
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Invalid review action"
    }

    assert admin_browser["saved"](listing_id) == before


def test_missing_listing_review_returns_safe_error_and_preserves_state(
    admin_browser,
):
    existing_id = admin_browser["create"](
        title="Existing Property",
    )
    token = admin_browser["csrf"]()
    before = admin_browser["saved"](existing_id).copy()

    response = admin_browser["submit"](
        999999,
        "verify",
        token,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Listing not found"}
    assert admin_browser["saved"](existing_id) == before


@pytest.mark.parametrize("role_id", [2, 3])
@pytest.mark.parametrize(
    "path",
    ["/admin", "/admin/listings"],
)
def test_nonadmins_cannot_open_admin_pages(
    admin_browser,
    role_id,
    path,
):
    admin_browser["sign_in"](role_id)

    page = admin_browser["client"].get(path)

    assert page.status_code == 401


@pytest.mark.parametrize("role_id", [2, 3])
def test_nonadmins_cannot_post_admin_actions(
    admin_browser,
    role_id,
):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()

    admin_browser["sign_in"](role_id)

    response = admin_browser["submit"](
        listing_id,
        "verify",
        token,
    )

    assert response.status_code == 401

    assert (
        admin_browser["saved"](listing_id)["status"]
        == "pending"
    )


def test_rejection_feedback_is_safely_escaped(
    admin_browser,
):
    listing_id = admin_browser["create"]()
    token = admin_browser["csrf"]()
    supplied_feedback = "<script>alert('bad')</script>"

    response = admin_browser["submit"](
        listing_id,
        "reject",
        token,
        feedback=supplied_feedback,
    )

    assert response.status_code == 303
    saved = admin_browser["saved"](listing_id)
    assert saved["status"] == "rejected"
    assert saved["review_feedback"] == supplied_feedback

    page = admin_browser["client"].get("/admin/listings")

    assert page.status_code == 200
    assert supplied_feedback not in page.text
    assert "&lt;script&gt;alert(&#39;bad&#39;)&lt;/script&gt;" in page.text


def test_review_changes_only_targeted_listing(
    admin_browser,
):
    first_id = admin_browser["create"](
        title="First Property",
    )

    second_id = admin_browser["create"](
        title="Second Property",
    )

    token = admin_browser["csrf"]()

    response = admin_browser["submit"](
        first_id,
        "verify",
        token,
    )

    assert response.status_code == 303

    assert (
        admin_browser["saved"](first_id)["status"]
        == "approved"
    )

    assert (
        admin_browser["saved"](second_id)["status"]
        == "pending"
    )