
"""Rejected state for accommodation listings requiring correction."""

from typing import Any

from app.services.listing_state import ListingState


class RejectedState(ListingState):
    """A rejected listing awaiting correction and resubmission."""

    def handle(
        self, listing: dict[str, Any], action: str
    ) -> str:
        """Allow resubmission; reject other transitions."""

        if action == "resubmit":
            return "pending"

        raise ValueError(
            f"Cannot perform '{action}' while listing is rejected"
        )

    def is_visible(self) -> bool:
        """Rejected listings are never visible to students."""
        return False
