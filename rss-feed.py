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
    author, dc:creator      employer, as the kicker (RSS_ITEM1_AUTHOR)
    enclosure, media:content  the ad's picture, JPEG, 16:9 (RSS_ITEM1_IMAGE)
    media:title             the picture's alt text
    category                the ad's tags, without "stillinger"
    nl:extra1               employer's logo, JPEG, or empty
    nl:extra2               application deadline, "05.01.2027" or "Løpende"
    nl:extra3               place of work, as the subtitle
    nl:extra4               "20-50 %"
    nl:extra5               "Fast", "Vikariat" ...

Same ads as the front: those whose "Skjul fra forsiden" (hidefromfp_time)
is in the future. Employer and place are the kicker and subtitle, as on
the cards; the rest comes from each ad's data element, with the API's
hidefromfp_time and teaserKicker when an ad has none. Email clients don't all show WebP, so every image is JPEG.

The nl: namespace URI is the one MAKE's article gives; check in MAKE that
the extra fields come through before relying on them.

Usage:
    python3 rss-feed.py                  # -> site/stillinger.xml
    python3 rss-feed.py --out feed.xml --self https://.../feed.xml
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site" / "stillinger.xml"
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


def deadline(f: dict, ad: dict, now: float) -> str:
    if f.get("soknadsfrist"):
        return f["soknadsfrist"]
    t = int(ad.get("hidefromfp_time") or 0)
    if t - now > OPEN_ENDED_DAYS * 86400:
        return "Løpende"
    return datetime.fromtimestamp(t, timezone.utc).astimezone().strftime("%d.%m.%Y")


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


def item(ad: dict, now: float) -> str:
    link = (ad.get("siteDomain") or SITE) + (ad.get("published_url") or f"/a/{ad['id']}")
    f = facts(fetch(link))
    # Kicker and subtitle first: the short forms the front's cards show.
    employer = clean(ad.get("kicker")) or f.get("arbeidsgiver", "")
    place = clean(ad.get("subtitle")) or f.get("arbeidssted", "")
    img = image_url(ad)
    published = datetime.fromisoformat(ad["published"])

    lines = [
        f"<title>{cdata(clean(ad.get('title')))}</title>",
        f"<link>{escape(link)}</link>",
        f'<guid isPermaLink="false">{escape(SITE)}/a/{ad["id"]}</guid>',
        f"<pubDate>{format_datetime(published)}</pubDate>",
        f"<description>{cdata(first_paragraph(ad))}</description>",
        f"<author>{cdata(employer)}</author>",
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--self", dest="self_url", help="the URL the feed is served at")
    args = ap.parse_args()

    now = time.time()
    active = [a for a in ads() if int(a.get("hidefromfp_time") or 0) > now]
    active.sort(key=lambda a: a.get("published") or "", reverse=True)
    if not active:
        # More likely an API hiccup than an empty site. Keeping the last feed
        # is harmless: MAKE only takes items newer than its last run.
        sys.exit("error: no active ads; nothing written")

    xmlns = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())
    head = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<rss version="2.0" {xmlns}>',
        "  <channel>",
        "    <title>Dagen Stilling: ledige stillinger</title>",
        f"    <link>{SITE}/</link>",
        "    <description>Ledige stillinger på stilling.dagen.no</description>",
        "    <language>nb</language>",
        f"    <lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>",
    ]
    if args.self_url:
        head.append(f'    <atom:link href={quoteattr(args.self_url)} rel="self"'
                    ' type="application/rss+xml" />')
    body = "".join(item(a, now) for a in active)
    xml = "\n".join(head) + "\n" + body + "  </channel>\n</rss>\n"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(xml, encoding="utf-8")
    print(f"{len(active)} ads -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
