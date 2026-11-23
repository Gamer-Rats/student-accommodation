from abc import ABC, abstractmethod
from typing import Any

class ListingState(ABC):
    """Common interface for accommodation listing states."""

    @abstractmethod
    def handle(self, listing: dict[str, Any], action: str) -> str:
        """Return the next state or reject an invalid transition."""
        raise NotImplementedError

    @abstractmethod
    def is_visible(self) -> bool:
        """Return whether listings in this state may be visible."""
        raise NotImplementedError
