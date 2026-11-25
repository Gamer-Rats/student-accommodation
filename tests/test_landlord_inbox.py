
"""Task #45: Landlord inbox website tests."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.listing import Listing
from app.models.message import Message
from app.models.user import User
from app.routers import router, static_files


@pytest.fixture
def inbox_setup(test_session):
    """Set up an isolated landlord inbox test website."""

    users = {
        1: SimpleNamespace(
            id=1,
            role="admin",
            username="admin",
        ),
        2: SimpleNamespace(
            id=2,
            role="landlord",
            username="landlord",
        ),
        3: SimpleNamespace(
            id=3,
            role="landlord",
            username="landlord2",
        ),
        4: SimpleNamespace(
            id=4,
            role="student",
            username="student",
        ),
    }

    current = {"id": 2}

    def authenticated_user():
        return users[current["id"]]

    def test_database():
        yield test_session

    app = FastAPI()

    app.add_middleware(
        SessionMiddleware,
        secret_key="task45-inbox-test-secret",
    )

    app.include_router(router)

    app.mount(
        "/static",
        static_files,
        name="static",
    )

    app.dependency_overrides[
        get_current_user
    ] = authenticated_user

    app.dependency_overrides[
        get_session
    ] = test_database

    def create_user(
        username,
        display_name,
    ):
        user = User(
            username=username,
            email=f"{username}@example.com",
            password="test-password",
            role="student",
            display_name=display_name,
            student_id="202012345",
        )

        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        return user.id

    def create_listing(
        owner=2,
        title="Test Apartment",
        listing_status="active",
    ):
        listing = Listing(
            landlord_id=owner,
            title=title,
            area="st_augustine",
            price=2500,
            amenities="wifi, parking",
            contact_phone="868-555-1234",
            contact_email="landlord@example.com",
            photos="",
            status=listing_status,
            created_at="2026-11-24T10:00:00+00:00",
        )

        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)

        return listing.id

    def create_message(
        listing_id,
        student_id,
        body="Is this apartment available?",
        created_at="2026-11-24T12:00:00+00:00",
    ):
        message = Message(
            listing_id=listing_id,
            student_id=student_id,
            body=body,
            created_at=created_at,
        )

        test_session.add(message)
        test_session.commit()
        test_session.refresh(message)

        return message.id

    with TestClient(
        app,
        follow_redirects=False,
    ) as client:

        def sign_in(user_id):
            current["id"] = user_id

        yield {
            "client": client,
            "sign_in": sign_in,
            "create_user": create_user,
            "create_listing": create_listing,
            "create_message": create_message,
        }


def test_landlord_can_open_inbox(inbox_setup):
    response = inbox_setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "Landlord Inbox" in response.text
    assert "Student Inquiries" in response.text


def test_empty_inbox_displays_message(inbox_setup):
    response = inbox_setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "No Messages Yet" in response.text
    assert 'id="message-count"' in response.text


def test_landlord_can_read_student_message(inbox_setup):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_one",
        "Student One",
    )

    listing_id = setup["create_listing"](
        title="Apartment Near UWI",
    )

    setup["create_message"](
        listing_id,
        student_id,
        body="Can I arrange a viewing?",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "Student One" in response.text
    assert "@student_one" in response.text
    assert "Apartment Near UWI" in response.text
    assert "Can I arrange a viewing?" in response.text


def test_landlord_only_sees_own_messages(inbox_setup):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_two",
        "Student Two",
    )

    own_listing = setup["create_listing"](
        owner=2,
        title="My Apartment",
    )

    other_listing = setup["create_listing"](
        owner=3,
        title="Other Landlord Apartment",
    )

    setup["create_message"](
        own_listing,
        student_id,
        body="Message for landlord one",
    )

    setup["create_message"](
        other_listing,
        student_id,
        body="Private message for landlord two",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "My Apartment" in response.text
    assert "Message for landlord one" in response.text

    assert "Other Landlord Apartment" not in response.text
    assert "Private message for landlord two" not in response.text


def test_second_landlord_sees_only_their_messages(
    inbox_setup,
):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_three",
        "Student Three",
    )

    listing_one = setup["create_listing"](
        owner=2,
        title="First Landlord Property",
    )

    listing_two = setup["create_listing"](
        owner=3,
        title="Second Landlord Property",
    )

    setup["create_message"](
        listing_one,
        student_id,
        body="Message for first landlord",
    )

    setup["create_message"](
        listing_two,
        student_id,
        body="Message for second landlord",
    )

    setup["sign_in"](3)

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "Second Landlord Property" in response.text
    assert "Message for second landlord" in response.text

    assert "First Landlord Property" not in response.text
    assert "Message for first landlord" not in response.text


@pytest.mark.parametrize(
    "user_id",
    [1, 4],
)
def test_non_landlords_cannot_access_inbox(
    inbox_setup,
    user_id,
):
    setup = inbox_setup

    setup["sign_in"](user_id)

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 403


def test_multiple_messages_are_displayed(inbox_setup):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_four",
        "Student Four",
    )

    listing_id = setup["create_listing"]()

    setup["create_message"](
        listing_id,
        student_id,
        body="First inquiry",
    )

    setup["create_message"](
        listing_id,
        student_id,
        body="Second inquiry",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "First inquiry" in response.text
    assert "Second inquiry" in response.text


def test_messages_are_sorted_newest_first(inbox_setup):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_five",
        "Student Five",
    )

    listing_id = setup["create_listing"]()

    setup["create_message"](
        listing_id,
        student_id,
        body="Older inquiry",
        created_at="2026-11-20T10:00:00+00:00",
    )

    setup["create_message"](
        listing_id,
        student_id,
        body="Newest inquiry",
        created_at="2026-11-24T10:00:00+00:00",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200

    assert (
        response.text.index("Newest inquiry")
        < response.text.index("Older inquiry")
    )


def test_messages_remain_after_listing_deactivation(
    inbox_setup,
):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_six",
        "Student Six",
    )

    listing_id = setup["create_listing"](
        listing_status="inactive",
    )

    setup["create_message"](
        listing_id,
        student_id,
        body="Previous student inquiry",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "Previous student inquiry" in response.text


def test_message_html_is_escaped(inbox_setup):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_seven",
        "Student Seven",
    )

    listing_id = setup["create_listing"]()

    setup["create_message"](
        listing_id,
        student_id,
        body="<script>alert('bad')</script>",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_student_name_is_escaped(inbox_setup):
    setup = inbox_setup

    student_id = setup["create_user"](
        "student_eight",
        "<b>Student Eight</b>",
    )

    listing_id = setup["create_listing"]()

    setup["create_message"](
        listing_id,
        student_id,
        body="Hello landlord",
    )

    response = setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "<b>Student Eight</b>" not in response.text
    assert "&lt;b&gt;Student Eight&lt;/b&gt;" in response.text


def test_inbox_link_appears_in_landlord_navigation(
    inbox_setup,
):
    response = inbox_setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert "Inbox" in response.text
    assert 'href="http://testserver/app/landlord/inbox"' in response.text


def test_inbox_link_is_active_on_inbox_page(inbox_setup):
    response = inbox_setup["client"].get(
        "/app/landlord/inbox"
    )

    assert response.status_code == 200
    assert 'aria-current="page"' in response.text

