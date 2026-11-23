
"""Inactive state for unavailable accommodation listings."""

from typing import Any

from app.services.listing_state import ListingState


class InactiveState(ListingState):
    """An unavailable listing that may require verification before reactivation."""

    def handle(
        self, listing: dict[str, Any], action: str
    ) -> str:
        """Return the next status if reactivation is permitted."""

        if action == "activate":
            if listing.get("admin_hold", False):
                raise ValueError(
                    "Cannot activate a listing under administrative hold"
                )

            if listing.get("requires_reverification", False):
                raise ValueError(
                    "Cannot activate a listing requiring reverification"
                )

            return "active"

        raise ValueError(
            f"Cannot perform '{action}' while listing is inactive"
        )

    def is_visible(self) -> bool:
        """Inactive listings must not be visible to students."""
        return False
