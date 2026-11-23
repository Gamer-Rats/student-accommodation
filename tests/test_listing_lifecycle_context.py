import pytest

from app.services.listing_lifecycle import ListingLifecycle
from app.services.listing_state import ListingState


class FakePendingState(ListingState):
    def handle(self, listing, action):
        if action == "verify":
            return "approved"
        raise ValueError("Invalid transition")

    def is_visible(self):
        return False


class FakeApprovedState(ListingState):
    def handle(self, listing, action):
        raise ValueError("Invalid transition")

    def is_visible(self):
        return False


class FakeActiveState(ListingState):
    def handle(self, listing, action):
        raise ValueError("Invalid transition")

    def is_visible(self):
        return True


def make_context(status="pending", **extra):
    listing = {"id": 1, "status": status, **extra}

    states = {
        "pending": FakePendingState(),
        "approved": FakeApprovedState(),
        "active": FakeActiveState(),
    }

    return ListingLifecycle(listing, states)


def test_delegates_valid_transition():
    lifecycle = make_context()

    result = lifecycle.transition("verify")

    assert isinstance(result, FakeApprovedState)
    assert lifecycle.listing["status"] == "approved"


def test_invalid_transition_preserves_status():
    lifecycle = make_context()

    with pytest.raises(ValueError, match="Invalid transition"):
        lifecycle.transition("activate")

    assert lifecycle.listing["status"] == "pending"
    assert isinstance(lifecycle.current_state, FakePendingState)


def test_visibility_respects_state_and_holds():
    assert make_context("active").is_visible()
    assert not make_context("pending").is_visible()

    assert not make_context(
        "active", admin_hold=True
    ).is_visible()

    assert not make_context(
        "active", requires_reverification=True
    ).is_visible()


def test_unknown_status_rejected():
    with pytest.raises(ValueError, match="Unknown listing state"):
        make_context("missing")