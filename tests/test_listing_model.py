from app.models.listing import Listing

def make_listing(**changes):
    data = {
        "landlord_id": 1,
        "title": "Test Accommodation",
        "area": "st_augustine",
        "price": 2500,
        "amenities": "wifi,parking",
        "contact_phone": "555-1234",
        "contact_email": "landlord@example.com",
        "created_at": "2026-11-23T10:00:00+00:00",
    }
    data.update(changes)
    return Listing(**data)


def test_listing_defaults_to_pending():
    listing = make_listing()

    assert listing.status == "pending"


def test_model_has_no_redundant_flags():
    columns = {column.name for column in Listing.__table__.columns}

    assert "status" in columns

    for flag in (
        "flag_pending",
        "flag_verified",
        "flag_active",
        "flag_rejected",
    ):
        assert flag not in columns


def test_administrative_fields_have_defaults():
    listing = make_listing()

    assert listing.review_feedback == ""
    assert listing.admin_hold is False
    assert listing.requires_reverification is False


def test_listing_status_can_be_persisted(test_session):
    listing = make_listing(status="approved")

    test_session.add(listing)
    test_session.commit()
    test_session.refresh(listing)

    saved = test_session.get(Listing, listing.id)

    assert saved is not None
    assert saved.status == "approved"


def test_restrictions_can_be_persisted(test_session):
    listing = make_listing(
        status="inactive",
        review_feedback="Requires further inspection",
        admin_hold=True,
        requires_reverification=True,
    )

    test_session.add(listing)
    test_session.commit()
    test_session.refresh(listing)

    saved = test_session.get(Listing, listing.id)

    assert saved is not None
    assert saved.status == "inactive"
    assert saved.admin_hold is True
    assert saved.requires_reverification is True
    assert saved.review_feedback == "Requires further inspection"