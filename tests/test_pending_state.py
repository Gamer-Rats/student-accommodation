
import pytest

from app.services.pending_state import PendingState
from app.services.listing_lifecycle import ListingLifecycle


@pytest.mark.parametrize(
    "action, expected",
    [
        ("verify", "approved"),
        ("provisionally_accept", "provisional"),
        ("reject", "rejected"),
    ],
)
def test_pending_review_transitions(action, expected):
    state = PendingState()

    result = state.handle(
        {"id": 1, "status": "pending"}, action
    )

    assert result == expected


@pytest.mark.parametrize(
    "action",
    [
        "activate",
        "deactivate",
        "resubmit",
        "submit",
        "unknown",
    ],
)
def test_pending_rejects_invalid_transitions(action):
    state = PendingState()

    with pytest.raises(
        ValueError, match="while listing is pending"
    ):
        state.handle(
            {"id": 1, "status": "pending"}, action
        )


def test_pending_is_hidden():
    state = PendingState()

    assert state.is_visible() is False


def test_invalid_transition_does_not_change_context():
    lifecycle = ListingLifecycle(
        {"id": 1, "status": "pending"},
        {"pending": PendingState()},
    )

    with pytest.raises(ValueError):
        lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "pending"
    assert isinstance(lifecycle.current_state, PendingState)
