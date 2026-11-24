#!/usr/bin/env python3
"""Fills the MAKE row designs in make/ from the feeds in site/, the way MAKE
does, and writes site/preview.html: a rough look at the newsletter before
it is set up in MAKE. Header, intro and footer here are stand-ins; MAKE's
own blocks replace them.

    python3 rss-feed.py && python3 preview.py
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NL = "{http://www.w3.org}"
FONT = "'Schibsted Grotesk',Helvetica,Arial,sans-serif"


def items(feed: str) -> list[dict]:
    out = []
    for it in ET.parse(ROOT / "site" / feed).getroot().iter("item"):
        enc = it.find("enclosure")
        d = {"TITLE": it.findtext("title"), "URL": it.findtext("link"),
             "AUTHOR": it.findtext("author"), "SUMMARY": it.findtext("description"),
             "IMAGE": enc.get("url") if enc is not None else ""}
        for n in range(1, 6):
            d[f"EXTRA{n}"] = it.findtext(f"{NL}extra{n}") or ""
        out.append(d)
    return out


def row(design: str, feed: list[dict], offset: int) -> str:
    src = (ROOT / "make" / design).read_text(encoding="utf-8")
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)

    def fill(m: re.Match) -> str:
        i, key = offset + int(m.group(1)) - 1, m.group(2)
        return html.escape(feed[i][key] or "") if i < len(feed) else ""
    return re.sub(r"\{\{RSS_ITEM(\d)_([A-Z0-9_]+)\}\}", fill, src)


def heading(text: str) -> str:
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="background-color:#F5F5F5;"><tr><td style="padding:24px 20px 14px 20px;">'
            f'<span style="display:inline-block;border-left:3px solid #C4151C;padding-left:10px;'
            f'font-family:{FONT};font-size:18px;line-height:22px;font-weight:700;color:#1A1618;">'
            f'{text}</span></td></tr></table>')


def main() -> None:
    new, featured, older = items("stillinger.xml"), items("fremhevet.xml"), items("eldre.xml")
    rows = [
        f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border-bottom:1px solid #E4E0DF;">
<tr><td style="padding:18px 20px;"><img src="stilling-logo.png" width="130" alt="Dagen Stilling" style="display:block;"></td>
<td align="right" style="padding:18px 20px;font-family:{FONT};font-size:13px;"><a href="https://stilling.dagen.no/" style="color:#1A1618;text-decoration:none;">Alle stillinger</a></td></tr></table>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fff;"><tr><td style="padding:28px 20px 26px 20px;font-family:{FONT};">
<div style="width:36px;height:3px;background:#C4151C;margin-bottom:16px;"></div>
<div style="font-size:30px;line-height:36px;font-weight:700;color:#1A1618;">Ukens nye stillinger</div>
<div style="font-size:15px;line-height:22px;color:#4A4247;margin-top:10px;">Nye stillinger denne uken i kristne organisasjoner, menigheter, skoler og bedrifter over hele landet.</div>
</td></tr></table>''',
        heading("Nye denne uken"),
        row("to-per-rad.html", new, 0),
        row("to-per-rad.html", new, 2),
        row("fullbredde.html", featured, 0),
        row("liste-overskrift.html", older, 0),
        *(row("liste-rad.html", older, i) for i in range(min(5, len(older)))),
        '<table role="presentation" width="100%" style="background:#F5F5F5;"><tr><td height="24"></td></tr></table>',
    ]
    page = f'''<!doctype html>
<html lang="nb"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Forhåndsvisning: nyhetsbrev</title>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;700&display=swap" rel="stylesheet"></head>
<body style="margin:0;padding:24px 0;background:#EDEBEA;">
<div style="max-width:600px;margin:0 auto;border:1px solid #E4E0DF;border-radius:8px;overflow:hidden;background:#F5F5F5;">
{"".join(rows)}
</div></body></html>
'''
    (ROOT / "site" / "preview.html").write_text(page, encoding="utf-8")
    print("-> site/preview.html")


if __name__ == "__main__":
    main()
