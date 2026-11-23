
import pytest

from app.services.rejected_state import RejectedState
from app.services.pending_state import PendingState
from app.services.listing_lifecycle import ListingLifecycle


def make_lifecycle(status="rejected"):
    return ListingLifecycle(
        {"id": 1, "status": status},
        {
            "rejected": RejectedState(),
            "pending": PendingState(),
        },
    )


def test_rejected_can_be_resubmitted():
    state = RejectedState()

    result = state.handle(
        {"id": 1, "status": "rejected"},
        "resubmit",
    )

    assert result == "pending"


@pytest.mark.parametrize(
    "action",
    [
        "activate",
        "deactivate",
        "verify",
        "reject",
        "submit",
        "provisionally_accept",
        "force_deactivate",
        "unknown",
    ],
)
def test_rejected_rejects_invalid_actions(action):
    with pytest.raises(
        ValueError, match="while listing is rejected"
    ):
        RejectedState().handle(
            {"id": 1, "status": "rejected"},
            action,
        )


def test_rejected_is_hidden():
    assert RejectedState().is_visible() is False
    assert make_lifecycle().is_visible() is False


def test_resubmission_updates_context():
    lifecycle = make_lifecycle()

    lifecycle.transition("resubmit")

    assert lifecycle.listing["status"] == "pending"
    assert isinstance(lifecycle.current_state, PendingState)
    assert lifecycle.is_visible() is False


def test_invalid_transition_preserves_context():
    lifecycle = make_lifecycle()

    with pytest.raises(ValueError):
        lifecycle.transition("verify")

    assert lifecycle.listing["status"] == "rejected"
    assert isinstance(lifecycle.current_state, RejectedState)


def test_rejected_requires_resubmission_before_verification():
    lifecycle = make_lifecycle("pending")

    lifecycle.transition("reject")
    assert lifecycle.listing["status"] == "rejected"

    with pytest.raises(ValueError):
        lifecycle.transition("verify")

    lifecycle.transition("resubmit")
    assert lifecycle.listing["status"] == "pending"
