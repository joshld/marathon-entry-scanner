"""Conservative candidate extraction from organisers' event and registration pages.

Detected fields are NEVER labelled verified. They are evidence to review, not
official confirmation of the event edition, category, eligibility or prices.
"""
import json
import re
from datetime import date, datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12
}
DATE_RX = re.compile(
    r"(?:20(?:2[6-9]|3[0-3])[-/.]\d{1,2}[-/.]\d{1,2})"
    r"|(?:20(?:2[6-9]|3[0-3])年\d{1,2}月\d{1,2}日)"
    r"|(?:\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+20\d{2}\b)"
    r"|(?:\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+20\d{2}\b)",
    re.I
)
DATE_LABEL = {
    "race_date": re.compile(r"\b(?:race date|event date|marathon date|date of (?:the )?(?:marathon|race))\b|大会開催日|開催日", re.I),
    "entry_open_date": re.compile(r"\b(?:entries?|registrations?|applications?|ballot)(?:.{0,32}?)(?:open|opens|opened|start|starts|begin|begins)\b|エントリー開始|申込開始|受付開始", re.I),
    "entry_close_date": re.compile(r"\b(?:entries?|registrations?|applications?|ballot)(?:.{0,32}?)(?:close|closes|closed|end|ends|deadline)\b|申込締切|受付終了日|締切日", re.I),
}
PRICE_RX = re.compile(r"(?:A\$|NZ\$|HK\$|US\$|S\$|£|€|¥|\$|₹|₩|₱|R\s?|THB\s?|JPY\s?|AUD\s?|USD\s?|EUR\s?|GBP\s?)\s?\d[\d,]*(?:\.\d{1,2})?", re.I)
RULE_RX = re.compile(r"\b(?:minimum age|age limit|years of age|must be at least|qualifying time|qualifying result|residen(?:cy|ts?) only|eligibility criteria|qualification standards)\b|参加資格|年齢制限|参加条件", re.I)
COMMON = set("marathon half run running festival international standard chartered the and city race event ultra trail by of for".split())

def iso_date(raw):
    if not raw:
        return None
    m = DATE_RX.search(str(raw))
    if not m:
        return None
    s = m.group(0).strip()
    try:
        if "年" in s:
            p = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
            d = date(*map(int, p.groups()))
        elif re.match(r"^\d{4}[-/.]", s):
            y, mo, day = map(int, re.split(r"[-/.]", s))
            d = date(y, mo, day)
        else:
            s = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", s, flags=re.I).replace(",", "").replace(".", "")
            parts = s.split()
            if parts[0].isdigit():
                day, mon, year = int(parts[0]), parts[1], int(parts[2])
            else:
                mon, day, year = parts[0], int(parts[1]), int(parts[2])
            d = date(year, MONTHS[mon[:3].lower()], day)
        if not (2026 <= d.year <= date.today().year + 4):
            return None
        return d.isoformat()
    except (ValueError, TypeError, KeyError, AttributeError):
        return None

def event_match(name, race):
    if not name:
        return False
    name_tokens = set(re.findall(r"[a-z0-9]+", name.lower())) - COMMON
    race_tokens = set(re.findall(r"[a-z0-9]+", race["name"].lower())) - COMMON
    if not race_tokens:
        return False
    overlap = name_tokens & race_tokens
    return len(overlap) >= min(2, len(race_tokens)) or (
        len(overlap) >= 1 and len(race_tokens) <= 2 and
        ("marathon" in name.lower() or "ultra" in name.lower())
    )

def jsonld_nodes(soup):
    def traverse(obj):
        if isinstance(obj, list):
            for el in obj:
                yield from traverse(el)
        elif isinstance(obj, dict):
            yield obj
            for key in ("@graph", "mainEntity", "events", "subEvent"):
                if key in obj:
                    yield from traverse(obj[key])
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            yield from traverse(json.loads(tag.string or tag.get_text()))
        except (ValueError, TypeError):
            continue

def candidate(value, url, method):
    return {"value": value, "source_url": url, "method": method, "verification": "unverified"}

