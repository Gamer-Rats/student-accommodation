
import pytest

from app.services.provisional_state import ProvisionalState
from app.services.listing_lifecycle import ListingLifecycle
from app.services.listing_state import ListingState


class FakeApprovedState(ListingState):
    def handle(self, listing, action):
        raise ValueError("Invalid transition")

    def is_visible(self):
        return False


def test_provisional_can_be_verified():
    state = ProvisionalState()

    result = state.handle(
        {"id": 1, "status": "provisional"}, "verify"
    )

    assert result == "approved"


@pytest.mark.parametrize(
    "action",
    [
        "activate",
        "deactivate",
        "resubmit",
        "submit",
        "provisionally_accept",
        "reject",
        "unknown",
    ],
)
def test_provisional_rejects_invalid_transitions(action):
    state = ProvisionalState()

    with pytest.raises(
        ValueError, match="while listing is provisional"
    ):
        state.handle(
            {"id": 1, "status": "provisional"}, action
        )


def test_provisional_is_hidden():
    state = ProvisionalState()

    assert state.is_visible() is False


def test_valid_transition_updates_context():
    lifecycle = ListingLifecycle(
        {"id": 1, "status": "provisional"},
        {
            "provisional": ProvisionalState(),
            "approved": FakeApprovedState(),
        },
    )

    lifecycle.transition("verify")

    assert lifecycle.listing["status"] == "approved"
    assert isinstance(
        lifecycle.current_state, FakeApprovedState
    )


def test_invalid_transition_preserves_context():
    lifecycle = ListingLifecycle(
        {"id": 1, "status": "provisional"},
        {
            "provisional": ProvisionalState(),
            "approved": FakeApprovedState(),
        },
    )

    with pytest.raises(ValueError):
        lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "provisional"
    assert isinstance(
        lifecycle.current_state, ProvisionalState
    )
