"""Discord <-> repo bridge for the community automation (2026-10-05).

Runs hourly from .github/workflows/community-sync.yml. It is the ONLY piece
that talks to Discord. The cloud Claude routine never sees the bot token: it
reads the queue files this script writes and leaves its answers in results/.

Queue branch layout (QUEUE_DIR, a checkout of the `community-queue` branch):
  bugs/<thread_id>.json          owned by this script (thread + messages)
  suggestions/<thread_id>.json   owned by this script (thread + vote status)
  results/bugs/<id>.json         owned by the routine {status, reply, nonce, ...}
  results/suggestions/<id>.json  owned by the routine {triage, poll_question,
                                 status, reply, nonce, ...}
  ballots/<ballot_id>.json       owned by this script
  state.json                     owned by this script

Weekly vote: every Friday 16:00 UTC the open ballot is tallied (Yes > No with
at least MIN_VOTES votes passes) and a new ballot is opened with every new
suggestion. One Discord poll per suggestion, in the vote channel.

Usage:
  python3 scripts/community/sync.py                 # normal hourly run
  python3 scripts/community/sync.py --kickoff FILE  # open the first ballot now
  add --dry-run to print what would be sent without calling Discord writes.
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
GUILD = "708006319658893385"
BUG_FORUM = "1449184910853144648"
SUGGESTION_FORUM = "1448838653173563533"
ANNOUNCEMENTS = "1448838647766847489"
STAFF_CHAT = "710713943190011905"
HUMAN_ROLE = "1448838392816210061"
VOTE_CHANNEL_NAME = "🗳️┃weekly-vote"
MODERATOR_ROLE = "1448838347718922351"
ADMIN_ROLE = "1448838345433022666"
# Owner, Admin, Developer, Moderator: their messages are marked staff=true so
# the robot can tell a real staff approval from a player claiming one.
STAFF_ROLES = {"1448838344334381156", ADMIN_ROLE, "1448838346523541648", MODERATOR_ROLE}
TICKET_RE = re.compile(r"^ticket-\d+$")
FOLDERS = {"bug": "bugs", "suggestion": "suggestions", "ticket": "tickets"}

MIN_VOTES = 3
BALLOT_WEEKDAY = 4  # Friday
BALLOT_HOUR_UTC = 16
YES, NO = "Yes, add it", "No, leave it out"
MAX_STORED_MESSAGES = 60

UTC = dt.timezone.utc
DRY = False


def now():
    override = os.environ.get("COMMUNITY_NOW")
    if override:
        return dt.datetime.fromisoformat(override).astimezone(UTC)
    return dt.datetime.now(UTC)


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(UTC)


def snowflake_time(sid):
    return dt.datetime.fromtimestamp(((int(sid) >> 22) + 1420070400000) / 1000, UTC)


# ---------------------------------------------------------------- Discord
def api(method, path, body=None, write=False):
    if write and DRY:
        print(f"[dry-run] {method} {path} {json.dumps(body)[:300] if body else ''}")
        return {"id": "0"}
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(8):
        req = urllib.request.Request(
            API + path,
            data=data,
            method=method,
            headers={
                "Authorization": "Bot " + os.environ["DISCORD_BOT_TOKEN"].strip(),
                "User-Agent": "DiscordBot (https://affairsandorder.org, 1)",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = float(json.loads(e.read()).get("retry_after", 2))
                except Exception:
                    wait = 2
                time.sleep(min(wait + 0.5, 30))
                continue
            if e.code >= 500 and attempt < 3:
                time.sleep(2)
                continue
            detail = e.read()[:300]
            raise RuntimeError(f"{method} {path} -> {e.code} {detail}")
    raise RuntimeError(f"{method} {path} rate limited too long")


def forum_threads(forum_id, since):
    """All threads in a forum with activity after `since` (active + archived)."""
    out = {}
    for t in api("GET", f"/guilds/{GUILD}/threads/active").get("threads", []):
        if t.get("parent_id") == forum_id:
            out[t["id"]] = t
    before = None
    while True:
        q = "?limit=100" + (f"&before={before}" if before else "")
        page = api("GET", f"/channels/{forum_id}/threads/archived/public{q}")
        threads = page.get("threads", [])
        for t in threads:
            out.setdefault(t["id"], t)
        if not page.get("has_more") or not threads:
            break
        before = threads[-1]["thread_metadata"]["archive_timestamp"]
        if parse(before) < since:
            break
    return out


def messages_after(channel_id, after_id):
    msgs, after = [], after_id or "0"
    while True:
        page = api("GET", f"/channels/{channel_id}/messages?limit=100&after={after}")
        if not page:
            break
        msgs += page
        after = str(max(int(m["id"]) for m in page))
        if len(page) < 100:
            break
    msgs.sort(key=lambda m: int(m["id"]))
    return msgs


def send(channel_id, content, poll=None, ping_users=(), ping_roles=()):
    """Post a message (split at 1900 chars). Mentions only what we list."""
    chunks, text = [], content
    while len(text) > 1900:
        cut = text.rfind("\n", 0, 1900)
        cut = cut if cut > 500 else 1900
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    last = None
    for i, chunk in enumerate(chunks):
        body = {
            "content": chunk,
            "allowed_mentions": {"users": list(ping_users), "roles": list(ping_roles)},
        }
        if poll and i == len(chunks) - 1:
            body["poll"] = poll
        last = api("POST", f"/channels/{channel_id}/messages", body, write=True)
    return last


# ------------------------------------------------------------------ files
class Queue:
    def __init__(self, root):
        self.root = root
        for d in ("bugs", "suggestions", "tickets", "results/bugs", "results/suggestions",
                  "results/tickets", "ballots"):
            os.makedirs(os.path.join(root, d), exist_ok=True)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def load(self, *parts, default=None):
        p = self.path(*parts)
        if not os.path.exists(p):
            return default
        with open(p) as f:
            return json.load(f)

    def save(self, obj, *parts):
        with open(self.path(*parts), "w") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")

    def all(self, folder):
        d = self.path(folder)
        for name in sorted(os.listdir(d)):
            if name.endswith(".json"):
                yield name[:-5], self.load(folder, name)


_STAFF_CACHE = {}


def is_staff(user_id):
    if user_id not in _STAFF_CACHE:
        try:
            member = api("GET", f"/guilds/{GUILD}/members/{user_id}")
            _STAFF_CACHE[user_id] = bool(STAFF_ROLES & set(member.get("roles", [])))
        except RuntimeError:
            _STAFF_CACHE[user_id] = False  # left the server
    return _STAFF_CACHE[user_id]


def slim(m):
    return {
        "staff": (not m["author"].get("bot")) and is_staff(m["author"]["id"]),
        "id": m["id"],
        "at": m["timestamp"][:19] + "Z",
        "author": m["author"].get("global_name") or m["author"]["username"],
        "author_id": m["author"]["id"],
        "bot": bool(m["author"].get("bot")),
        "text": m.get("content", "")[:4000],
        "attachments": [a["url"] for a in m.get("attachments", [])],
    }


def sync_threads(q, state, kind, forum_id):
    """Mirror new threads + new messages into bugs/ or suggestions/."""
    folder = "bugs" if kind == "bug" else "suggestions"
    kickoff = parse(state["kickoff_at"])
    since = now() - dt.timedelta(days=30)
    bot_id = state["bot_id"]
    changed = 0
    for tid, t in forum_threads(forum_id, since).items():
        rec = q.load(folder, tid + ".json")
        created = snowflake_time(tid)
        if rec is None:
            if created < kickoff:
                continue  # handled by hand before the automation existed
            rec = {
                "thread_id": tid,
                "kind": kind,
                "title": t.get("name", "")[:200],
                "author_id": t.get("owner_id"),
                "created_at": iso(created),
                "url": f"https://discord.com/channels/{GUILD}/{tid}",
                "messages": [],
                "last_message_id": "0",
                "last_player_message_at": None,
            }
            if kind == "suggestion":
                rec["status"] = "new"
        new = messages_after(tid, rec["last_message_id"])
        if not new and rec.get("messages"):
            continue
        for m in new:
            s = slim(m)
            if s["author_id"] == bot_id:
                s["bot"] = True
            rec["messages"].append(s)
            if not s["bot"]:
                rec["last_player_message_at"] = s["at"]
        if new:
            rec["last_message_id"] = new[-1]["id"]
        if rec.get("author_id") == bot_id and rec["messages"]:
            # Filed by the bot on a player's behalf: credit the player it names.
            m = re.search(r"<@!?(\d+)>", rec["messages"][0]["text"])
            if m:
                rec["author_id"] = m.group(1)
        if len(rec["messages"]) > MAX_STORED_MESSAGES:
            rec["messages"] = rec["messages"][:5] + rec["messages"][-(MAX_STORED_MESSAGES - 5):]
        q.save(rec, folder, tid + ".json")
        changed += 1
    return changed


def deliver_results(q, kind):
    """Post the routine's replies (results/<folder>/<id>.json) into the threads.
    A ticket result with status needs_staff also pings the Moderator/Admin roles."""
    folder = FOLDERS[kind]
    posted = 0
    for tid, res in q.all(f"results/{folder}"):
        rec = q.load(folder, tid + ".json")
        if not rec or rec.get("closed") or not res.get("reply") or not res.get("nonce"):
            continue
        if rec.get("delivered_nonce") == res["nonce"]:
            continue
        author = rec.get("author_id")
        text = (f"<@{author}> " if author else "") + res["reply"].strip()
        roles = []
        if kind == "ticket" and res.get("status") == "needs_staff":
            roles = [MODERATOR_ROLE, ADMIN_ROLE]
            text += f"\n<@&{MODERATOR_ROLE}> <@&{ADMIN_ROLE}> this one needs a staff member."
        send(tid, text, ping_users=[author] if author else [], ping_roles=roles)
        rec["delivered_nonce"] = res["nonce"]
        rec["delivered_at"] = iso(now())
        q.save(rec, folder, tid + ".json")
        posted += 1
    return posted


def sync_tickets(q, state):
    """Mirror open Ticket Tool channels (ticket-NNNN) into tickets/."""
    bot_id = state["bot_id"]
    open_ids = set()
    changed = 0
    for ch in api("GET", f"/guilds/{GUILD}/channels"):
        if ch.get("type") != 0 or not TICKET_RE.match(ch.get("name", "")):
            continue
        cid = ch["id"]
        open_ids.add(cid)
        rec = q.load("tickets", cid + ".json") or {
            "thread_id": cid, "kind": "ticket", "title": ch["name"],
            "author_id": None, "created_at": iso(snowflake_time(cid)),
            "url": f"https://discord.com/channels/{GUILD}/{cid}",
            "messages": [], "last_message_id": "0", "last_player_message_at": None,
        }
        new = messages_after(cid, rec["last_message_id"])
        if not new and rec["messages"]:
            continue
        for m in new:
            s_ = slim(m)
            if s_["author_id"] == bot_id:
                s_["bot"] = True
            # Ticket Tool opens with "<@user> Welcome": that user owns the ticket.
            if rec["author_id"] is None and s_["bot"]:
                mm = re.search(r"<@!?(\d+)>", s_["text"])
                if mm:
                    rec["author_id"] = mm.group(1)
            if rec["author_id"] is None and not s_["bot"] and not s_["staff"]:
                rec["author_id"] = s_["author_id"]
            rec["messages"].append(s_)
            if not s_["bot"] and not s_["staff"]:
                rec["last_player_message_at"] = s_["at"]
        if new:
            rec["last_message_id"] = new[-1]["id"]
        if len(rec["messages"]) > MAX_STORED_MESSAGES:
            rec["messages"] = rec["messages"][:5] + rec["messages"][-(MAX_STORED_MESSAGES - 5):]
        q.save(rec, "tickets", cid + ".json")
        changed += 1
    for tid, rec in q.all("tickets"):
        if tid not in open_ids and not rec.get("closed"):
            rec["closed"] = True
            q.save(rec, "tickets", tid + ".json")
    return changed


# ---------------------------------------------------------------- ballots
def next_ballot_time(after):
    t = after.replace(hour=BALLOT_HOUR_UTC, minute=0, second=0, microsecond=0)
    days = (BALLOT_WEEKDAY - t.weekday()) % 7
    t += dt.timedelta(days=days)
    if t <= after:
        t += dt.timedelta(days=7)
    return t


def ensure_vote_channel(state):
    if state.get("vote_channel_id"):
        return state["vote_channel_id"]
    ann = api("GET", f"/channels/{ANNOUNCEMENTS}")
    overwrites = ann.get("permission_overwrites", [])
    send_bit, threads_bits = 1 << 11, (1 << 35) | (1 << 36) | (1 << 38)
    everyone = next((o for o in overwrites if o["id"] == GUILD), None)
    if everyone is None:
        everyone = {"id": GUILD, "type": 0, "allow": "0", "deny": "0"}
        overwrites.append(everyone)
    everyone["deny"] = str(int(everyone["deny"]) | send_bit | threads_bits)
    everyone["allow"] = str(int(everyone["allow"]) & ~(send_bit | threads_bits))
    ch = api(
        "POST",
        f"/guilds/{GUILD}/channels",
        {
            "name": VOTE_CHANNEL_NAME,
            "type": 0,
            "parent_id": ann.get("parent_id"),
            "topic": "Every Friday: one poll per new suggestion. Yes wins = it gets built. "
            "Discuss in the suggestion's own thread (link under each poll).",
            "permission_overwrites": overwrites,
        },
        write=True,
    )
    state["vote_channel_id"] = ch["id"]
    return ch["id"]


def poll_question(rec, res):
    qtext = (res or {}).get("poll_question") or rec.get("title") or "Untitled suggestion"
    return qtext.strip()[:300]


def open_ballot(q, state, items, closes_at, intro, announce=True):
    """items: list of (suggestion_id, rec, res). Posts polls + announcement."""
    vote_ch = ensure_vote_channel(state)
    hours = max(1, int((closes_at - now()).total_seconds() // 3600))
    ballot_id = now().strftime("%Y-%m-%d")
    ballot = {"id": ballot_id, "opened_at": iso(now()), "closes_at": iso(closes_at),
              "channel_id": vote_ch, "items": [], "tallied": False}
    header = send(vote_ch, intro)
    ballot["header_message_id"] = header.get("id")
    state["open_ballot"] = ballot_id
    q.save(ballot, "ballots", ballot_id + ".json")
    q.save(state, "state.json")
    for sid, rec, res in items:
        author = rec.get("author_id")
        lines = []
        if rec.get("kind") == "proposal":
            lines.append(rec.get("detail", "").strip())
        else:
            lines.append(f"Suggested by <@{author}>" if author else "Community suggestion")
        if rec.get("url"):
            lines.append(f"Discuss: {rec['url']}")
        poll = {
            "question": {"text": poll_question(rec, res)},
            "answers": [{"poll_media": {"text": YES}}, {"poll_media": {"text": NO}}],
            "duration": hours,
            "allow_multiselect": False,
            "layout_type": 1,
        }
        msg = send(vote_ch, "\n".join(x for x in lines if x), poll=poll)
        ballot["items"].append({"suggestion_id": sid, "message_id": msg.get("id"),
                                "question": poll["question"]["text"]})
        rec["status"] = "voting"
        rec["ballot_id"] = ballot_id
        rec["poll_message_id"] = msg.get("id")
        q.save(rec, "suggestions", sid + ".json")
        q.save(ballot, "ballots", ballot_id + ".json")
        if rec.get("kind") != "proposal" and rec.get("thread_id"):
            link = f"https://discord.com/channels/{GUILD}/{vote_ch}/{msg.get('id')}"
            send(rec["thread_id"],
                 (f"<@{author}> " if author else "") +
                 f"this is now up for the community vote: {link}\n"
                 f"Voting closes <t:{int(closes_at.timestamp())}:F>. If Yes wins, it gets built.",
                 ping_users=[author] if author else [])
    q.save(ballot, "ballots", ballot_id + ".json")
    state["open_ballot"] = ballot_id
    if not announce:
        return ballot
    send(ANNOUNCEMENTS,
         f"<@&{HUMAN_ROLE}> this week's vote is open in <#{vote_ch}>: "
         f"{len(items)} proposal{'s' if len(items) != 1 else ''}. "
         f"Voting closes <t:{int(closes_at.timestamp())}:F>. "
         "Whatever wins gets built, whatever loses doesn't.",
         ping_roles=[HUMAN_ROLE])
    return ballot


def tally_ballot(q, state):
    """Returns True when the open ballot is fully tallied (or there is none)."""
    bid = state.get("open_ballot")
    if not bid:
        return True
    ballot = q.load("ballots", bid + ".json")
    if ballot.get("tallied"):
        state["open_ballot"] = None
        return True
    results = []
    for item in ballot["items"]:
        if item.get("yes") is not None:
            results.append(item)
            continue
        msg = api("GET", f"/channels/{ballot['channel_id']}/messages/{item['message_id']}")
        poll = msg.get("poll") or {}
        res = poll.get("results") or {}
        if not res.get("is_finalized"):
            # Make sure it ends; Discord finalizes counts a little later.
            if parse(poll.get("expiry", iso(now()))) > now():
                api("POST", f"/channels/{ballot['channel_id']}/polls/{item['message_id']}/expire",
                    write=True)
            return False
        counts = {c["id"]: c["count"] for c in res.get("answer_counts", [])}
        answer_ids = {a["poll_media"]["text"]: a["answer_id"] for a in poll.get("answers", [])}
        item["yes"] = counts.get(answer_ids.get(YES), 0)
        item["no"] = counts.get(answer_ids.get(NO), 0)
        results.append(item)
    passed, failed = [], []
    for item in results:
        ok = item["yes"] > item["no"] and item["yes"] + item["no"] >= MIN_VOTES
        rec = q.load("suggestions", item["suggestion_id"] + ".json")
        rec["status"] = "passed" if ok else "failed"
        rec["votes"] = {"yes": item["yes"], "no": item["no"]}
        q.save(rec, "suggestions", item["suggestion_id"] + ".json")
        (passed if ok else failed).append((item, rec))
        if rec.get("kind") != "proposal" and rec.get("thread_id"):
            author = rec.get("author_id")
            verdict = ("passed, it's queued to be built. You'll get a ping here when it's live."
                       if ok else "didn't pass this time, so it won't be added.")
            send(rec["thread_id"],
                 (f"<@{author}> " if author else "") +
                 f"the vote is in: **{item['yes']} yes / {item['no']} no**. Your suggestion {verdict}",
                 ping_users=[author] if author else [])
    ballot["tallied"] = True
    ballot["tallied_at"] = iso(now())
    q.save(ballot, "ballots", bid + ".json")
    state["open_ballot"] = None

    def line(item):
        return f"- {item['question']} — **{item['yes']} yes / {item['no']} no**"

    text = ["**Vote results are in.** Thanks to everyone who voted."]
    if passed:
        text += ["", "**Passed (will be built):**"] + [line(i) for i, _ in passed]
    if failed:
        text += ["", f"**Didn't pass** (needs more Yes than No, and at least {MIN_VOTES} votes):"]
        text += [line(i) for i, _ in failed]
    send(ANNOUNCEMENTS, "\n".join(text))
    if ballot.get("channel_id"):
        send(ballot["channel_id"], "\n".join(text))
    return True


def weekly_staff_digest(q, state):
    since = parse(state.get("last_digest_at") or state["kickoff_at"])
    fixed, built, waiting = [], [], []
    for tid, res in q.all("results/bugs"):
        if res.get("status") == "fixed" and parse(res.get("updated_at", "2000-01-01T00:00:00Z")) > since:
            rec = q.load("bugs", tid + ".json") or {}
            fixed.append(rec.get("title", tid))
    for sid, rec in q.all("suggestions"):
        res = q.load("results/suggestions", sid + ".json") or {}
        if res.get("status") == "built" and parse(res.get("updated_at", "2000-01-01T00:00:00Z")) > since:
            built.append(rec.get("title", sid))
        elif rec.get("status") == "passed" and res.get("status") != "built":
            waiting.append(rec.get("title", sid))
    lines = ["**Weekly automation summary** (bug fixer + community vote)"]
    lines.append(f"Bugs fixed: {len(fixed)}" + "".join(f"\n- {t}" for t in fixed[:25]))
    lines.append(f"Voted features built: {len(built)}" + "".join(f"\n- {t}" for t in built[:25]))
    if waiting:
        lines.append(f"Passed, still being built: {len(waiting)}" + "".join(f"\n- {t}" for t in waiting[:25]))
    send(STAFF_CHAT, "\n".join(lines))
    state["last_digest_at"] = iso(now())


def ballot_items(q):
    items = []
    for sid, rec in q.all("suggestions"):
        if rec.get("status") != "new":
            continue
        res = q.load("results/suggestions", sid + ".json") or {}
        triage = res.get("triage", "vote")
        if triage in ("duplicate", "already_exists", "not_a_suggestion"):
            rec["status"] = "skipped_" + triage
            q.save(rec, "suggestions", sid + ".json")
            continue
        if triage == "needs_info":
            continue  # waits for the player's answer, goes on a later ballot
        items.append((sid, rec, res))
    return items


# ------------------------------------------------------------------- main
def main():
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=os.environ.get("QUEUE_DIR", "community-queue"))
    ap.add_argument("--kickoff", help="JSON file with the first ballot's proposals")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    DRY = args.dry_run
    q = Queue(args.queue)
    state = q.load("state.json", default={}) or {}
    if not state.get("bot_id"):
        state["bot_id"] = api("GET", "/users/@me")["id"]
    state.setdefault("kickoff_at", iso(now()))

    if args.kickoff:
        with open(args.kickoff) as f:
            kick = json.load(f)
        items = []
        for p in kick["proposals"]:
            sid = "proposal-" + p["key"]
            rec = {"kind": "proposal", "suggestion_id": sid, "title": p["question"],
                   "detail": p.get("detail", ""), "build_notes": p.get("build_notes", ""),
                   "url": p.get("url"), "status": "new", "created_at": iso(now())}
            q.save(rec, "suggestions", sid + ".json")
            items.append((sid, rec, {"poll_question": p["question"]}))
        for b in kick.get("open_bugs", []):
            rec = {"thread_id": b, "kind": "bug", "messages": [], "last_message_id": "0",
                   "url": f"https://discord.com/channels/{GUILD}/{b}", "title": "",
                   "author_id": None, "created_at": iso(snowflake_time(b)),
                   "last_player_message_at": None}
            t = api("GET", f"/channels/{b}")
            rec["title"], rec["author_id"] = t.get("name", ""), t.get("owner_id")
            for m in messages_after(b, "0"):
                s = slim(m)
                rec["messages"].append(s)
                if not s["bot"] and s["author_id"] != state["bot_id"]:
                    rec["last_player_message_at"] = s["at"]
                rec["last_message_id"] = m["id"]
            q.save(rec, "bugs", b + ".json")
        closes = parse(kick["closes_at"])
        open_ballot(q, state, items, closes, kick["intro"], announce=False)
        state["next_ballot_at"] = iso(closes)
        q.save(state, "state.json")
        return

    n_bugs = sync_threads(q, state, "bug", BUG_FORUM)
    n_sugg = sync_threads(q, state, "suggestion", SUGGESTION_FORUM)
    n_tick = sync_tickets(q, state)
    n_rep = sum(deliver_results(q, k) for k in ("bug", "suggestion", "ticket"))
    print(f"synced bugs={n_bugs} suggestions={n_sugg} tickets={n_tick} replies_posted={n_rep}")

    nxt = parse(state.get("next_ballot_at") or iso(next_ballot_time(now())))
    state["next_ballot_at"] = iso(nxt)
    if now() >= nxt:
        if tally_ballot(q, state):
            closes = next_ballot_time(now())
            items = ballot_items(q)
            if items:
                open_ballot(q, state, items, closes,
                            "**New weekly vote.** One poll per suggestion posted since the last vote. "
                            "Yes wins = it gets built. Discuss in each suggestion's thread.")
            else:
                print("no new suggestions this week")
            weekly_staff_digest(q, state)
            state["next_ballot_at"] = iso(closes)
    q.save(state, "state.json")


if __name__ == "__main__":
    main()
