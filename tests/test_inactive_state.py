
import pytest

from app.services.inactive_state import InactiveState
from app.services.active_state import ActiveState
from app.services.listing_lifecycle import ListingLifecycle


def make_lifecycle(**extra):
    return ListingLifecycle(
        {"id": 1, "status": "inactive", **extra},
        {
            "inactive": InactiveState(),
            "active": ActiveState(),
        },
    )


def test_inactive_can_be_activated():
    state = InactiveState()

    result = state.handle(
        {"id": 1, "status": "inactive"},
        "activate",
    )

    assert result == "active"


@pytest.mark.parametrize(
    "restriction",
    ["admin_hold", "requires_reverification"],
)
def test_inactive_cannot_activate_with_restrictions(restriction):
    state = InactiveState()

    listing = {
        "id": 1,
        "status": "inactive",
        restriction: True,
    }

    with pytest.raises(ValueError, match="Cannot activate"):
        state.handle(listing, "activate")


@pytest.mark.parametrize(
    "action",
    [
        "verify",
        "reject",
        "deactivate",
        "resubmit",
        "submit",
        "provisionally_accept",
        "force_deactivate",
        "unknown",
    ],
)
def test_inactive_rejects_invalid_actions(action):
    state = InactiveState()

    with pytest.raises(
        ValueError, match="while listing is inactive"
    ):
        state.handle(
            {"id": 1, "status": "inactive"},
            action,
        )


def test_inactive_is_hidden():
    assert InactiveState().is_visible() is False


def test_reactivation_updates_context():
    lifecycle = make_lifecycle()

    lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "active"
    assert isinstance(lifecycle.current_state, ActiveState)
    assert lifecycle.is_visible() is True


@pytest.mark.parametrize(
    "restriction",
    ["admin_hold", "requires_reverification"],
)
def test_blocked_reactivation_preserves_context(restriction):
    lifecycle = make_lifecycle(**{restriction: True})

    with pytest.raises(ValueError):
        lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "inactive"
    assert isinstance(lifecycle.current_state, InactiveState)
    assert lifecycle.is_visible() is False


def test_invalid_transition_preserves_context():
    lifecycle = make_lifecycle()

    with pytest.raises(ValueError):
        lifecycle.transition("verify")

    assert lifecycle.listing["status"] == "inactive"
    assert isinstance(lifecycle.current_state, InactiveState)
