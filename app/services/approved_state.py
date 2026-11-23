from typing import Any
from app.services.listing_state import ListingState

class ApprovedState(ListingState):


    def handle(self, listing: dict[str, Any], action: str) -> str:
   
        if action == "activate":
            return "active"

        raise ValueError(  f"Cannot perform '{action}' while listing is approved")

    def is_visible(self) -> bool:
        return False
