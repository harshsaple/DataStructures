"""Watch a page and push an ntfy alert when new items are seen."""
from datetime import datetime, timedelta, timezone
import html
import os
import re
import sys
import urllib.request
import json

# All settings can come from one CONFIG secret (JSON) or from separate variables.
_cfg = json.loads(os.environ.get("CONFIG") or "{}")
for _k, _v in _cfg.items():
    if not os.environ.get(_k):
        os.environ[_k] = _v

URL = os.environ["TARGET_URL"]
CITIES = os.environ["SECTIONS"].split(",")
A_LABEL, B_LABEL = os.environ["LABELS"].split(",")  # page labels for type A and type B
A_NAME, B_NAME = os.environ.get("NAMES", "A,B").split(",")  # names shown in alerts
TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = "last_alert.txt"


def fetch_text():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text)


def parse(text):
    """Return {section: {"A"|"B": {"count", "earliest", "seen"}}}."""
    anchor = os.environ.get("ANCHOR", "")
    if anchor and anchor in text:
        text = text[text.index(anchor):]
    results = {}
    for i, city in enumerate(CITIES):
        start = text.find(city)
        if start < 0:
            continue
        nxt = [text.find(c, start + len(city)) for c in CITIES[i + 1:]]
        nxt = [n for n in nxt if n > 0]
        block = text[start: min(nxt) if nxt else start + 1500]
        info = {}
        labels = ((A_LABEL, "A"), (B_LABEL, "B"))
        for j, (label, key) in enumerate(labels):
            pos = re.search(re.escape(label), block, re.I)
            if not pos:
                continue
            part = block[pos.start():]
            if j == 0:  # stop the A part where the B part begins
                b = re.search(re.escape(labels[1][0]), part, re.I)
                part = part[: b.start()] if b else part
            m = re.search(r"(\d+)\s+openings?", part, re.I)
            e = re.search(r"Earliest from ([A-Z][a-z]+ \d{4})", part)
            seen = re.search(r"last seen (\d{1,2} [A-Z][a-z]{2}, \d{1,2}:\d{2} [ap]m)", part, re.I)
            if m:
                info[key] = {"count": int(m.group(1)),
                             "earliest": e.group(1) if e else "?",
                             "seen": seen.group(1) if seen else ""}
        results[city] = info
    return results


def notify(title, body, priority, tags):
    req = urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}", data=body.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Tags": tags,
                 "Click": os.environ.get("CLICK_URL", "")})
    urllib.request.urlopen(req, timeout=30)


def short_month(m):
    return m[:3] + " " + m[-4:] if m != "?" else m


def lines_for(data, key):
    out = []
    for city, v in data.items():
        x = v.get(key)
        if x and x["count"] > 0:
            seen = f" · last seen {x['seen'].split(', ')[-1]}" if x["seen"] else ""
            out.append(f"• {city}: from {short_month(x['earliest'])} · {x['count']} in last 3h{seen}")
    return out


def main():
    try:
        data = parse(fetch_text())
    except Exception as e:  # page down: stay quiet, try next run
        print("fetch failed:", e)
        return
    print(data)
    if not data:
        print("could not parse page")
        return

    hits_b = lines_for(data, "B")
    hits_a = lines_for(data, "A")
    if not hits_b and not hits_a:
        print("no openings")
        return

    # Alert only when something was seen that we haven't alerted on before
    # (a new "last seen" time), not every time a 3-hour count changes.
    sightings = sorted(f"{c}|{k}|{x['seen']}" for c, v in data.items()
                       for k, x in v.items() if x["count"] > 0)
    old = set(open(STATE_FILE).read().split("\n")) if os.path.exists(STATE_FILE) else set()
    fresh = [s for s in sightings if s not in old]
    with open(STATE_FILE, "w") as f:
        f.write("\n".join(sightings))
    if not fresh:
        print("nothing new since last alert, skipping")
        return
    new_b = any(s.split("|")[1] == "B" for s in fresh)

    ist = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%-I:%M %p")
    body = ""
    if hits_b:
        body += f"{B_NAME.upper()}\n" + "\n".join(hits_b) + "\n\n"
    if hits_a:
        body += f"{A_NAME}\n" + "\n".join(hits_a) + "\n\n"
    body += f"Checked {ist} IST · times are IST · tap to open"

    if new_b:
        cities = ", ".join(s.split("|")[0] for s in fresh if s.split("|")[1] == "B")
        notify(f"{B_NAME} slots seen: {cities}", body, "urgent", "green_circle,rotating_light")
    else:
        cities = ", ".join(sorted({s.split("|")[0] for s in fresh}))
        notify(f"New {A_NAME} slots: {cities}", body, "default", "large_blue_circle")
    print("alert sent:\n" + body)


if __name__ == "__main__":
    sys.exit(main())
