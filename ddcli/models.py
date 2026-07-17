"""Plain data shapes passed around the app.

These are deliberately simple containers — no DoorDash logic lives here, just
the nouns everyone agrees on: a Store, a MenuItem, a Cart, an OrderResult.
The mock backend and the real dd-cli backend both produce these same shapes,
which is what lets the rest of the app not care which one is running.
"""

from dataclasses import dataclass, field


def dollars(cents: int) -> str:
    """Format a cents amount as $X.XX for humans."""
    return f"${cents / 100:,.2f}"


@dataclass
class MenuItem:
    id: str
    name: str
    price_cents: int
    description: str = ""


@dataclass
class Store:
    id: str
    name: str
    cuisine: str
    eta_minutes: int
    delivery_fee_cents: int
    menu: list[MenuItem] = field(default_factory=list)


@dataclass
class CartLine:
    person: str          # who asked for it
    request: str         # the raw human text, e.g. "chicken burrito, no onions"
    item: MenuItem       # the real menu item it was matched to
    note: str = ""       # special instructions pulled from the request


@dataclass
class Cart:
    store: Store
    lines: list[CartLine] = field(default_factory=list)

    @property
    def subtotal_cents(self) -> int:
        return sum(line.item.price_cents for line in self.lines)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.store.delivery_fee_cents


@dataclass
class OrderResult:
    order_id: str
    status: str          # e.g. "placed", "confirmed"
    total_cents: int
    eta_minutes: int
