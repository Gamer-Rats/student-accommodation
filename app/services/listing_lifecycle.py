"""State Pattern context for an accommodation listing."""

from typing import Any, Mapping

from app.services.listing_state import ListingState


class ListingLifecycle:
    def __init__(
        self,
        listing: dict[str, Any],
        states: Mapping[str, ListingState],
    ):
        self.listing = dict(listing)
        self.states = dict(states)
        self.current_state = self._get_state(self.listing["status"])

    def _get_state(self, status: str) -> ListingState:
        if status not in self.states:
            raise ValueError(f"Unknown listing state: {status}")

        return self.states[status]

    def transition(self, action: str) -> ListingState:
        """Process a transition through the current state."""

        next_status = self.current_state.handle(
            dict(self.listing), action
        )

        next_state = self._get_state(next_status)

        self.listing["status"] = next_status
        self.current_state = next_state

        return next_state

    def is_visible(self) -> bool:
        """Check whether the listing can be shown to students."""

        return (
            self.current_state.is_visible()
            and not self.listing.get("admin_hold", False)
            and not self.listing.get("requires_reverification", False)
        )