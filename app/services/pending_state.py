
"""Pending state for accommodation listing verification."""

from typing import Any

from app.services.listing_state import ListingState


class PendingState(ListingState):
    """A listing awaiting administrative verification."""

    def handle(
        self, listing: dict[str, Any], action: str
    ) -> str:
        """Return the next status for an allowed action."""

        if action == "verify":
            return "approved"

        if action == "provisionally_accept":
            return "provisional"

        if action == "reject":
            return "rejected"

        raise ValueError(
            f"Cannot perform '{action}' while listing is pending"
        )

    def is_visible(self) -> bool:
        """Pending listings are not visible to students."""
        return False