def extract(html, url, race):
    soup = BeautifulSoup(html[:1500000], "html.parser")
    detected = {}
    prices, restrictions = [], []
    for obj in jsonld_nodes(soup):
        typ = obj.get("@type", [])
        types = [typ] if isinstance(typ, str) else typ if isinstance(typ, list) else []
        if not any(t.endswith("Event") for t in types if isinstance(t, str)):
            continue
        if not event_match(str(obj.get("name", "")), race):
            continue
        if event_date := iso_date(obj.get("startDate")):
            if event_date >= date.today().isoformat():
                detected.setdefault("race_date", candidate(event_date, url, "JSON-LD Event.startDate"))
        offer_list = obj.get("offers") or []
        if isinstance(offer_list, dict):
            offer_list = [offer_list]
        if isinstance(offer_list, list):
            for offer in offer_list[:8]:
                if not isinstance(offer, dict):
                    continue
                for key, fields in (("entry_open_date", ["validFrom", "availabilityStarts"]), ("entry_close_date", ["validThrough", "availabilityEnds"])):
                    for field in fields:
                        val = iso_date(offer.get(field))
                        if val:
                            detected.setdefault(key, candidate(val, url, "JSON-LD offer."+field))
                if offer.get("price") is not None and offer.get("priceCurrency"):
                    txt = str(offer["priceCurrency"]) + " " + str(offer["price"])
                    if len(txt) <= 40:
                        prices.append({"text": txt, "source_url": url, "method": "JSON-LD offer", "verification":"unverified"})
    for node in soup(["script", "style", "footer", "nav", "noscript"]):
        node.decompose()
    headings = " ".join(tag.get_text(" ", strip=True) for tag in soup.select("title, h1")[:6])
    page_matches_event = event_match(headings, race)
    chunks = [re.sub(r"\s+", " ", s).strip() for s in soup.stripped_strings]
    # Keep local context rather than scanning dates against the whole page:
    # this reduces unrelated news headlines and other events being misassigned.
    for idx, chunk in enumerate(chunks):
        if not chunk:
            continue
        neighbors = " ".join(chunks[idx:idx+3])[:220]
        for key, rx in DATE_LABEL.items():
            if key in detected:
                continue
            # Generic registration calendars often contain dates for OTHER
            # races. Only infer race day when this page names the race.
            if key == "race_date" and not page_matches_event:
                continue
            label = rx.search(chunk)
            if not label:
                continue
            # Need a date after the relevant label; require an explicit year.
            window = (chunk[label.end():] + " " + " ".join(chunks[idx+1:idx+3]))[:150]
            if parsed := iso_date(window):
                if key != "race_date" or parsed >= date.today().isoformat():
                    detected[key] = candidate(parsed, url, "Date next to entry/race label")
        # Capture potential entry pricing only when fee wording is nearby.
        if len(prices) < 4 and len(chunk) < 300 and re.search(r"fee|price|entry|registration|参加費|エントリー料金", neighbors, re.I):
            if match := PRICE_RX.search(neighbors[:140]):
                value = match.group(0).strip()
                if value not in [p["text"] for p in prices]:
                    prices.append({"text": value, "source_url": url, "method": "Page text", "verification":"unverified"})
        if len(restrictions) < 4 and len(chunk) < 280 and RULE_RX.search(chunk):
            if chunk not in [p["text"] for p in restrictions]:
                restrictions.append({"text": chunk[:180], "source_url":url, "verification":"unverified"})
    if prices:
        detected["prices"] = prices[:4]
    if restrictions:
        detected["restrictions"] = restrictions[:4]
    return detected, soup

def linked_registration_page(soup, source_url):
    hostname = (urlparse(source_url).hostname or "").removeprefix("www.")
    choices = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        label = " ".join(a.stripped_strings).lower()
        link = urljoin(source_url, href)
        parsed = urlparse(link)
        host = (parsed.hostname or "").removeprefix("www.")
        if parsed.scheme not in ("https", "http") or not host or host != hostname:
            continue
        if parsed.path.lower().endswith((".pdf",".jpg",".png",".zip")):
            continue
        score = 0
        target = (label + " " + parsed.path.lower())
        if re.search(r"\b(?:enter|entries|entry|register|registration|ballot|apply)\b|エントリー|申込み|申込", target):
            score += 3
        if re.search(r"\b(?:fee|price|eligib|requirements|race info|event info)\b|大会要項|募集要項", target):
            score += 1
        if score and parsed.path not in ("", "/"):
            choices.append((score, link.split("#")[0]))
    choices.sort(key=lambda x: -x[0])
    return choices[0][1] if choices else None

def merge_detected(primary, secondary):
    merged = dict(primary)
    for key, value in secondary.items():
        if key in ("prices","restrictions"):
            seen={x["text"] for x in merged.get(key,[])}
            merged.setdefault(key,[])
            for item in value:
                if item["text"] not in seen and len(merged[key])<4:
                    merged[key].append(item)
                    seen.add(item["text"])
        else:
            merged.setdefault(key,value)
    return merged
