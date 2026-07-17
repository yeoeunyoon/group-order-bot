"""The coordinator: runs one group order from requests to a placed order.

The flow is deliberately staged so the safety gate can't be skipped:

    collect()  -> gather everyone's requests
    plan()     -> search, pick a store, build ONE shared cart
    preview()  -> a human-readable summary of what WOULD be ordered
    confirm()  -> a real person says yes (this is the only way to unlock checkout)
    checkout() -> place the order  [blocked unless confirmed AND under the limit]

checkout() refuses to run unless confirm() was called and the total is within
the spending limit. That refusal is the whole safety story — an agent can plan
and preview all it wants, but it cannot spend money without a human yes.
"""

from dataclasses import dataclass

from bot import matcher
from ddcli.base import DDClient
from ddcli.errors import GuardrailError
from ddcli.models import Cart, CartLine, OrderResult, dollars


@dataclass
class Request:
    person: str
    text: str


class OrderSession:
    def __init__(self, client: DDClient, spend_limit_cents: int):
        self.client = client
        self.spend_limit_cents = spend_limit_cents
        self.requests: list[Request] = []
        self.cart: Cart | None = None
        self.unmatched: list[Request] = []
        self._confirmed = False

    # 1. collect -----------------------------------------------------------
    def collect(self, person: str, text: str) -> None:
        self.requests.append(Request(person, text))
        # Any change to the order invalidates a prior confirmation.
        self._confirmed = False

    # 2. plan --------------------------------------------------------------
    def plan(self) -> Cart:
        if not self.requests:
            raise ValueError("no requests collected yet")

        texts = [r.text for r in self.requests]
        # A broad search using everyone's words; the matcher picks the store.
        stores = self.client.search_stores(" ".join(texts))
        store = matcher.choose_store(texts, stores)
        if store is None:
            raise GuardrailError("No nearby store can satisfy these requests.")

        store = self.client.get_menu(store.id)
        cart = Cart(store=store)
        self.unmatched = []
        for req in self.requests:
            item, note = matcher.resolve_item(req.text, store)
            if item is None:
                self.unmatched.append(req)
                continue
            cart.lines.append(CartLine(req.person, req.text, item, note))

        self.cart = cart
        self._confirmed = False
        return cart

    # 3. preview -----------------------------------------------------------
    def preview(self) -> str:
        if self.cart is None:
            raise ValueError("call plan() before preview()")
        c = self.cart
        lines = [f"Order preview — {c.store.name}  (ETA ~{c.store.eta_minutes} min)", ""]
        for line in c.lines:
            note = f"  ·  {line.note}" if line.note else ""
            lines.append(
                f"  {line.person:<8} {line.item.name:<22} "
                f"{dollars(line.item.price_cents):>8}{note}"
            )
        lines += [
            "",
            f"  {'Subtotal':<31}{dollars(c.subtotal_cents):>8}",
            f"  {'Delivery':<31}{dollars(c.store.delivery_fee_cents):>8}",
            f"  {'TOTAL':<31}{dollars(c.total_cents):>8}",
        ]
        if self.unmatched:
            lines.append("")
            lines.append("  ⚠ Couldn't match (left off the order):")
            for req in self.unmatched:
                lines.append(f"      {req.person}: \"{req.text}\"")
        over = c.total_cents > self.spend_limit_cents
        limit = dollars(self.spend_limit_cents)
        lines.append("")
        lines.append(
            f"  ⛔ Over the {limit} spending limit — checkout will be blocked."
            if over
            else f"  ✓ Within the {limit} spending limit."
        )
        return "\n".join(lines)

    # 4. confirm -----------------------------------------------------------
    def confirm(self) -> None:
        """A HUMAN calls this. The agent must never call it on its own."""
        if self.cart is None:
            raise ValueError("nothing to confirm — call plan() first")
        self._confirmed = True

    # 5. checkout ----------------------------------------------------------
    def checkout(self) -> OrderResult:
        if self.cart is None:
            raise GuardrailError("Nothing to check out — no cart has been planned.")
        if not self._confirmed:
            raise GuardrailError(
                "Checkout blocked: no human confirmation. Call confirm() first."
            )
        if self.cart.total_cents > self.spend_limit_cents:
            raise GuardrailError(
                f"Checkout blocked: total {dollars(self.cart.total_cents)} exceeds "
                f"the {dollars(self.spend_limit_cents)} spending limit."
            )
        return self.client.checkout(self.cart)
