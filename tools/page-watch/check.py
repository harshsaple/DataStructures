"""Read several feeds of sightings and push an ntfy alert for new, matching ones.

All specifics come from the CONFIG secret (JSON):
  NTFY_TOPIC     ntfy topic to push to
  SOURCES        list of {"name", "type", "url"}; type is one of: embedded, grid, table
  MATCH          value of the class field to keep (embedded type only)
  SECTION        heading of the block to read (grid type only)
  NAMES          display names: "<first kind>,<second kind>"
  CLICK_URL      link opened when the notification is tapped
  FRESH_MINUTES  ignore sightings older than this when first noticed (default 120)
"""
import html as htmllib
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

CFG = json.loads(os.environ.get("CONFIG") or "{}")
TOPIC = CFG["NTFY_TOPIC"]
SOURCES = CFG["SOURCES"]
MATCH = CFG.get("MATCH", "").lower()
SECTION = CFG.get("SECTION", "")
A_NAME, B_NAME = CFG.get("NAMES", "A,B").split(",")
FRESH_MIN = int(CFG.get("FRESH_MINUTES", 120))
STATE_FILE = "last_alert.txt"
HEALTH_FILE = "health.json"
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc


# ---------- fetching ----------

def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
        "Accept": "text/html", "Accept-Language": "en"})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def plain(html):
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", html)))


def rec(src, city, kind, earliest, seen, count, key):
    """kind is 'a' (first name, e.g. biometrics) or 'b' (second name, e.g. interview)."""
    return {"src": src, "city": city.strip().title(), "kind": kind, "earliest": earliest,
            "seen": seen, "count": count, "id": f"{src}|{key}"}


# ---------- parsers (each returns sightings that show availability, and rows read) ----------

def parse_embedded(src, html):
    pat = (r'id:"([^"]+)",city:"([^"]+)",kind:"([^"]+)",visaClass:"([^"]+)",'
           r'earliestDate:"([\d-]+)",seenAt:(\d+),count:(\d+)')
    out, total = [], 0
    for rid, city, kind, cls, earliest, seen_ms, count in re.findall(pat, html):
        total += 1
        if cls.lower() != MATCH:
            continue
        city = {"delhi": "new delhi"}.get(city, city)
        out.append(rec(src, city, "a" if kind == "ofc" else "b",
                       datetime.strptime(earliest, "%Y-%m-%d").date(),
                       datetime.fromtimestamp(int(seen_ms) / 1000, UTC), int(count), rid))
    return out, total


def parse_grid(src, html):
    text = plain(html)
    start = text.find(SECTION)
    if start < 0:
        return [], 0
    end = text.find("View all", start)
    block = text[start:end if end > 0 else start + 4000]
    pat = (r"([A-Z][A-Z ]*?) (CONSULAR|VAC) (\d{1,2} \w{3} \d{4} \d{1,2}:\d{2}:\d{2} [AP]M) UTC "
           r"(N/A|\d{1,2} \w{3} \d{4}) (\d+)")
    out, total = [], 0
    for city, kind, upd, earliest, slots in re.findall(pat, block):
        total += 1
        if earliest == "N/A" and int(slots) == 0:
            continue
        seen = datetime.strptime(upd, "%d %b %Y %I:%M:%S %p").replace(tzinfo=UTC)
        e = datetime.strptime(earliest, "%d %b %Y").date() if earliest != "N/A" else None
        out.append(rec(src, city, "a" if kind == "VAC" else "b", e, seen, int(slots),
                       f"{city}|{kind}|{upd}|{earliest}"))
    return out, total


def parse_table(src, html):
    text = plain(html)
    pat = (r"([A-Z][A-Z ]*?) H-1B \(Regular\) (\d{2} \w{3}, \d{2}) (N/A|\d+) (\d+) "
           r"(\d{1,2} \w{3} \d{4}, \d{1,2}:\d{2} [AP]M)")
    out, total = [], 0
    for loc, earliest, _n, dates, seen in re.findall(pat, text):
        total += 1
        ofc = loc.endswith(" VAC")
        city = loc[:-4] if ofc else loc
        out.append(rec(src, city, "a" if ofc else "b",
                       datetime.strptime(earliest, "%d %b, %y").date(),
                       datetime.strptime(seen, "%d %b %Y, %I:%M %p").replace(tzinfo=UTC),
                       int(dates), f"{loc}|{earliest}|{seen}"))
    return out, total


