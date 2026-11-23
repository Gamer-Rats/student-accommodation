
"""Listing lifecycle operations using the State Design Pattern."""

from typing import Any

from app.services.listing_lifecycle import ListingLifecycle
from app.services.listing_state import ListingState
from app.services.pending_state import PendingState
from app.services.provisional_state import ProvisionalState
from app.services.approved_state import ApprovedState
from app.services.active_state import ActiveState
from app.services.inactive_state import InactiveState
from app.services.rejected_state import RejectedState


ACTIONS = (
    "verify",
    "provisionally_accept",
    "reject",
    "activate",
    "deactivate",
    "force_deactivate",
    "resubmit",
)


STATES: dict[str, ListingState] = {
    "pending": PendingState(),
    "provisional": ProvisionalState(),
    "approved": ApprovedState(),
    "active": ActiveState(),
    "inactive": InactiveState(),
    "rejected": RejectedState(),
}


def snapshot(listing: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the current listing data."""
    return dict(listing)


def apply_action(
    listing: dict[str, Any],
    action: str,
) -> dict[str, Any]:
    """Perform a listing transition using the State Pattern."""

    if action not in ACTIONS:
        return {
            "ok": False,
            "error": f"unknown action {action!r}",
        }

    try:
        # Activation must respect administrative restrictions.
        if action == "activate":
            if listing.get("admin_hold", False):
                raise ValueError(
                    "Cannot activate a listing under administrative hold"
                )

            if listing.get("requires_reverification", False):
                raise ValueError(
                    "Cannot activate a listing requiring reverification"
                )

        lifecycle = ListingLifecycle(listing, STATES)
        lifecycle.transition(action)

        updated = snapshot(lifecycle.listing)

        # Forced deactivation places the listing on hold.
        if action == "force_deactivate":
            updated["admin_hold"] = True

        return {
            "ok": True,
            "listing": updated,
            "row": updated,
            "changed": True,
        }

    except (ValueError, KeyError) as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def visible_to_students(listing: dict[str, Any]) -> bool:
    """Determine visibility using the current state object."""

    try:
        lifecycle = ListingLifecycle(listing, STATES)
        return lifecycle.is_visible()
    except (ValueError, KeyError):
        return False
