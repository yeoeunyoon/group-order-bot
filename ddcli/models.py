"""Plain data shapes passed around the app.

These are deliberately simple containers — no DoorDash logic lives here, just
the nouns everyone agrees on: a Store, a MenuItem, a Cart, a Quote, an
OrderResult. The mock backend and the real dd-cli backend both produce these
same shapes, which is what lets the rest of the app not care which one runs.
"""

from dataclasses import dataclass, field


def dollars(cents: int) -> str:
    """Format a cents amount as $X.XX for humans."""
    return f"${cents / 100:,.2f}"


@dataclass
class ModifierOption:
    """A customization choice on a menu item (dd-cli nested_options entry)."""
    id: str              # real dd-cli option id
    name: str            # e.g. "No Onions", "Extra Guac"
    price_cents: int = 0


@dataclass
class MenuItem:
    id: str              # real dd-cli item_id, e.g. "23266866023"
    name: str
    price_cents: int
    description: str = ""
    options: list["ModifierOption"] = field(default_factory=list)


@dataclass
class Store:
    id: str              # real dd-cli store_id, e.g. "928163"
    name: str
    cuisine: str
    eta_minutes: int
    delivery_fee_cents: int
    menu: list[MenuItem] = field(default_factory=list)
    menu_id: str = ""    # real dd-cli menu_id, needed to add items to a cart


@dataclass
class CartLine:
    person: str          # who asked for it
    request: str         # the raw human text, e.g. "chicken burrito, no onions"
    item: MenuItem       # the real menu item it was matched to
    note: str = ""       # special instructions pulled from the request
    selected_options: list["ModifierOption"] = field(default_factory=list)
    unresolved_note: str = ""  # note text we could NOT map to a real modifier

    @property
    def line_cents(self) -> int:
        return self.item.price_cents + sum(o.price_cents for o in self.selected_options)


@dataclass
class Cart:
    store: Store
    lines: list[CartLine] = field(default_factory=list)

    @property
    def subtotal_cents(self) -> int:
        return sum(line.line_cents for line in self.lines)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.store.delivery_fee_cents


@dataclass
class Quote:
    """The result of pricing a cart WITHOUT charging (dd-cli `order preview`).

    `handle` is the thing the checkout step needs to place the order — the
    real cart_uuid in live mode, a fake id in demo mode. `total_cents` /
    `total_display` are the authoritative numbers a human confirms against.
    """
    handle: str
    store_name: str
    total_cents: int     # authoritative total incl. fees/taxes (best-effort in live)
    total_display: str   # currency-formatted total straight from DoorDash
    eta_text: str = ""
    raw: dict | None = None  # the full preview JSON, for reference/debugging


@dataclass
class OrderResult:
    order_id: str
    status: str          # e.g. "placed", "pending", "confirmed"
    total_cents: int
    total_display: str
    eta_text: str = ""
