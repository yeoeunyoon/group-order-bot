"""The contract every backend must satisfy.

There are two backends:
  - MockDDClient  (demo mode)  — invents data, prices locally, pretends to submit
  - RealDDClient  (live mode)  — shells out to the real `dd-cli`

Both promise the same methods below, returning the same shapes from models.py.
The bot talks to this interface and never knows which one it got.

The order is deliberately split so pricing (no charge) is separate from
placing (charges money):

    search_stores -> get_menu -> prepare_order (price, no charge) -> place_order (CHARGES)
"""

from abc import ABC, abstractmethod

from .models import Cart, OrderResult, Quote, Store


class DDClient(ABC):
    @abstractmethod
    def search_stores(
        self, query: str, lat: float | None = None,
        lng: float | None = None, limit: int = 5,
    ) -> list[Store]:
        """Find restaurants matching a free-text query like 'ramen near me'."""

    @abstractmethod
    def get_menu(self, store_id: str) -> Store:
        """Return the store with its menu and menu_id populated."""

    @abstractmethod
    def prepare_order(self, cart: Cart) -> Quote:
        """Build the order and price it. NO money changes hands here."""

    @abstractmethod
    def place_order(self, quote: Quote, tip_cents: int = 0) -> OrderResult:
        """Place the order. CHARGES money. Only reached after the confirm gate."""
