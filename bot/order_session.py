"""The coordinator: runs one group order from requests to a placed order.

The flow is staged so the safety gate can't be skipped:

    collect()  -> gather everyone's requests
    plan()     -> search, pick a store, build ONE shared cart (local)
    prepare()  -> price it via dd-cli `order preview` (NO charge) -> a Quote
    preview()  -> a human-readable summary of what WOULD be ordered + real total
    confirm()  -> a real person says yes (the only way to unlock checkout)
    checkout() -> place the order  [blocked unless confirmed AND under the limit]

checkout() refuses to run unless confirm() was called and the quoted total is
within the spending limit. In live mode there is ALSO a second latch inside the
backend (GOB_ALLOW_REAL_ORDERS) — so an agent can plan, price, and preview all
it wants, but cannot spend money without an explicit human yes.
"""

from dataclasses import dataclass

from bot import matcher
from ddcli.base import DDClient
from ddcli.errors import GuardrailError
from ddcli.models import Cart, CartLine, OrderResult, Quote, dollars


@dataclass
class Request:
    person: str
    text: str


class OrderSession:
    def __init__(self, client: DDClient, spend_limit_cents: int, tip_cents: int = 0):
        self.client = client
        self.spend_limit_cents = spend_limit_cents
        self.tip_cents = tip_cents
        self.requests: list[Request] = []
        self.cart: Cart | None = None
        self.quote: Quote | None = None
        self.unmatched: list[Request] = []
        self._confirmed = False

    # 1. collect -----------------------------------------------------------
    def collect(self, person: str, text: str) -> None:
        self.requests.append(Request(person, text))
        self._invalidate()

    # 2. plan --------------------------------------------------------------
    def plan(self) -> Cart:
        if not self.requests:
            raise ValueError("no requests collected yet")

        texts = [r.text for r in self.requests]
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
            options, unresolved = matcher.resolve_options(note, item)
            cart.lines.append(CartLine(
                req.person, req.text, item, note,
                selected_options=options, unresolved_note=unresolved,
            ))

        if not cart.lines:
            raise GuardrailError("Couldn't match any request to this store's menu.")

        self.cart = cart
        self._invalidate()
        return cart

    # 3. prepare (price it — no charge) ------------------------------------
    def prepare(self) -> Quote:
        if self.cart is None:
            raise ValueError("call plan() before prepare()")
        self.quote = self.client.prepare_order(self.cart)
        self._confirmed = False
        return self.quote

    # 4. preview -----------------------------------------------------------
    def preview(self) -> str:
        if self.cart is None or self.quote is None:
            raise ValueError("call plan() then prepare() before preview()")
        c, q = self.cart, self.quote
        eta = f"  (ETA {q.eta_text})" if q.eta_text else ""
        lines = [f"Order preview — {q.store_name}{eta}", ""]
        for line in c.lines:
            mods = ", ".join(o.name for o in line.selected_options)
            mods = f"  ({mods})" if mods else ""
            lines.append(f"  {line.person:<8} {line.item.name:<22}{mods}")
            if line.unresolved_note:
                lines.append(f"           ⚠ note not applied: \"{line.unresolved_note}\"")
        total = q.total_display or dollars(q.total_cents)
        lines += ["", f"  {'TOTAL (incl. fees & tax)':<24} {total:>10}"]
        if self.unmatched:
            lines.append("")
            lines.append("  ⚠ Couldn't match (left off the order):")
            for req in self.unmatched:
                lines.append(f"      {req.person}: \"{req.text}\"")
        over = self._over_limit()
        limit = dollars(self.spend_limit_cents)
        lines.append("")
        lines.append(
            f"  ⛔ Over the {limit} spending limit — checkout will be blocked."
            if over
            else f"  ✓ Within the {limit} spending limit."
        )
        return "\n".join(lines)

    # 5. confirm -----------------------------------------------------------
    def confirm(self) -> None:
        """A HUMAN calls this. The agent must never call it on its own."""
        if self.quote is None:
            raise ValueError("nothing to confirm — call prepare() first")
        self._confirmed = True

    # 6. checkout ----------------------------------------------------------
    def checkout(self) -> OrderResult:
        if self.quote is None:
            raise GuardrailError("Nothing to check out — no priced order.")
        if not self._confirmed:
            raise GuardrailError(
                "Checkout blocked: no human confirmation. Call confirm() first."
            )
        if self._over_limit():
            raise GuardrailError(
                f"Checkout blocked: total {self.quote.total_display or dollars(self.quote.total_cents)} "
                f"exceeds the {dollars(self.spend_limit_cents)} spending limit."
            )
        return self.client.place_order(self.quote, tip_cents=self.tip_cents)

    # helpers --------------------------------------------------------------
    def _over_limit(self) -> bool:
        # total_cents can be 0 if a live total couldn't be parsed; treat a
        # positive total over the limit as the block condition.
        return bool(self.quote and self.quote.total_cents > self.spend_limit_cents)

    def _invalidate(self) -> None:
        # Any change to the order voids a prior price and confirmation.
        self.quote = None
        self._confirmed = False
