"""Watch a page and push an ntfy alert when counts change."""
import hashlib
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
    """Return {section: {"A": (count, earliest), "B": (count, earliest)}}."""
    anchor = os.environ.get("ANCHOR", "")
    if anchor and anchor in text:
        text = text[text.index(anchor):]
    results = {}
    for i, city in enumerate(CITIES):
        start = text.find(f"### {city}")
        if start < 0:
            start = text.find(city)
        if start < 0:
            continue
        nxt = [text.find(c, start + len(city)) for c in CITIES[i + 1:]]
        nxt = [n for n in nxt if n > 0]
        block = text[start: min(nxt) if nxt else start + 1500]
        info = {}
        for label, key in ((A_LABEL, "A"), (B_LABEL, "B")):
            m = re.search(re.escape(label) + r".{0,80}?(\d+)\s+openings?.{0,80}?Earliest from ([A-Z][a-z]+ \d{4})", block, re.I)
            if m:
                info[key] = (int(m.group(1)), m.group(2))
        results[city] = info
    return results


def notify(title, body, priority):
    req = urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}", data=body.encode(),
        headers={"Title": title, "Priority": priority, "Click": os.environ.get("CLICK_URL", "")})
    urllib.request.urlopen(req, timeout=30)


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

    hits_b = [f"{c}: {v['B'][1]} ({v['B'][0]})"
                 for c, v in data.items() if v.get("B", (0,))[0] > 0]
    hits_a = [f"{c}: {v['A'][1]} ({v['A'][0]})"
           for c, v in data.items() if v.get("A", (0,))[0] > 0]
    if not hits_b and not hits_a:
        print("no openings")
        return

    body = ""
    if hits_b:
        body += B_NAME + ": " + ", ".join(hits_b) + "\n"
    if hits_a:
        body += A_NAME + ": " + ", ".join(hits_a)

    # Skip if identical to the last alert, so you aren't pinged repeatedly.
    digest = hashlib.sha256(body.encode()).hexdigest()
    old = open(STATE_FILE).read().strip() if os.path.exists(STATE_FILE) else ""
    if digest == old:
        print("same as last alert, skipping")
        return
    with open(STATE_FILE, "w") as f:
        f.write(digest)

    if hits_b:
        notify("🟢 " + B_NAME, body, "urgent")
    else:
        notify(A_NAME + " only", body, "default")
    print("alert sent:\n" + body)


if __name__ == "__main__":
    sys.exit(main())
