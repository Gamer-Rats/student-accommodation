import pytest

from sqlmodel import select

from app.models.listing import Listing
from app.models.message import Message
from app.repositories.listing import ListingRepository


@pytest.fixture
def repository_setup(test_session):
    """Provide an isolated repository and database."""

    repository = ListingRepository(test_session)

    def make_listing(
        landlord_id=1,
        title="Test Apartment",
        status="pending",
    ):
        return Listing(
            landlord_id=landlord_id,
            title=title,
            area="st_augustine",
            price=2500,
            amenities="wifi",
            contact_phone="868-555-1234",
            contact_email="owner@example.com",
            photos="",
            created_at="2026-11-25T10:00:00+00:00",
            status=status,
        )

    return repository, test_session, make_listing


def test_create_listing(repository_setup):
    repository, db, make_listing = repository_setup

    listing = make_listing()

    saved = repository.create(listing)

    assert saved.id is not None
    assert saved.title == "Test Apartment"
    assert saved.status == "pending"

    db.expire_all()

    stored = db.get(Listing, saved.id)

    assert stored is not None
    assert stored.landlord_id == 1


def test_get_listing_by_id(repository_setup):
    repository, _, make_listing = repository_setup

    saved = repository.create(
        make_listing(title="Apartment Near Campus")
    )

    result = repository.get_by_id(saved.id)

    assert result is not None
    assert result.id == saved.id
    assert result.title == "Apartment Near Campus"


def test_unknown_listing_returns_none(repository_setup):
    repository, _, _ = repository_setup

    assert repository.get_by_id(999999) is None


def test_get_all_listings(repository_setup):
    repository, _, make_listing = repository_setup

    repository.create(
        make_listing(title="First Apartment")
    )

    repository.create(
        make_listing(title="Second Apartment")
    )

    listings = repository.get_all()

    assert len(listings) == 2
    assert listings[0].title == "First Apartment"
    assert listings[1].title == "Second Apartment"


def test_get_all_filters_by_status(repository_setup):
    repository, _, make_listing = repository_setup

    repository.create(
        make_listing(
            title="Pending Apartment",
            status="pending",
        )
    )

    repository.create(
        make_listing(
            title="Active Apartment",
            status="active",
        )
    )

    active = repository.get_all(status="active")

    assert len(active) == 1
    assert active[0].title == "Active Apartment"
    assert active[0].status == "active"


def test_get_by_landlord_filters_ownership(repository_setup):
    repository, _, make_listing = repository_setup

    repository.create(
        make_listing(
            landlord_id=1,
            title="Landlord One Property",
        )
    )

    repository.create(
        make_listing(
            landlord_id=2,
            title="Landlord Two Property",
        )
    )

    own_listings = repository.get_by_landlord(1)

    assert len(own_listings) == 1
    assert own_listings[0].landlord_id == 1
    assert own_listings[0].title == "Landlord One Property"


def test_get_inbox_by_landlord_filters_by_listing_owner(
    repository_setup,
):
    repository, _, make_listing = repository_setup

    own_listing = repository.create(
        make_listing(
            landlord_id=1,
            title="Landlord One Property",
        )
    )
    other_listing = repository.create(
        make_listing(
            landlord_id=2,
            title="Landlord Two Property",
        )
    )

    own_message = repository.create_message(
        Message(
            listing_id=own_listing.id,
            student_id=3,
            body="Message for landlord one",
            created_at="2026-11-25T10:00:00+00:00",
        )
    )
    repository.create_message(
        Message(
            listing_id=other_listing.id,
            student_id=4,
            body="Message for landlord two",
            created_at="2026-11-25T11:00:00+00:00",
        )
    )

    rows = repository.get_inbox_by_landlord(1)

    assert len(rows) == 1
    assert rows[0][0].id == own_message.id
    assert rows[0][1].id == own_listing.id


def test_get_inbox_by_landlord_returns_empty_list(
    repository_setup,
):
    repository, _, _ = repository_setup

    assert repository.get_inbox_by_landlord(1) == []


