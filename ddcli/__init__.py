"""The adapter layer: one interface, two interchangeable backends."""

from .base import DDClient
from .errors import DDCliError, GuardrailError
from .factory import get_client
from .models import Cart, CartLine, MenuItem, OrderResult, Quote, Store, dollars

__all__ = [
    "DDClient",
    "DDCliError",
    "GuardrailError",
    "get_client",
    "Cart",
    "CartLine",
    "MenuItem",
    "OrderResult",
    "Quote",
    "Store",
    "dollars",
]
