#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

SOURCE_URL = "https://fwp.mt.gov/news/current-closures-restrictions/waterbody-closures"
OUTPUT_PATH = Path("river-restrictions.json")

RIVERS = {
    "bitterroot": {"name": "Bitterroot River", "heading": "Bitterroot River"},
    "blackfoot": {"name": "Blackfoot River", "heading": "Blackfoot River"},
    "clark-fork": {"name": "Clark Fork River", "heading": "Clark Fork River"},
    "rock-creek": {"name": "Rock Creek", "heading": "Rock Creek"},
}

HEADERS = {
    "User-Agent": "KingfisherFlyShopRestrictionsBot/2.0 (+https://kingfisherflyshop.com/)"
}

EVENT_STARTS = (
    "Closed to floating",
    "Hoot owl restrictions",
    "Fishing closure",
    "Emergency closure",
    "Closed to all forms of use",
)

def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()

def infer_type(text: str) -> str:
    lower = text.lower()
    if "closed to floating" in lower or "floating closure" in lower:
        return "Floating Closure"
    if "hoot owl" in lower:
        return "Hoot Owl Restriction"
    if "fishing prohibited 24 hours" in lower or "fishing closure" in lower:
        return "Fishing Closure"
    if "closed to all forms of use" in lower:
        return "Emergency Closure"
    if "closure" in lower or "closed" in lower:
        return "Closure"
    return "FWP Restriction"

def infer_effective_date(text: str) -> str:
    patterns = (
        r"\bstarting\s+([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)",
        r"\bbeginning\s+([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)",
        r"\beffective\s+([A-Z][a-z]+\s+\d{1,2}(?:,\s*\d{4})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""

def collect_section(heading: Tag) -> tuple[str, list[dict[str, str]]]:
    parts = []
    links = []

    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"h2", "h3"}:
            break
        if not isinstance(sibling, Tag):
            continue

        text = clean_text(sibling.get_text(" ", strip=True))
        if text:
            parts.append(text)

        for anchor in sibling.find_all("a", href=True):
            links.append({
                "label": clean_text(anchor.get_text(" ", strip=True)),
                "url": urljoin(SOURCE_URL, anchor["href"]),
            })

    return clean_text(" ".join(parts)), links

def split_events(text: str, links: list[dict[str, str]]) -> list[dict]:
    marker = "|".join(re.escape(x) for x in EVENT_STARTS)
    matches = list(re.finditer(rf"(?i)(?={marker})", text))

    chunks = []
    if matches:
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk = clean_text(text[match.start():end])
            if chunk:
                chunks.append(chunk)
    elif text:
        chunks = [text]

    events = []
    for index, chunk in enumerate(chunks):
        sentences = [
            clean_text(s)
            for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", chunk)
            if clean_text(s)
        ]

        title = sentences[0] if sentences else chunk
        bullets = sentences[1:] if len(sentences) > 1 else []

        # Remove link-label noise from the visible sentence.
        title = re.sub(r"\s+More information\s+Map\s+\(PDF\)\s*", " ", title, flags=re.I)
        title = clean_text(title)

        event_links = []
        if index == 0 and links:
            event_links = links

        events.append({
            "type": infer_type(chunk),
            "effective_date": infer_effective_date(chunk),
            "title": title,
            "bullets": bullets,
            "message": chunk,
            "url": event_links[0]["url"] if event_links else SOURCE_URL,
            "links": event_links,
        })

    return events

def empty_river(name: str) -> dict:
    return {
        "name": name,
        "restricted": False,
        "restriction_type": "",
        "effective_date": "",
        "message": "No current fishing restrictions reported.",
        "notice_count": 0,
        "notices": [],
    }

def scrape_page() -> dict[str, dict]:
    response = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    headings = {
        clean_text(h.get_text(" ", strip=True)).lower(): h
        for h in soup.find_all(["h2", "h3"])
    }

    if not headings:
        raise RuntimeError("FWP page returned no river headings")

    rivers = {}

    for key, config in RIVERS.items():
        heading = headings.get(config["heading"].lower())
        if heading is None:
            rivers[key] = empty_river(config["name"])
            continue

        body, links = collect_section(heading)
        if not body:
            rivers[key] = empty_river(config["name"])
            continue

        notices = split_events(body, links)
        if not notices:
            rivers[key] = empty_river(config["name"])
            continue

        rivers[key] = {
            "name": config["name"],
            "restricted": True,
            "restriction_type": notices[0]["type"],
            "effective_date": notices[0]["effective_date"],
            "message": body,
            "notice_count": len(notices),
            "notices": notices,
        }

    return rivers

def main() -> int:
    try:
        rivers = scrape_page()
    except Exception as exc:
        print(f"ERROR: Could not read FWP restrictions page: {exc}", file=sys.stderr)
        print("Existing river-restrictions.json was left unchanged.", file=sys.stderr)
        return 1

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_URL,
        "rivers": rivers,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for key, river in rivers.items():
        print(f"{key}: restricted={river['restricted']} notices={river['notice_count']}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
