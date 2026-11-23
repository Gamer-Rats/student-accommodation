from typing import Any
from app.services.listing_state import ListingState

class ActiveState(ListingState):

    def handle(self, listing: dict[str, Any], action: str) -> str:

        if action in ("deactivate", "force_deactivate"):
            return "inactive"

        raise ValueError(
            f"Cannot perform '{action}' while listing is active"
        )

    def is_visible(self) -> bool:
        return True
