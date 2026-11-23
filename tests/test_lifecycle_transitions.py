"""Comprehensive transition and persistence tests for the listing State Pattern."""

from itertools import product

import pytest
from sqlmodel import Session

from app.models.listing import Listing
from app.services import listings
from app.services.lifecycle import ACTIONS, STATES, apply_action, visible_to_students
from app.services.listing_lifecycle import ListingLifecycle


EXPECTED_TRANSITIONS = {
    "pending": {
        "verify": "approved",
        "provisionally_accept": "provisional",
        "reject": "rejected",
    },
    "provisional": {"verify": "approved"},
    "approved": {"activate": "active"},
    "active": {
        "deactivate": "inactive",
        "force_deactivate": "inactive",
    },
    "inactive": {"activate": "active"},
    "rejected": {"resubmit": "pending"},
}
STATUSES = tuple(EXPECTED_TRANSITIONS)
ACTIONS_TO_TEST = (
    "verify", "provisionally_accept", "reject", "activate",
    "deactivate", "force_deactivate", "resubmit",
)


def listing_data(status="pending", **changes):
    data = {
        "id": 10,
        "landlord_id": 2,
        "status": status,
        "area": "st_augustine",
        "admin_hold": False,
        "requires_reverification": False,
        "review_feedback": "",
    }
    data.update(changes)
    return data


def test_all_states_and_actions_are_registered():
    assert set(STATES) == set(STATUSES)
    assert set(ACTIONS) == set(ACTIONS_TO_TEST)


@pytest.mark.parametrize("status,action", list(product(STATUSES, ACTIONS_TO_TEST)))
def test_all_transition_pairs_through_service_adapter(status, action):
    original = listing_data(status)
    unchanged = dict(original)
    result = apply_action(original, action)
    expected = EXPECTED_TRANSITIONS[status].get(action)

    assert original == unchanged
    if expected is None:
        assert result["ok"] is False
        assert "error" in result
        assert "row" not in result
    else:
        assert result["ok"] is True
        assert result["changed"] is True
        assert result["row"]["status"] == expected
        assert result["listing"] == result["row"]
        assert result["row"]["id"] == original["id"]
        assert result["row"]["admin_hold"] is (action == "force_deactivate")


@pytest.mark.parametrize("status,action", list(product(STATUSES, ACTIONS_TO_TEST)))
def test_all_transition_pairs_through_context(status, action):
    original = listing_data(status)
    lifecycle = ListingLifecycle(original, STATES)
    expected = EXPECTED_TRANSITIONS[status].get(action)

    if expected is None:
        with pytest.raises(ValueError):
            lifecycle.transition(action)
        assert lifecycle.listing == original
        assert lifecycle.current_state is STATES[status]
    else:
        next_state = lifecycle.transition(action)
        assert lifecycle.listing["status"] == expected
        assert lifecycle.current_state is next_state
        assert next_state is STATES[expected]
    assert original["status"] == status


@pytest.mark.parametrize("status", STATUSES)
def test_visibility_matches_current_state(status):
    data = listing_data(status)
    lifecycle = ListingLifecycle(data, STATES)
    should_be_visible = status == "active"
    assert lifecycle.is_visible() is should_be_visible
    assert visible_to_students(data) is should_be_visible


@pytest.mark.parametrize(
    "admin_hold,requires_reverification,expected",
    [
        (False, False, True),
        (True, False, False),
        (False, True, False),
        (True, True, False),
    ],
)
def test_active_visibility_respects_administrative_flags(
    admin_hold, requires_reverification, expected
):
    data = listing_data(
        "active",
        admin_hold=admin_hold,
        requires_reverification=requires_reverification,
    )
    assert visible_to_students(data) is expected


@pytest.mark.parametrize("status", ["approved", "inactive"])
@pytest.mark.parametrize(
    "restrictions",
    [
        {"admin_hold": True},
        {"requires_reverification": True},
        {"admin_hold": True, "requires_reverification": True},
    ],
)
def test_activation_is_blocked_by_restrictions(status, restrictions):
    original = listing_data(status, **restrictions)
    result = apply_action(original, "activate")
    assert result["ok"] is False
    assert original["status"] == status
    assert "row" not in result


@pytest.mark.parametrize("status", STATUSES)
def test_unknown_action_does_not_change_state(status):
    original = listing_data(status)
    lifecycle = ListingLifecycle(original, STATES)
    result = apply_action(original, "submit")
    assert result["ok"] is False
    assert "unknown action" in result["error"]
    with pytest.raises(ValueError):
        lifecycle.transition("submit")
    assert lifecycle.listing == original


@pytest.mark.parametrize("bad_status", ["verified", "mystery", ""])
def test_unknown_status_is_handled_safely(bad_status):
    data = listing_data(bad_status)
    with pytest.raises(ValueError, match="Unknown listing state"):
        ListingLifecycle(data, STATES)
    assert apply_action(data, "activate")["ok"] is False
    assert visible_to_students(data) is False


def test_missing_status_is_handled_safely():
    data = {"id": 10, "admin_hold": False}
    with pytest.raises(KeyError):
        ListingLifecycle(data, STATES)
    assert apply_action(data, "verify")["ok"] is False
    assert visible_to_students(data) is False


