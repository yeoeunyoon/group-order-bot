"""Drive the Slack handlers directly with fakes — no Slack connection, demo mode.

Confirms the front end wires a whole thread (open -> replies -> preview -> place)
to the engine correctly, including that the button click is what confirms.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import slack_app


class FakeSay:
    def __init__(self):
        self.msgs = []

    def __call__(self, **kwargs):
        self.msgs.append(kwargs)

    def texts(self):
        return " ".join(m.get("text", "") for m in self.msgs)


class FakeClient:
    def reactions_add(self, **kwargs):
        pass

    def users_info(self, user):
        return {"user": {"name": user, "profile": {"display_name": user}}}


def _ack():
    pass


def setup_function(_):
    slack_app.SESSIONS.clear()
    slack_app.QUERIES.clear()


def test_full_thread_flow_places_order():
    say = FakeSay()
    client = FakeClient()

    slack_app.open_order({"ts": "T1", "text": "<@U0> sushi"}, say)
    assert "T1" in slack_app.SESSIONS
    assert slack_app.QUERIES["T1"] == "sushi"

    slack_app.collect_reply(
        {"thread_ts": "T1", "ts": "m1", "user": "U1", "text": "chicken burrito", "channel": "C"},
        client,
    )
    slack_app.collect_reply(
        {"thread_ts": "T1", "ts": "m2", "user": "U2", "text": "steak bowl", "channel": "C"},
        client,
    )
    assert len(slack_app.SESSIONS["T1"].requests) == 2

    slack_app.do_preview(_ack, {"actions": [{"value": "T1"}]}, say, client)
    assert slack_app.SESSIONS["T1"].quote is not None

    slack_app.do_place(_ack, {"actions": [{"value": "T1"}], "user": {"id": "U1"}}, say, client)
    assert "T1" not in slack_app.SESSIONS  # order finished, thread cleared
    assert "placed the order" in say.texts()


def test_replies_outside_an_open_thread_are_ignored():
    client = FakeClient()
    # No session for T9 -> reply must not raise or create anything.
    slack_app.collect_reply(
        {"thread_ts": "T9", "ts": "m1", "user": "U1", "text": "hi", "channel": "C"},
        client,
    )
    assert slack_app.SESSIONS == {}


def test_preview_with_no_requests_prompts_and_does_not_crash():
    say = FakeSay()
    client = FakeClient()
    slack_app.open_order({"ts": "T2", "text": "<@U0>"}, say)
    slack_app.do_preview(_ack, {"actions": [{"value": "T2"}]}, say, client)
    assert "ordered yet" in say.texts()


def test_cancel_clears_the_thread():
    say = FakeSay()
    slack_app.open_order({"ts": "T3", "text": "<@U0> pizza"}, say)
    slack_app.do_cancel(_ack, {"actions": [{"value": "T3"}]}, say)
    assert "T3" not in slack_app.SESSIONS
    assert "T3" not in slack_app.QUERIES