PARSERS = {"embedded": parse_embedded, "grid": parse_grid, "table": parse_table}


# ---------- alerts ----------

def notify(title, body, priority, tags):
    req = urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}", data=body.encode("utf-8"),
        headers={"Title": title.encode("utf-8").decode("latin-1", "replace"),
                 "Priority": priority, "Tags": tags, "Click": CFG.get("CLICK_URL", "")})
    urllib.request.urlopen(req, timeout=30)


def line(r, now):
    d = r["earliest"].strftime("%-d %b %Y") if r["earliest"] else "date not shown"
    ago = int((now - r["seen"]).total_seconds() // 60)
    ago_s = f"{ago} min ago" if ago < 120 else f"{ago // 60} h ago"
    seen = r["seen"].astimezone(IST).strftime("%-I:%M %p")
    return f"• {r['city']}: {d} · seen {seen} ({ago_s}) · via {r['src']}"


def load_ids():
    try:
        return set(open(STATE_FILE).read().split("\n"))
    except OSError:
        return set()


def load_health():
    try:
        return json.load(open(HEALTH_FILE))
    except (OSError, ValueError):
        return {}


def check_health(name, ok, health, now):
    """Warn once after 3 failed runs in a row for a source, and once when it recovers."""
    fails = health.get(name, 0)
    if ok:
        if fails >= 3:
            notify(f"{name} working again", "Back to normal.", "low", "white_check_mark")
        health[name] = 0
    else:
        health[name] = fails + 1
        if fails + 1 == 3:
            notify(f"{name} not working",
                   f"Couldn't read {name} for ~15 min. Other sources still run.\n"
                   f"Since {now.astimezone(IST).strftime('%-I:%M %p')} IST.", "high", "warning")


def main():
    now = datetime.now(UTC)
    health = load_health()
    sightings = []
    for s in SOURCES:
        try:
            found, total = PARSERS[s["type"]](s["name"], fetch(s["url"]))
            ok = total > 0
            print(f"{s['name']}: {total} rows read, {len(found)} with availability")
        except Exception as e:
            found, ok = [], False
            print(f"{s['name']}: failed: {e}")
        check_health(s["name"], ok, health, now)
        sightings += found
    json.dump(health, open(HEALTH_FILE, "w"))

    for r in sorted(sightings, key=lambda r: r["seen"], reverse=True):
        print("  ", r["src"], r["city"], r["kind"], r["earliest"],
              r["seen"].astimezone(IST).strftime("%d %b %H:%M IST"))

    fresh = [r for r in sightings if now - r["seen"] <= timedelta(minutes=FRESH_MIN)]
    old_ids = load_ids()
    new = [r for r in fresh if r["id"] not in old_ids]
    keep = {r["id"] for r in fresh} | (old_ids & {r["id"] for r in sightings})
    open(STATE_FILE, "w").write("\n".join(sorted(keep)))
    if not new:
        print(f"nothing new in the last {FRESH_MIN} min")
        return

    key = lambda r: (r["earliest"] or datetime.max.date(), r["city"])
    a = sorted([r for r in new if r["kind"] == "a"], key=key)
    b = sorted([r for r in new if r["kind"] == "b"], key=key)
    body = ""
    if b:
        body += f"{B_NAME.upper()}\n" + "\n".join(line(r, now) for r in b) + "\n\n"
    if a:
        body += f"{A_NAME}\n" + "\n".join(line(r, now) for r in a) + "\n\n"
    body += f"Checked {now.astimezone(IST).strftime('%-I:%M %p')} IST · may already be taken, open now"

    if b:
        cities = ", ".join(dict.fromkeys(r["city"] for r in b))
        notify(f"{B_NAME} slot: {cities}", body, "urgent", "green_circle,rotating_light")
    else:
        cities = ", ".join(dict.fromkeys(r["city"] for r in a))
        notify(f"{A_NAME} slot: {cities}", body, "default", "large_blue_circle")
    print("alert sent:\n" + body)


if __name__ == "__main__":
    sys.exit(main())
