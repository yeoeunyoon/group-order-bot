"""Demo-mode backend: fake but realistic DoorDash data.

This is what lets the whole app run today, before dd-cli access is approved.
Nothing here touches the network or any real money. When you go live, the app
stops calling this file and calls real.py instead — see factory.py.
"""

import itertools

from .base import DDClient
from .models import Cart, MenuItem, OrderResult, Store

# A tiny pretend universe of nearby stores.
_CATALOG: list[Store] = [
    Store(
        id="store_ippudo",
        name="Ippudo Ramen",
        cuisine="ramen japanese noodles",
        eta_minutes=32,
        delivery_fee_cents=399,
        menu=[
            MenuItem("i1", "Tonkotsu Ramen", 1650, "Pork broth, chashu, egg"),
            MenuItem("i2", "Spicy Miso Ramen", 1750, "Miso broth with chili"),
            MenuItem("i3", "Veggie Ramen", 1550, "Mushroom broth, tofu"),
            MenuItem("i4", "Pork Gyoza", 850, "Six pan-fried dumplings"),
        ],
    ),
    Store(
        id="store_chipotle",
        name="Chipotle",
        cuisine="mexican burrito tacos bowl",
        eta_minutes=24,
        delivery_fee_cents=299,
        menu=[
            MenuItem("c1", "Chicken Burrito", 1195, "Flour tortilla, rice, beans"),
            MenuItem("c2", "Steak Bowl", 1395, "No tortilla, extra steak"),
            MenuItem("c3", "Veggie Tacos", 995, "Three soft tacos, fajita veg"),
            MenuItem("c4", "Chips & Guac", 495, "Fresh guacamole"),
        ],
    ),
    Store(
        id="store_sweetgreen",
        name="Sweetgreen",
        cuisine="salad healthy bowl vegetarian",
        eta_minutes=19,
        delivery_fee_cents=349,
        menu=[
            MenuItem("s1", "Harvest Bowl", 1345, "Chicken, sweet potato, wild rice"),
            MenuItem("s2", "Kale Caesar Salad", 1145, "Kale, parmesan, croutons"),
            MenuItem("s3", "Guacamole Greens", 1245, "Avocado, tomato, greens"),
        ],
    ),
]

_order_counter = itertools.count(1001)


class MockDDClient(DDClient):
    def search_stores(self, query: str) -> list[Store]:
        q = query.lower()
        words = {w for w in q.replace(",", " ").split() if len(w) > 2}
        scored = []
        for store in _CATALOG:
            haystack = f"{store.name} {store.cuisine}".lower()
            score = sum(1 for w in words if w in haystack)
            scored.append((score, store))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        # If nothing matched at all, just return everything (like a broad search).
        if scored and scored[0][0] == 0:
            return list(_CATALOG)
        return [store for score, store in scored if score > 0]

    def get_menu(self, store_id: str) -> Store:
        for store in _CATALOG:
            if store.id == store_id:
                return store
        raise KeyError(f"unknown store: {store_id}")

    def checkout(self, cart: Cart) -> OrderResult:
        return OrderResult(
            order_id=f"MOCK-{next(_order_counter)}",
            status="placed",
            total_cents=cart.total_cents,
            eta_minutes=cart.store.eta_minutes,
        )
