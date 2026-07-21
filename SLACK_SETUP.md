# Slack setup (one time, ~10 minutes)

The bot talks to Slack over **Socket Mode**, so you do **not** need a public URL
or any hosting — it runs from your laptop.

## 1. Create the app
1. Go to <https://api.slack.com/apps> → **Create New App** → **From scratch**.
2. Name it `Group-Order Bot`, pick your workspace.

## 2. Turn on Socket Mode
- **Settings → Socket Mode** → toggle **Enable Socket Mode** on.
- When prompted, create an **App-Level Token** with the `connections:write`
  scope. Copy it — it starts with `xapp-`. This is your `SLACK_APP_TOKEN`.

## 3. Add the permissions the bot needs
- **Features → OAuth & Permissions → Bot Token Scopes**, add:
  - `app_mentions:read`  — hear the @mention that opens an order
  - `chat:write`         — post messages
  - `channels:history`   — read thread replies in public channels
  - `groups:history`     — read thread replies in private channels
  - `reactions:write`    — ✅ each collected request
  - `users:read`         — show people's names in the preview

## 4. Subscribe to events
- **Features → Event Subscriptions** → **Enable Events** on.
- Under **Subscribe to bot events**, add:
  - `app_mention`
  - `message.channels`
  - `message.groups`

## 5. Install & grab the bot token
- **Settings → Install App** → **Install to Workspace** → allow.
- Copy the **Bot User OAuth Token** — it starts with `xoxb-`. This is your
  `SLACK_BOT_TOKEN`.

## 6. Run it
```bash
pip install -r requirements.txt
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_APP_TOKEN=xapp-...
python slack_app.py
```

## 7. Use it
In any channel the bot is in (invite it with `/invite @Group-Order Bot`):

1. Type `@Group-Order Bot` — the bot opens an order and replies in a thread.
2. Everyone **replies in that thread** with what they want, in plain language.
3. Click **Preview & Price** — the bot builds one shared cart and shows the total.
4. Click **Place order** — this is the human "yes." Nothing is charged before it.

Still in **demo mode** (fake restaurants) until `dd-cli` is approved. To go live
later, the only change is `export GOB_MODE=live` (plus `GOB_ALLOW_REAL_ORDERS=1`
to actually spend) — same switch as the CLI demo.
