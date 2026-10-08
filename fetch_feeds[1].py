#!/usr/bin/env python3
"""Fetch RSS/Atom feeds and write feed.json for the UPSC CA portal.
Stores only headline, link, source, time and a short snippet (not full articles).
Add or remove sources in FEEDS. A feed that fails is skipped; others still update."""
import json, re, os, html, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

FEEDS = [
    # (label, url)  -- PIB URL: confirm on pib.gov.in/RssMain.aspx and replace if needed
    ("PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
    ("The Hindu - National", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ("The Hindu - Editorial", "https://www.thehindu.com/opinion/editorial/feeder/default.rss"),
    ("The Hindu - International", "https://www.thehindu.com/news/international/feeder/default.rss"),
    ("The Hindu - Business", "https://www.thehindu.com/business/feeder/default.rss"),
    ("Indian Express - India", "https://indianexpress.com/section/india/feed/"),
    ("Indian Express - Explained", "https://indianexpress.com/section/explained/feed/"),
    # Added sources -- URLs not verified from here; a failing feed is skipped, check the Actions log
    ("Indian Express - Editorials", "https://indianexpress.com/section/opinion/editorials/feed/"),
    ("The Hindu - Science", "https://www.thehindu.com/sci-tech/science/feeder/default.rss"),
    ("The Hindu - Environment", "https://www.thehindu.com/sci-tech/energy-and-environment/feeder/default.rss"),
    ("PRS India", "https://prsindia.org/rss/theprsblog"),
    ("Rajya Sabha TV / Sansad TV", "https://sansadtv.nic.in/rss"),
]
KEEP_DAYS, MAX_ITEMS, SNIP = 7, 400, 600
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feed.json")
IST = timezone(timedelta(hours=5, minutes=30))
UA = "Mozilla/5.0 (compatible; UPSC-CA-Portal/1.0)"

CATS = [  # (category, GS paper, keywords) -- first match wins, tune freely
    ("Polity", "GS2", "supreme court|high court|parliament|lok sabha|rajya sabha|constitution|election commission|bill|amendment|governor|cabinet|governance|panchayat|federal"),
    ("International Relations", "GS2", "bilateral|summit|un |united nations|foreign minister|treaty|mea|quad|brics|g20|asean|diplomat|sanction|saarc|ties with"),
    ("Economy", "GS3", "rbi|gdp|inflation|repo|budget|gst|fiscal|trade|export|import|sebi|bank|msme|tax|economy|msp|agricultur"),
    ("Environment", "GS3", "climate|wildlife|forest|pollution|biodiversity|tiger|emission|cop|ramsar|ecolog|carbon|monsoon|glacier"),
    ("Science & Tech", "GS3", "isro|satellite|ai |artificial intelligence|quantum|space|drdo|semiconductor|vaccine|research|launch|mission|cyber"),
    ("Security", "GS3", "army|navy|air force|terror|border|defence|missile|naxal|insurgen|lac |loc "),
    ("Society", "GS1", "women|education|health|tribal|poverty|caste|nutrition|migration|scheme|welfare|children|census"),
    ("History & Culture", "GS1", "heritage|unesco|temple|archaeolog|museum|festival|monument|freedom struggle|inscription"),
    ("Geography", "GS1", "earthquake|cyclone|flood|river|volcano|drought|himalaya|island|landslide"),
]

# ---- UPSC relevance filter: drops sports/film/crime/market-noise, keeps policy-relevant items ----
EXCLUDE = re.compile(r"\b(cricket|ipl|t20|odi|test match|football|fifa|premier league|tennis|badminton|kabaddi|"
    r"bollywood|tollywood|box office|actor|actress|celebrity|web series|ott|trailer|horoscope|astrology|"
    r"murder|murdered|stabbed|rape|accident|sensex|nifty|share price|stock to buy|gold rate|petrol price|"
    r"recipe|fashion|lifestyle|viral video|wedding|condole|condoles|greets|congratulates|birth anniversary|best wishes)\b", re.I)
IMPORTANT = re.compile(r"\b(scheme|policy|act|bill|ordinance|committee|commission|tribunal|cabinet|supreme court|high court|"
    r"constitution|treaty|agreement|mou|summit|index|report|survey|rbi|msp|budget|gdp|mission|programme|initiative|"
    r"bench|amendment|regulation|framework|sebi|niti aayog|census)\b", re.I)
SRC_BONUS = {"PIB": 3, "The Hindu - Editorial": 3, "Indian Express - Editorials": 3, "Indian Express - Explained": 3,
             "PRS India": 3, "The Hindu - Science": 1, "The Hindu - Environment": 1}
KEEP_MIN = 2

def score(i):
    t = i["h"] + " " + i.get("snip", "")
    if EXCLUDE.search(t):
        return -1
    t2 = " " + t.lower() + " "
    hits = sum(1 for _, _, kw in CATS if re.search(kw, t2))
    return SRC_BONUS.get(i["src"], 0) + min(hits, 3) + (1 if IMPORTANT.search(t) else 0)

def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()

def classify(text):
    t = " " + text.lower() + " "
    for cat, gs, kw in CATS:
        if re.search(kw, t):
            return cat, gs
    return "Polity", "GS2"

def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(IST)

def local(tag):
    return tag.split("}")[-1]

def parse_feed(xml_bytes, label):
    root = ET.fromstring(xml_bytes)
    out = []
    for el in root.iter():
        if local(el.tag) not in ("item", "entry"):
            continue
        f = {}
        for c in el:
            k = local(c.tag)
            if k == "link":
                f["link"] = (c.attrib.get("href") or c.text or "").strip()
            elif k in ("title", "description", "summary", "pubDate", "published", "updated"):
                f.setdefault(k, c.text or "")
        title = clean(f.get("title"))
        link = f.get("link", "")
        if not title or not link:
            continue
        d = parse_date(f.get("pubDate") or f.get("published") or f.get("updated")) or datetime.now(IST)
        snip = clean(f.get("description") or f.get("summary"))[:SNIP]
        cat, gs = classify(title + " " + snip)
        out.append({"id": link, "h": title, "link": link, "src": label, "t": d.isoformat(),
                    "date": d.strftime("%Y-%m-%d"), "snip": snip, "cat": cat, "gs": gs})
    return out

def main():
    try:
        old = json.load(open(OUT, encoding="utf-8")).get("items", [])
    except Exception:
        old = []
    items = {i["id"]: i for i in old}
    status = {}
    for label, url in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                got = parse_feed(r.read(), label)
            for i in got:
                items.setdefault(i["id"], i)
            status[label] = "ok (%d)" % len(got)
        except Exception as e:
            status[label] = "failed: %s" % type(e).__name__
    cutoff = datetime.now(IST) - timedelta(days=KEEP_DAYS)
    for i in items.values():
        i["score"] = score(i)
    total = len(items)
    kept = [i for i in items.values() if i["score"] >= KEEP_MIN and datetime.fromisoformat(i["t"]) >= cutoff]
    print("Relevance filter kept %d of %d items" % (len(kept), total))
    kept.sort(key=lambda i: i["t"], reverse=True)
    kept = kept[:MAX_ITEMS]
    for k, v in status.items():
        print(k, "->", v)
    if [i["id"] for i in kept] == [i["id"] for i in old]:
        print("No new items; feed.json unchanged.")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(IST).isoformat(), "status": status, "items": kept},
                  f, ensure_ascii=False, indent=1)
    print("Wrote", len(kept), "items")

if __name__ == "__main__":
    main()
