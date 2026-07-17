"""Turn messy human requests into real menu items and pick a store.

This is the 'brain' seam. Right now it's a simple, dependency-free keyword
matcher so the demo runs with no API key. When you want real intelligence,
swap KeywordMatcher for an AgentMatcher that asks Claude to do the same job
(read the requests, choose the store, map each request to a menu item) — the
rest of the app doesn't change, because it only depends on the two functions
below returning (item, note) and a chosen store.
"""

import re

from ddcli.models import MenuItem, Store

_STOPWORDS = {"a", "an", "the", "with", "and", "some", "please", "of", "for", "me"}
_NOTE_RE = re.compile(r"\b(no|without|extra|add)\b.*", re.IGNORECASE)


def extract_note(request: str) -> str:
    """Pull special instructions like 'no onions' or 'extra guac' out of a request."""
    match = _NOTE_RE.search(request)
    return match.group(0).strip() if match else ""


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def resolve_item(request: str, store: Store) -> tuple[MenuItem | None, str]:
    """Best-effort match of one request to one item on this store's menu."""
    note = extract_note(request)
    # Match on the words before any note phrase, so 'no onions' doesn't sway it.
    core = _NOTE_RE.sub("", request)
    wanted = _tokens(core)

    best_item, best_score = None, 0
    for item in store.menu:
        score = len(wanted & _tokens(item.name))
        if score > best_score:
            best_item, best_score = item, score
    return best_item, note


def choose_store(requests: list[str], stores: list[Store]) -> Store | None:
    """Pick the store that can satisfy the most people (ties: faster ETA)."""
    best_store, best_matched = None, -1
    for store in stores:
        matched = sum(1 for r in requests if resolve_item(r, store)[0] is not None)
        better = matched > best_matched or (
            matched == best_matched
            and best_store is not None
            and store.eta_minutes < best_store.eta_minutes
        )
        if better:
            best_store, best_matched = store, matched
    return best_store if best_matched > 0 else None
