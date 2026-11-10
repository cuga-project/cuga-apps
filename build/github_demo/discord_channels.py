"""Create the demo's Discord channels with the bot's own token. Never prints the token.

  guilds                         list the servers the bot is in (id, name)
  setup GUILD_ID [--category N]  create (or reuse, by name) the three channels and print their ids:
                                   ask-cuga    people chat with CUGA (@mention it)
                                   cuga-watch  live GitHub feed — read-only for people
                                   cuga-news   daily report      — read-only for people

Read-only means a permission overwrite on @everyone that denies Send Messages (and thread
messages), plus an allow for the bot. The bot needs Manage Channels and Manage Roles in the server.

Token: DISCORD_BOT_TOKEN in the env (deploy.sh writes it to a mode-600 file and sources it).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
VIEW, SEND, EMBED, READ_HISTORY, ADD_REACTIONS = 1 << 10, 1 << 11, 1 << 14, 1 << 16, 1 << 6
SEND_IN_THREADS, CREATE_PUBLIC_THREADS, CREATE_PRIVATE_THREADS = 1 << 38, 1 << 35, 1 << 36
CHANNELS = [
    ("ask-cuga", False, "Ask CUGA about GitHub repos: @mention it. It can read, never change anything."),
    ("cuga-watch", True, "Live feed: CUGA posts when something happens on the watched GitHub repo."),
    ("cuga-news", True, "Daily report: CUGA posts the repo's activity every morning (09:00 EST)."),
]


def _call(method: str, path: str, body: dict | None = None):
    tok = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not tok:
        raise SystemExit("DISCORD_BOT_TOKEN is not set")
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bot {tok}", "Content-Type": "application/json",
                                          "User-Agent": "cuga-github-demo (https://github.com/cuga-project, 1)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Discord {method} {path}: HTTP {e.code} {e.read().decode()[:200]}")


def cmd_guilds() -> None:
    me = _call("GET", "/users/@me")
    print(f"bot: {me.get('username')} ({me.get('id')})")
    for g in _call("GET", "/users/@me/guilds"):
        print(f"{g['id']}  {g['name']}")


def cmd_setup(guild: str, *flags: str) -> None:
    category = flags[flags.index("--category") + 1] if "--category" in flags else None
    bot_id = _call("GET", "/users/@me")["id"]
    existing = {c["name"]: c for c in _call("GET", f"/guilds/{guild}/channels") if c.get("type") == 0}
    for name, read_only, topic in CHANNELS:
        overwrites = [{"id": bot_id, "type": 1, "allow": str(VIEW | SEND | EMBED | READ_HISTORY), "deny": "0"}]
        if read_only:
            deny = SEND | SEND_IN_THREADS | CREATE_PUBLIC_THREADS | CREATE_PRIVATE_THREADS
            overwrites.append({"id": guild, "type": 0, "allow": str(VIEW | READ_HISTORY | ADD_REACTIONS), "deny": str(deny)})
        if name in existing:
            ch = _call("PATCH", f"/channels/{existing[name]['id']}", {"topic": topic, "permission_overwrites": overwrites})
            how = "updated"
        else:
            body = {"name": name, "type": 0, "topic": topic, "permission_overwrites": overwrites}
            if category:
                body["parent_id"] = category
            ch = _call("POST", f"/guilds/{guild}/channels", body)
            how = "created"
        print(f"{name}: {ch['id']} ({how}{', read-only for people' if read_only else ''})")


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["-h"]
    fns = {"guilds": cmd_guilds, "setup": cmd_setup}
    if cmd not in fns:
        print(__doc__)
        sys.exit(2)
    fns[cmd](*args)
