
import pytest

from app.services.active_state import ActiveState
from app.services.listing_lifecycle import ListingLifecycle
from app.services.listing_state import ListingState


class FakeInactiveState(ListingState):
    def handle(self, listing, action):
        raise ValueError("Invalid transition")

    def is_visible(self):
        return False


def make_lifecycle(**overrides):
    return ListingLifecycle(
        {"id": 1, "status": "active", **overrides},
        {
            "active": ActiveState(),
            "inactive": FakeInactiveState(),
        },
    )


@pytest.mark.parametrize(
    "action",
    ["deactivate", "force_deactivate"],
)
def test_active_can_be_deactivated(action):
    state = ActiveState()

    result = state.handle(
        {"id": 1, "status": "active"}, action
    )

    assert result == "inactive"


@pytest.mark.parametrize(
    "action",
    [
        "activate",
        "verify",
        "reject",
        "resubmit",
        "submit",
        "provisionally_accept",
        "unknown",
    ],
)
def test_active_rejects_invalid_actions(action):
    state = ActiveState()

    with pytest.raises(
        ValueError, match="while listing is active"
    ):
        state.handle(
            {"id": 1, "status": "active"}, action
        )


def test_active_state_is_visible():
    assert ActiveState().is_visible() is True


@pytest.mark.parametrize(
    "action",
    ["deactivate", "force_deactivate"],
)
def test_valid_transition_updates_context(action):
    lifecycle = make_lifecycle()

    lifecycle.transition(action)

    assert lifecycle.listing["status"] == "inactive"
    assert isinstance(
        lifecycle.current_state, FakeInactiveState
    )
    assert lifecycle.is_visible() is False


def test_invalid_transition_preserves_context():
    lifecycle = make_lifecycle()

    with pytest.raises(ValueError):
        lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "active"
    assert isinstance(
        lifecycle.current_state, ActiveState
    )


@pytest.mark.parametrize(
    "restriction",
    ["admin_hold", "requires_reverification"],
)
def test_visibility_respects_restrictions(restriction):
    lifecycle = make_lifecycle(**{restriction: True})

    assert lifecycle.is_visible() is False


def test_active_context_visible_without_restrictions():
    assert make_lifecycle().is_visible() is True
