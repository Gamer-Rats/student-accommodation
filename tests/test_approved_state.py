
import pytest

from app.services.approved_state import ApprovedState
from app.services.listing_lifecycle import ListingLifecycle
from app.services.listing_state import ListingState


class FakeActiveState(ListingState):
    def handle(self, listing, action):
        raise ValueError("Invalid transition")

    def is_visible(self):
        return True


def test_approved_can_be_activated():
    state = ApprovedState()

    result = state.handle(
        {"id": 1, "status": "approved"}, "activate"
    )

    assert result == "active"


@pytest.mark.parametrize(
    "action",
    [
        "verify",
        "reject",
        "deactivate",
        "resubmit",
        "submit",
        "provisionally_accept",
        "unknown",
    ],
)
def test_approved_rejects_invalid_actions(action):
    state = ApprovedState()

    with pytest.raises(
        ValueError, match="while listing is approved"
    ):
        state.handle(
            {"id": 1, "status": "approved"}, action
        )


def test_approved_is_hidden():
    state = ApprovedState()

    assert state.is_visible() is False


def test_valid_transition_updates_context():
    lifecycle = ListingLifecycle(
        {"id": 1, "status": "approved"},
        {
            "approved": ApprovedState(),
            "active": FakeActiveState(),
        },
    )

    lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "active"
    assert isinstance(
        lifecycle.current_state, FakeActiveState
    )


def test_invalid_transition_preserves_context():
    lifecycle = ListingLifecycle(
        {"id": 1, "status": "approved"},
        {
            "approved": ApprovedState(),
            "active": FakeActiveState(),
        },
    )

    with pytest.raises(ValueError):
        lifecycle.transition("deactivate")

    assert lifecycle.listing["status"] == "approved"
    assert isinstance(
        lifecycle.current_state, ApprovedState
    )
