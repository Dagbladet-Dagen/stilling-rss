#!/usr/bin/env python3
"""Builds an RSS feed of the active ads for MAKE (make.as), the newsletter.

The front page's script can't do this: it runs in the reader's browser,
and MAKE fetches a feed from its own servers without running any
JavaScript. A feed has to be XML at a URL, so this runs wherever that file
is served from, on a schedule.

Labrador's own feed (https://stilling.dagen.no/rss?lab_viewport=rss, from
the "rss" front set up 24.11.2026) gives MAKE the title, the place and the
picture. This one also carries the facts, in the elements MAKE reads
(support.make.as, "Design av RSS rader"):

    title                   job title
    link, guid              the ad
    pubDate                 when the ad was published. MAKE's recurring
                            send takes the items newer than its last run,
                            newest first; "Forskyv" skips the first N
    description             the ad's first paragraph (RSS_ITEM1_SUMMARY,
                            _SUMMARY_100, _SUMMARY_200)
    dc:creator              employer, as the kicker (RSS_ITEM1_AUTHOR;
                            RSS <author> must be an e-mail address)
    enclosure, media:content  the ad's picture, JPEG, 16:9 (RSS_ITEM1_IMAGE)
    media:title             the picture's alt text
    category                the ad's tags, without "stillinger"
    nl:extra1               employer's logo, JPEG, or empty
    nl:extra2               "Frist 6. desember", "Frist snarest" or "Løpende"
    nl:extra3               place of work, as the subtitle
    nl:extra4               "20-50 %"
    nl:extra5               "Fast", "Vikariat" ...

Same ads as the front: those whose "Skjul fra forsiden" (hidefromfp_time)
is in the future. Employer and place are the kicker and subtitle, as on
the cards; the rest comes from each ad's data element, with the API's
hidefromfp_time and teaserKicker when an ad has none. Email clients don't all show WebP, so every image is JPEG.

The nl: namespace URI is the one MAKE's article gives; check in MAKE that
the extra fields come through before relying on them.

Three feeds, because MAKE only takes items newer than its last run:

    stillinger.xml  every active ad, pubDate = published: "Nye denne uken"
    fremhevet.xml   open-ended ads ("Løpende"), pubDate = now: in every send
    eldre.xml       ads published before the last Friday 09:00 send,
                    shortest deadline first, pubDate = now minus a minute
                    per place, so MAKE keeps that order: "Fikk du med deg disse?"

Usage:
    python3 rss-feed.py                  # -> site/*.xml
    python3 rss-feed.py --base https://.../   # adds atom:link self
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"
UA = "Mozilla/5.0 (compatible; dagen-stilling-feed)"
SITE = "https://stilling.dagen.no"
QUERY = "lab_site_id:6 AND section:stillinger"
FIELDS = ["id", "title", "kicker", "subtitle", "tags", "section_tag", "image",
          "frontCropUrl", "altText", "published_url", "siteDomain",
          "hidefromfp_time", "published", "teaserKicker", "bodytext_style_json"]
IMAGE = "https://image.dagen.no/"
IMAGE_SIZE = (1200, 675)
# As in the carousel: a deadline more than a year off is no real deadline.
OPEN_ENDED_DAYS = 365

DATA = re.compile(r'<script type="text/plain" class="stilling-data">\n?(.*?)</script>', re.S)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "nl": "http://www.w3.org",
}


def fetch(url: str) -> str | None:
    res = subprocess.run(["curl", "-sSfL", "-m", "30", "-A", UA, url],
                         capture_output=True, check=False)
    if res.returncode:
        print(f"warning: could not fetch {url}: {res.stderr.decode().strip()}",
              file=sys.stderr)
        return None
    return res.stdout.decode("utf-8", errors="replace")


def ads() -> list[dict]:
    url = (f"https://api.dagen.no/api/v1/article/?query={quote(QUERY)}"
           f"&fields={','.join(FIELDS)}&limit=200&cb={int(time.time())}")
    body = fetch(url)
    if body is None:
        sys.exit("error: the API did not answer; nothing written")
    return json.loads(body).get("result") or []


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_key(s: str) -> str:
    s = s.strip().rstrip(":").lower()
    for a, b in (("æ", "ae"), ("ø", "o"), ("å", "a")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", s)


def facts(page: str | None) -> dict[str, str]:
    """The data element's lines, keyed like annonse.js (first value wins)."""
    out: dict[str, str] = {}
    m = DATA.search(page or "")
    if not m:
        return out
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = norm_key(key), clean(value)
        if value and key not in out:
            out[key] = value
    return out


