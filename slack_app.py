"""Slack front end for Group-Order Bot.

This is the "microphone and speaker" — it turns a real Slack thread into the
same flow demo.py plays out on fake data. The ordering brain and the safety
guardrail live in bot/ and ddcli/ and are NOT touched here; this file only:

    - listens for @mentions to OPEN an order,
    - collects thread replies as each person's request,
    - runs plan() + prepare() and posts a preview when someone clicks a button,
    - and calls confirm() + checkout() ONLY when a human clicks "Place order".

Mode (demo vs. live) is inherited from config.py exactly like the CLI demo, so
this bot spends no real money until dd-cli is approved and GOB_MODE=live.

Run it:
    pip install -r requirements.txt
    export SLACK_BOT_TOKEN=xoxb-...     # Bot User OAuth Token
    export SLACK_APP_TOKEN=xapp-...     # App-Level Token (Socket Mode)
    python slack_app.py

See SLACK_SETUP.md for the one-time Slack app configuration.
"""

import logging
import os

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

import config
from bot import OrderSession
from ddcli import DDCliError, GuardrailError, get_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("group-order-bot.slack")

# token_verification_enabled=False lets the app be constructed (and imported for
# tests) without a live network call; the real credentials are still verified
# when SocketModeHandler.start() opens the connection.
app = App(
    # A placeholder keeps construction (and offline import for tests) working
    # when no token is set; main() requires the real one before connecting.
    token=os.environ.get("SLACK_BOT_TOKEN") or "xoxb-placeholder-not-set",
    token_verification_enabled=False,
)

# One live order per thread. Key = the thread's root timestamp (its id).
SESSIONS: dict[str, OrderSession] = {}

# Cache Slack user id -> display name so we don't call users_info repeatedly.
_NAME_CACHE: dict[str, str] = {}


def display_name(client, user_id: str) -> str:
    """A human-friendly name for a Slack user id, cached."""
    if user_id in _NAME_CACHE:
        return _NAME_CACHE[user_id]
    try:
        info = client.users_info(user=user_id)["user"]
        prof = info.get("profile", {})
        name = prof.get("display_name") or prof.get("real_name") or info.get("name")
    except Exception:  # noqa: BLE001 — a name lookup must never break an order
        name = user_id
    _NAME_CACHE[user_id] = name
    return name


def new_session() -> OrderSession:
    return OrderSession(
        client=get_client(),
        spend_limit_cents=config.SPEND_LIMIT_CENTS,
        tip_cents=config.TIP_CENTS,
    )


# --- 1. @mention opens an order --------------------------------------------
@app.event("app_mention")
def open_order(event, say):
    thread_ts = event["ts"]  # replies to this message become the order's requests
    SESSIONS[thread_ts] = new_session()
    limit = config.SPEND_LIMIT_CENTS / 100
    say(
        thread_ts=thread_ts,
        text=(
            f":shopping_trolley: *Order open!*  (mode: {config.MODE}, "
            f"limit: ${limit:,.2f})\n"
            "Reply in this thread with what you want — plain language is fine, "
            'e.g. "chicken burrito, no onions".\n'
            "When everyone's in, click *Preview & Price*."
        ),
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": (
                f":shopping_trolley: *Order open!*  _(mode: {config.MODE}, "
                f"limit: ${limit:,.2f})_\n"
                "Reply in this thread with what you want — plain language is "
                'fine, e.g. "chicken burrito, no onions".'
            )}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text",
                 "text": "Preview & Price"}, "style": "primary",
                 "action_id": "preview", "value": thread_ts},
                {"type": "button", "text": {"type": "plain_text",
                 "text": "Cancel"}, "action_id": "cancel", "value": thread_ts},
            ]},
        ],
    )


# --- 2. thread replies are collected as requests ---------------------------
@app.event("message")
def collect_reply(event, client):
    if event.get("bot_id") or event.get("subtype"):
        return  # ignore the bot's own posts and edits/joins/etc.
    thread_ts = event.get("thread_ts")
    if not thread_ts or thread_ts not in SESSIONS:
        return  # not a reply to an open order
    text = (event.get("text") or "").strip()
    if not text:
        return
    person = display_name(client, event["user"])
    SESSIONS[thread_ts].collect(person, text)
    client.reactions_add(
        channel=event["channel"], timestamp=event["ts"], name="white_check_mark"
    )


# --- 3. "Preview & Price" -> plan() + prepare() + preview() ------------------
@app.action("preview")
def do_preview(ack, body, say, client):
    ack()
    thread_ts = body["actions"][0]["value"]
    session = SESSIONS.get(thread_ts)
    if session is None:
        return
    if not session.requests:
        say(thread_ts=thread_ts, text="Nobody's ordered yet — reply with a request first.")
        return
    try:
        session.plan()
        session.prepare()
    except (DDCliError, GuardrailError) as exc:
        say(thread_ts=thread_ts, text=f":raised_hand: Stopped before any charge: {exc}")
        return

    say(
        thread_ts=thread_ts,
        text="Order preview",
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn",
             "text": f"```{session.preview()}```"}},
            {"type": "section", "text": {"type": "mrkdwn",
             "text": "*Nothing is ordered yet.* A human has to click below."}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text",
                 "text": "Place order"}, "style": "primary",
                 "action_id": "place", "value": thread_ts},
                {"type": "button", "text": {"type": "plain_text",
                 "text": "Cancel"}, "action_id": "cancel", "value": thread_ts},
            ]},
        ],
    )


# --- 4. "Place order" is the human YES -> confirm() + checkout() -------------
@app.action("place")
def do_place(ack, body, say, client):
    ack()
    thread_ts = body["actions"][0]["value"]
    session = SESSIONS.get(thread_ts)
    if session is None:
        return
    who = display_name(client, body["user"]["id"])
    session.confirm()  # a real person clicked the button — this is the human yes
    try:
        result = session.checkout()
    except (GuardrailError, DDCliError) as exc:
        say(thread_ts=thread_ts, text=f":shield: Blocked: {exc}")
        return
    SESSIONS.pop(thread_ts, None)
    eta = f", ETA {result.eta_text}" if result.eta_text else ""
    say(
        thread_ts=thread_ts,
        text=(f":white_check_mark: *{who} placed the order!*  "
              f"#{result.order_id} — {result.total_display}, "
              f"status: {result.status}{eta} :motor_scooter:"),
    )


# --- 5. Cancel --------------------------------------------------------------
@app.action("cancel")
def do_cancel(ack, body, say):
    ack()
    thread_ts = body["actions"][0]["value"]
    if SESSIONS.pop(thread_ts, None) is not None:
        say(thread_ts=thread_ts, text=":x: Order cancelled. No money spent.")


def main() -> None:
    missing = [v for v in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN") if not os.environ.get(v)]
    if missing:
        raise SystemExit(
            f"Missing {' and '.join(missing)}. See SLACK_SETUP.md — export the "
            "xoxb- (bot) and xapp- (app-level) tokens, then run again."
        )
    log.info("Group-Order Bot (Slack) starting — mode=%s", config.MODE)
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
