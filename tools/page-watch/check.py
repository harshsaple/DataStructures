"""Read a feed of sightings and push an ntfy alert for fresh, matching ones.

All specifics come from the CONFIG secret (JSON) or separate env variables:
  NTFY_TOPIC     ntfy topic to push to
  TARGET_URL     page whose embedded records are read
  MATCH          value of the record's class field to keep
  NAMES          display names: "<name for primary kind>,<name for other kinds>"
  PRIMARY_KIND   record kind shown with the first name (default "ofc")
  CLICK_URL      link opened when the notification is tapped
  FRESH_MINUTES  ignore records older than this when first noticed (default 120)
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

_cfg = json.loads(os.environ.get("CONFIG") or "{}")
for _k, _v in _cfg.items():
    if not os.environ.get(_k):
        os.environ[_k] = str(_v)

URL = os.environ["TARGET_URL"]
TOPIC = os.environ["NTFY_TOPIC"]
MATCH = os.environ["MATCH"].lower()
A_NAME, B_NAME = os.environ.get("NAMES", "A,B").split(",")
PRIMARY = os.environ.get("PRIMARY_KIND", "ofc")
FRESH_MIN = int(os.environ.get("FRESH_MINUTES", "120"))
HEALTH_FILE = "health.txt"
STATE_FILE = "last_alert.txt"
IST = timezone(timedelta(hours=5, minutes=30))

RECORD = re.compile(
    r'id:"([^"]+)",city:"([^"]+)",kind:"([^"]+)",visaClass:"([^"]+)",'
    r'earliestDate:"([\d-]+)",seenAt:(\d+),count:(\d+)')


def fetch():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept": "text/html"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def parse(html):
    out = []
    for rid, city, kind, cls, earliest, seen_ms, count in RECORD.findall(html):
        out.append({"id": rid, "city": city, "kind": kind, "cls": cls.lower(),
                    "earliest": earliest, "count": int(count),
                    "seen": datetime.fromtimestamp(int(seen_ms) / 1000, IST)})
    return out


def notify(title, body, priority, tags):
    req = urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}", data=body.encode("utf-8"),
        headers={"Title": title.encode("utf-8").decode("latin-1", "replace"),
                 "Priority": priority, "Tags": tags,
                 "Click": os.environ.get("CLICK_URL", "")})
    urllib.request.urlopen(req, timeout=30)


def nice_city(c):
    return {"delhi": "New Delhi", "newdelhi": "New Delhi", "new-delhi": "New Delhi"}.get(c, c.title())


def line(r, now):
    d = datetime.strptime(r["earliest"], "%Y-%m-%d").strftime("%-d %b %Y")
    more = f" (+{r['count'] - 1} more date{'s' if r['count'] > 2 else ''})" if r["count"] > 1 else ""
    ago = int((now - r["seen"]).total_seconds() // 60)
    return f"• {nice_city(r['city'])}: {d}{more} · seen {r['seen'].strftime('%-I:%M %p')} ({ago} min ago)"


def health(problem, now):
    """Return True if OK. Alert once when the source breaks, once when it recovers."""
    was = open(HEALTH_FILE).read().strip() if os.path.exists(HEALTH_FILE) else "ok"
    if problem:
        print(problem)
        fails = int(was) + 1 if was.isdigit() else 1
        with open(HEALTH_FILE, "w") as f:
            f.write(str(fails))
        if fails == 3:  # ~15 min of failures in a row
            notify("Watcher not working", f"{problem}\nNo alerts until this is fixed. "
                   f"Since {now.strftime('%-I:%M %p')} IST.", "high", "warning")
        return False
    if was.isdigit() and int(was) >= 3:
        notify("Watcher working again", "Back to normal.", "low", "white_check_mark")
    with open(HEALTH_FILE, "w") as f:
        f.write("ok")
    return True


def main():
    now = datetime.now(IST)
    try:
        records = parse(fetch())
        problem = "" if records else "no records found (page layout may have changed)"
    except Exception as e:
        records, problem = [], f"fetch failed: {e}"
    if not health(problem, now):
        return

    mine = [r for r in records if r["cls"] == MATCH]
    print(f"{len(records)} records, {len(mine)} matching")
    for r in mine:
        print(" ", r["city"], r["kind"], r["earliest"], r["seen"].strftime("%d %b %H:%M"))

    fresh = [r for r in mine if now - r["seen"] <= timedelta(minutes=FRESH_MIN)]
    old_ids = set(open(STATE_FILE).read().split()) if os.path.exists(STATE_FILE) else set()
    new = [r for r in fresh if r["id"] not in old_ids]
    with open(STATE_FILE, "w") as f:  # remember ids still on the feed
        f.write("\n".join(sorted({r["id"] for r in fresh} | (old_ids & {r["id"] for r in mine}))))
    if not new:
        print(f"nothing new in the last {FRESH_MIN} min")
        return

    a = sorted([r for r in new if r["kind"] == PRIMARY], key=lambda r: r["earliest"])
    b = sorted([r for r in new if r["kind"] != PRIMARY], key=lambda r: r["earliest"])
    body = ""
    if b:
        body += f"{B_NAME.upper()}\n" + "\n".join(line(r, now) for r in b) + "\n\n"
    if a:
        body += f"{A_NAME}\n" + "\n".join(line(r, now) for r in a) + "\n\n"
    body += f"Checked {now.strftime('%-I:%M %p')} IST · may already be taken, open now"

    if b:
        cities = ", ".join(dict.fromkeys(nice_city(r["city"]) for r in b))
        notify(f"{B_NAME} slot: {cities}", body, "urgent", "green_circle,rotating_light")
    else:
        cities = ", ".join(dict.fromkeys(nice_city(r["city"]) for r in a))
        notify(f"{A_NAME} slot: {cities}", body, "default", "large_blue_circle")
    print("alert sent:\n" + body)


if __name__ == "__main__":
    sys.exit(main())