def first_paragraph(ad: dict) -> str:
    try:
        doc = json.loads(ad.get("bodytext_style_json") or "{}")["editor-structure"]
    except (ValueError, KeyError, TypeError):
        return ""

    def text(node: dict) -> str:
        if node.get("type") == "text":
            return node.get("text", "")
        return "".join(text(c) for c in node.get("content", []))

    for node in doc.get("content", []):
        if node.get("type") == "paragraph":
            t = clean(text(node))
            if t:
                return t
    return ""


def image_url(ad: dict) -> str:
    crop = ad.get("frontCropUrl") or (f"?imageId={ad['image']}" if ad.get("image") else "")
    if not crop:
        return ""
    w, h = IMAGE_SIZE
    return f"{IMAGE}{ad.get('image', '')}.jpg{crop}&width={w}&height={h}&format=jpg"


def jpeg(url: str) -> str:
    """Labrador's image URLs, as JPEG; anything else as it is."""
    url = re.sub(r"^Logo:\s*", "", url, flags=re.I).strip()
    if not re.match(r"^https://\S+$", url):
        return ""
    return re.sub(r"(labrador\.media/_img/img)\.webp", r"\1.jpg", url)


MONTHS = ["januar", "februar", "mars", "april", "mai", "juni", "juli",
          "august", "september", "oktober", "november", "desember"]
OSLO = ZoneInfo("Europe/Oslo")
# The newsletter goes out Fridays at 09:00 Oslo time.
SEND_WEEKDAY, SEND_HOUR = 4, 9


def open_ended(ad: dict, now: float) -> bool:
    return int(ad.get("hidefromfp_time") or 0) - now > OPEN_ENDED_DAYS * 86400


def deadline(f: dict, ad: dict, now: float) -> str:
    """Ready to print: "Frist 6. desember", "Frist snarest" or "Løpende"."""
    raw = f.get("soknadsfrist", "")
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", raw)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"Frist {int(m.group(1))}. {MONTHS[int(m.group(2)) - 1]}"
    if raw.lower().startswith("løpende") or (not raw and open_ended(ad, now)):
        return "Løpende"
    if raw:
        return "Frist " + raw[0].lower() + raw[1:]
    d = datetime.fromtimestamp(int(ad["hidefromfp_time"]), OSLO)
    return f"Frist {d.day}. {MONTHS[d.month - 1]}"


def last_send(now: float) -> datetime:
    """The most recent Friday 09:00 in Oslo, at or before now."""
    local = datetime.fromtimestamp(now, OSLO)
    day = local.date() - timedelta(days=(local.weekday() - SEND_WEEKDAY) % 7)
    send = datetime(day.year, day.month, day.day, SEND_HOUR, tzinfo=OSLO)
    return send if send <= local else send - timedelta(days=7)