def test_get_inbox_by_landlord_orders_newest_first_with_id_tiebreaker(
    repository_setup,
):
    repository, _, make_listing = repository_setup
    listing = repository.create(
        make_listing(landlord_id=1)
    )

    messages = [
        Message(
            listing_id=listing.id,
            student_id=3,
            body="Older message",
            created_at="2026-11-24T10:00:00+00:00",
        ),
        Message(
            listing_id=listing.id,
            student_id=3,
            body="Earlier message at same time",
            created_at="2026-11-25T10:00:00+00:00",
        ),
        Message(
            listing_id=listing.id,
            student_id=3,
            body="Later message at same time",
            created_at="2026-11-25T10:00:00+00:00",
        ),
        Message(
            listing_id=listing.id,
            student_id=3,
            body="Newest message",
            created_at="2026-11-26T10:00:00+00:00",
        ),
    ]
    saved_messages = [
        repository.create_message(message)
        for message in messages
    ]

    rows = repository.get_inbox_by_landlord(1)

    assert [row[0].body for row in rows] == [
        "Newest message",
        "Later message at same time",
        "Earlier message at same time",
        "Older message",
    ]
    assert rows[1][0].id == saved_messages[2].id
    assert rows[2][0].id == saved_messages[1].id


def test_get_inbox_by_landlord_keeps_messages_without_student_details(
    repository_setup,
):
    repository, _, make_listing = repository_setup
    listing = repository.create(
        make_listing(landlord_id=1)
    )
    message = repository.create_message(
        Message(
            listing_id=listing.id,
            student_id=999,
            body="Message from missing student",
            created_at="2026-11-25T10:00:00+00:00",
        )
    )

    rows = repository.get_inbox_by_landlord(1)

    assert len(rows) == 1
    assert rows[0][0].id == message.id
    assert rows[0][2] is None


def test_landlord_with_no_listings_returns_empty_list(
    repository_setup,
):
    repository, _, make_listing = repository_setup

    repository.create(
        make_listing(landlord_id=1)
    )

    result = repository.get_by_landlord(999)

    assert result == []


def test_save_updates_existing_listing(repository_setup):
    repository, db, make_listing = repository_setup

    listing = repository.create(
        make_listing()
    )

    listing.title = "Updated Apartment"
    listing.price = 3200
    listing.status = "approved"

    saved = repository.save(listing)

    assert saved.title == "Updated Apartment"
    assert saved.price == 3200
    assert saved.status == "approved"

    db.expire_all()

    stored = db.get(Listing, listing.id)

    assert stored.title == "Updated Apartment"
    assert stored.price == 3200
    assert stored.status == "approved"


def test_create_message(repository_setup):
    repository, db, make_listing = repository_setup

    listing = repository.create(
        make_listing(status="active")
    )

    message = Message(
        listing_id=listing.id,
        student_id=3,
        body="Is this apartment available?",
        created_at="2026-11-25T11:00:00+00:00",
    )

    saved = repository.create_message(message)

    assert saved.id is not None
    assert saved.listing_id == listing.id
    assert saved.student_id == 3

    db.expire_all()

    stored = db.get(Message, saved.id)

    assert stored is not None
    assert stored.body == "Is this apartment available?"


def test_get_all_returns_empty_list_for_empty_database(
    repository_setup,
):
    repository, _, _ = repository_setup

    assert repository.get_all() == []


def test_repository_does_not_modify_listing_status(
    repository_setup,
):
    """Business lifecycle rules belong to the service layer."""

    repository, _, make_listing = repository_setup

    listing = repository.create(
        make_listing(status="pending")
    )

    assert listing.status == "pending"

    fetched = repository.get_by_id(listing.id)

    assert fetched.status == "pending"


def test_repository_returns_listings_in_id_order(
    repository_setup,
):
    repository, _, make_listing = repository_setup

    first = repository.create(
        make_listing(title="First")
    )

    second = repository.create(
        make_listing(title="Second")
    )

    results = repository.get_all()

    assert [item.id for item in results] == [
        first.id,
        second.id,
    ]
