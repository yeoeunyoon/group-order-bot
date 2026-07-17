"""The contract every backend must satisfy.

There are two backends:
  - MockDDClient  (demo mode)  — invents data, pretends to check out
  - RealDDClient  (live mode)  — shells out to the real `dd-cli`

Both promise the same four methods below, returning the same shapes from
models.py. The bot talks to this interface and never knows which one it got.
"""

from abc import ABC, abstractmethod

from .models import Cart, OrderResult, Store


class DDClient(ABC):
    @abstractmethod
    def search_stores(self, query: str) -> list[Store]:
        """Find stores matching a free-text query like 'ramen near me'."""

    @abstractmethod
    def get_menu(self, store_id: str) -> Store:
        """Return the full store with its menu populated."""

    @abstractmethod
    def checkout(self, cart: Cart) -> OrderResult:
        """Place the order. Only ever reached after the confirm gate passes."""
