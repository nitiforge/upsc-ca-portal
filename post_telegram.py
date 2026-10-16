#!/usr/bin/env python3
"""Post new AI study notes to a Telegram channel or group (optional).

Needs two GitHub secrets: TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID
(@yourchannel, or a numeric id). The bot must be an admin of the channel.
Without them this script exits quietly. SITE_URL (optional) is linked in each post.

Safety: each note is posted once (state in telegram_state.json), at most TG_MAX_PER_RUN
per run. On the very first run only the newest TG_FIRST_RUN notes are posted, so an
existing backlog never floods the channel.
"""
import json, os, sys, time, html, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
NOTES = os.path.join(HERE, "auto_notes.json")
STATE = os.path.join(HERE, "telegram_state.json")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
SITE = os.environ.get("SITE_URL", "").strip()
MAX_RUN = int(os.environ.get("TG_MAX_PER_RUN", "5"))
FIRST_RUN = int(os.environ.get("TG_FIRST_RUN", "3"))


class Stop(Exception):
    pass


def load(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def e(x):
    return html.escape(str(x or ""), quote=False)


def message(n):
    key = "\n".join("• " + e(k) for k in (n.get("key") or [])[:3])
    pre = (n.get("pre") or [""])[0]
    parts = ["<b>%s</b>" % e(n.get("title")),
             "%s · %s · %s" % (e(n.get("gs")), e(n.get("cat")), e(n.get("date"))), "",
             "<b>Why in news:</b> " + e(n.get("why"))]
    if key:
        parts += ["", key]
    if pre:
        parts += ["", "<b>Prelims:</b> " + e(pre)]
    if n.get("check"):
        parts += ["", "<i>Verify: %s</i>" % e(n["check"])]
    parts += ["", "AI draft by Niti Pathshala × NitiForge. Verify before quoting."]
    if SITE:
        parts.append('<a href="%s">Full note with diagram</a>' % html.escape(SITE, quote=True))
    return "\n".join(parts)[:4000]


def send(text):
    body = json.dumps({"chat_id": CHAT, "text": text, "parse_mode": "HTML",
                       "disable_web_page_preview": True}).encode()
    for attempt in range(3):
        req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % TOKEN, data=body,
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r).get("ok", False)
        except urllib.error.HTTPError as err:
            detail = err.read()[:300]
            if err.code in (400, 401, 403, 404):
                raise Stop("Telegram refused the post (HTTP %s). Check the bot token, the chat id, and that the bot is an admin of the channel. %s"
                           % (err.code, detail.decode("utf-8", "replace")[:120]))
            if err.code == 429 and attempt < 2:
                try:
                    wait = int(json.loads(detail).get("parameters", {}).get("retry_after", 10))
                except Exception:
                    wait = 10
                time.sleep(min(wait, 30) + 1)
                continue
            raise Stop("Telegram error HTTP %s" % err.code)
        except urllib.error.URLError as err:
            if attempt < 2:
                time.sleep(3)
                continue
            raise Stop("Telegram unreachable: %s" % err.reason)
    return False


def main():
    if not (TOKEN and CHAT):
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; skipping Telegram posts.")
        return
    notes = load(NOTES, {}).get("notes", {})
    first = not os.path.exists(STATE)
    st = load(STATE, {})
    posted = st.get("posted", {})
    now = datetime.now(timezone.utc)
    fresh = sorted(((k, v) for k, v in notes.items() if k not in posted),
                   key=lambda kv: kv[1].get("created", ""), reverse=True)
    if first and len(fresh) > FIRST_RUN:
        for k, _ in fresh[FIRST_RUN:]:      # backlog: mark as posted without sending
            posted[k] = "skipped-first-run"
        fresh = fresh[:FIRST_RUN]
    sent = 0
    try:
        for k, n in reversed(fresh[:MAX_RUN]):  # oldest of the batch first
            if send(message(n)):
                posted[k] = now.isoformat()
                sent += 1
                print("Posted:", n.get("title", "")[:70])
                json.dump({"posted": posted}, open(STATE, "w", encoding="utf-8"), indent=1)
                time.sleep(3)
    except Stop as err:
        print("STOPPING:", err)
    cut = (now - timedelta(days=30)).isoformat()
    posted = {k: v for k, v in posted.items() if k in notes or v >= cut}
    if sent or first:
        json.dump({"posted": posted}, open(STATE, "w", encoding="utf-8"), indent=1)
    print("Telegram: %d posted this run." % sent)


if __name__ == "__main__":
    main()
