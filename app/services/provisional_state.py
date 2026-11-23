
"""Provisional state for accommodation listing verification."""

from typing import Any

from app.services.listing_state import ListingState


class ProvisionalState(ListingState):
    """A listing requiring further administrative verification."""

    def handle(
        self, listing: dict[str, Any], action: str
    ) -> str:
        """Return the next status for an allowed action."""

        if action == "verify":
            return "approved"

        raise ValueError(
            f"Cannot perform '{action}' while listing is provisional"
        )

    def is_visible(self) -> bool:
        """Provisional listings are not visible to students."""
        return False