@pytest.mark.parametrize(
    "start,steps",
    [
        (
            "pending",
            [
                ("verify", "approved"),
                ("activate", "active"),
                ("deactivate", "inactive"),
                ("activate", "active"),
            ],
        ),
        (
            "pending",
            [
                ("provisionally_accept", "provisional"),
                ("verify", "approved"),
                ("activate", "active"),
            ],
        ),
        (
            "pending",
            [
                ("reject", "rejected"),
                ("resubmit", "pending"),
                ("verify", "approved"),
                ("activate", "active"),
            ],
        ),
    ],
)
def test_complete_state_workflows(start, steps):
    row = listing_data(start)
    for action, expected in steps:
        result = apply_action(row, action)
        assert result["ok"] is True
        row = result["row"]
        assert row["status"] == expected
        assert visible_to_students(row) is (expected == "active")
        assert not any(
            flag in row
            for flag in (
                "flag_pending", "flag_verified", "flag_active", "flag_rejected"
            )
        )


def test_forced_deactivation_cannot_be_reactivated_on_hold():
    row = listing_data("active")
    result = apply_action(row, "force_deactivate")
    assert result["ok"] is True
    held = result["row"]
    assert held["status"] == "inactive"
    assert held["admin_hold"] is True
    assert visible_to_students(held) is False
    retry = apply_action(held, "activate")
    assert retry["ok"] is False
    assert held["status"] == "inactive"


@pytest.fixture
def lifecycle_database(test_session, monkeypatch):
    """Use an in-memory database; never touch the normal application DB."""
    monkeypatch.setattr(listings, "engine", test_session.bind)
    users = {
        1: {"id": 1, "role": "admin"},
        2: {"id": 2, "role": "landlord"},
        3: {"id": 3, "role": "landlord"},
    }
    monkeypatch.setattr(listings, "get_user", lambda user_id: users.get(user_id))

    def create(status="pending", **changes):
        data = {
            "landlord_id": 2,
            "title": "Lifecycle Test Flat",
            "area": "st_augustine",
            "price": 2500,
            "amenities": "wifi",
            "contact_phone": "555-0100",
            "contact_email": "landlord@example.com",
            "created_at": "2026-11-23T10:00:00+00:00",
            "status": status,
        }
        data.update(changes)
        listing = Listing(**data)
        test_session.add(listing)
        test_session.commit()
        test_session.refresh(listing)
        return listing.id

    def persisted(listing_id):
        with Session(test_session.bind) as session:
            obj = session.get(Listing, listing_id)
            assert obj is not None
            return obj.model_dump()

    return create, persisted


@pytest.mark.parametrize(
    "initial,action,actor_id,expected",
    [
        ("pending", "verify", 1, "approved"),
        ("pending", "provisionally_accept", 1, "provisional"),
        ("pending", "reject", 1, "rejected"),
        ("provisional", "verify", 1, "approved"),
        ("approved", "activate", 2, "active"),
        ("active", "deactivate", 2, "inactive"),
        ("active", "force_deactivate", 1, "inactive"),
        ("inactive", "activate", 2, "active"),
        ("rejected", "resubmit", 2, "pending"),
    ],
)
def test_valid_transitions_are_persisted(
    lifecycle_database, initial, action, actor_id, expected
):
    create, persisted = lifecycle_database
    listing_id = create(initial)
    result = listings.transition(actor_id, listing_id, action)
    assert result["ok"] is True
    assert result["listing"]["status"] == expected
    assert persisted(listing_id)["status"] == expected
    if action == "force_deactivate":
        assert persisted(listing_id)["admin_hold"] is True


@pytest.mark.parametrize(
    "initial,action,actor_id",
    [
        ("pending", "activate", 2),
        ("pending", "deactivate", 2),
        ("rejected", "verify", 1),
        ("approved", "reject", 1),
        ("provisional", "activate", 2),
        ("active", "resubmit", 2),
    ],
)
def test_invalid_transitions_do_not_change_database(
    lifecycle_database, initial, action, actor_id
):
    create, persisted = lifecycle_database
    listing_id = create(initial)
    before = persisted(listing_id)
    result = listings.transition(actor_id, listing_id, action)
    assert result["ok"] is False
    assert persisted(listing_id) == before


def test_full_workflow_is_persisted(lifecycle_database):
    create, persisted = lifecycle_database
    listing_id = create()
    for actor, action, expected in (
        (1, "verify", "approved"),
        (2, "activate", "active"),
        (2, "deactivate", "inactive"),
        (2, "activate", "active"),
    ):
        result = listings.transition(actor, listing_id, action)
        assert result["ok"] is True
        assert persisted(listing_id)["status"] == expected


def test_force_deactivation_hold_is_persisted(lifecycle_database):
    create, persisted = lifecycle_database
    listing_id = create("active")
    result = listings.transition(1, listing_id, "force_deactivate")
    assert result["ok"] is True
    assert persisted(listing_id)["admin_hold"] is True
    retry = listings.transition(2, listing_id, "activate")
    assert retry["ok"] is False
    assert persisted(listing_id)["status"] == "inactive"


def test_reverification_blocks_database_reactivation(lifecycle_database):
    create, persisted = lifecycle_database
    listing_id = create("inactive", requires_reverification=True)
    result = listings.transition(2, listing_id, "activate")
    assert result["ok"] is False
    assert persisted(listing_id)["status"] == "inactive"


def test_non_owner_cannot_change_listing(lifecycle_database):
    create, persisted = lifecycle_database
    listing_id = create("approved")
    result = listings.transition(3, listing_id, "activate")
    assert result["ok"] is False
    assert result["error"] == "not listing owner"
    assert persisted(listing_id)["status"] == "approved"