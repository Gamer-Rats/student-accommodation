import pytest

from app.services.listing_state import ListingState


def test_interface_cannot_be_instantiated():
    with pytest.raises(TypeError):
        ListingState()


def test_concrete_state_implements_interface():
    class ExampleState(ListingState):
        def handle(self, listing, action):
            return "pending"

        def is_visible(self):
            return False

    state = ExampleState()

    assert state.handle({}, "submit") == "pending"
    assert state.is_visible() is False