def tags(ad: dict) -> list[str]:
    hide = {"stillinger", (ad.get("section_tag") or "").lower()}
    seen, out = set(), []
    for t in (clean(x) for x in (ad.get("tags") or "").split(",")):
        if t and t.lower() not in hide and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def cdata(s: str) -> str:
    return "<![CDATA[" + s.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def item(ad: dict, f: dict, now: float, pub: datetime) -> str:
    link = (ad.get("siteDomain") or SITE) + (ad.get("published_url") or f"/a/{ad['id']}")
    # Kicker and subtitle first: the short forms the front's cards show.
    employer = clean(ad.get("kicker")) or f.get("arbeidsgiver", "")
    place = clean(ad.get("subtitle")) or f.get("arbeidssted", "")
    img = image_url(ad)

    lines = [
        f"<title>{cdata(clean(ad.get('title')))}</title>",
        f"<link>{escape(link)}</link>",
        f'<guid isPermaLink="false">{escape(SITE)}/a/{ad["id"]}</guid>',
        f"<pubDate>{format_datetime(pub)}</pubDate>",
        f"<description>{cdata(first_paragraph(ad))}</description>",
        f"<dc:creator>{cdata(employer)}</dc:creator>",
    ]
    if img:
        lines += [
            f'<enclosure url={quoteattr(img)} length="0" type="image/jpeg" />',
            f'<media:content url={quoteattr(img)} medium="image" type="image/jpeg"'
            f' width="{IMAGE_SIZE[0]}" height="{IMAGE_SIZE[1]}">'
            f"<media:title>{cdata(clean(ad.get('altText')))}</media:title>"
            "</media:content>",
        ]
    lines += [f"<category>{cdata(t)}</category>" for t in tags(ad)]
    lines += [
        f"<nl:extra1>{escape(jpeg(f.get('logo') or ad.get('teaserKicker') or ''))}</nl:extra1>",
        f"<nl:extra2>{cdata(deadline(f, ad, now))}</nl:extra2>",
        f"<nl:extra3>{cdata(place)}</nl:extra3>",
        f"<nl:extra4>{cdata(f.get('stillingsprosent', ''))}</nl:extra4>",
        f"<nl:extra5>{cdata(f.get('ansettelsesform', ''))}</nl:extra5>",
    ]
    return "    <item>\n" + "".join(f"      {x}\n" for x in lines) + "    </item>\n"


def write(path: Path, title: str, desc: str, items: list[str], base: str | None) -> None:
    xmlns = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())
    head = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<rss version="2.0" {xmlns}>',
        "  <channel>",
        f"    <title>{escape(title)}</title>",
        f"    <link>{SITE}/</link>",
        f"    <description>{escape(desc)}</description>",
        "    <language>nb</language>",
        f"    <lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>",
    ]
    if base:
        head.append(f'    <atom:link href={quoteattr(base + path.name)} rel="self"'
                    ' type="application/rss+xml" />')
    path.write_text("\n".join(head) + "\n" + "".join(items) + "  </channel>\n</rss>\n",
                    encoding="utf-8")
    print(f"{len(items):3} ads -> {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=OUT, help="folder for the feeds")
    ap.add_argument("--base", help="the URL the folder is served at, ending in /")
    args = ap.parse_args()

    now = time.time()
    built = datetime.now(timezone.utc).replace(microsecond=0)
    active = [a for a in ads() if int(a.get("hidefromfp_time") or 0) > now]
    if not active:
        # More likely an API hiccup than an empty site. Keeping the last feeds
        # is harmless: MAKE only takes items newer than its last run.
        sys.exit("error: no active ads; nothing written")
    for a in active:
        a["_f"] = facts(fetch((a.get("siteDomain") or SITE) +
                              (a.get("published_url") or f"/a/{a['id']}")))
        a["_pub"] = datetime.fromisoformat(a["published"])

    def fresh(group: list[dict]) -> list[str]:
        # Newer than any MAKE run, one minute apart, so MAKE keeps this order.
        return [item(a, a["_f"], now, built - timedelta(minutes=i))
                for i, a in enumerate(group)]

    newest = sorted(active, key=lambda a: a["_pub"], reverse=True)
    featured = [a for a in newest if open_ended(a, now)]
    cutoff = last_send(now)
    older = sorted((a for a in active
                    if not open_ended(a, now) and a["_pub"] < cutoff),
                   key=lambda a: (int(a["hidefromfp_time"]), -a["_pub"].timestamp()))

    args.out.mkdir(parents=True, exist_ok=True)
    write(args.out / "stillinger.xml", "Dagen Stilling: ledige stillinger",
          "Alle aktive stillinger, nyeste først, med publiseringsdato",
          [item(a, a["_f"], now, a["_pub"]) for a in newest], args.base)
    write(args.out / "fremhevet.xml", "Dagen Stilling: løpende stillinger",
          "Annonser uten fast frist, med i hver utsending", fresh(featured), args.base)
    write(args.out / "eldre.xml", "Dagen Stilling: fikk du med deg disse?",
          "Aktive stillinger fra før forrige nyhetsbrev, korteste frist først",
          fresh(older), args.base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
