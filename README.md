# stilling-rss

An RSS feed of the active job ads on [stilling.dagen.no](https://stilling.dagen.no),
for the weekly newsletter in MAKE (make.as).

**Feeds** (base https://dagbladet-dagen.github.io/stilling-rss/):

| Feed | Section | What |
| --- | --- | --- |
| `stillinger.xml` | Nye denne uken | every active ad, by publishing date |
| `fremhevet.xml`  | Ledige stillinger hos … | open-ended ads, in every send |
| `eldre.xml`      | Fikk du med deg disse? | ads from before the last send, shortest deadline first |

**Row designs** for MAKE are in `make/`: `to-per-rad.html` (2 ads),
`fullbredde.html` (1 ad with its heading), `liste-overskrift.html` and
`liste-rad.html` (1 line per row). `preview.py` fills them from the feeds:
https://dagbladet-dagen.github.io/stilling-rss/preview.html

`rss-feed.py` reads the ads from Labrador's public API and each ad's page,
and writes `site/stillinger.xml`. The workflow in `.github/workflows/feed.yml`
runs it every night and early Friday morning, commits the feed when the ads
change, and publishes it with GitHub Pages. Run it by hand under
Actions → Feed → Run workflow.

What each element holds, and how MAKE uses it, is at the top of
`rss-feed.py`. In short, per ad:

| MAKE merge code       | Content                        |
| --------------------- | ------------------------------ |
| `RSS_ITEMn_TITLE`     | Job title                      |
| `RSS_ITEMn_URL`       | The ad                         |
| `RSS_ITEMn_AUTHOR`    | Employer                       |
| `RSS_ITEMn_SUMMARY`   | The ad's first paragraph       |
| `RSS_ITEMn_IMAGE`     | The ad's picture, JPEG 16:9    |
| `RSS_ITEMn_EXTRA1`    | Employer logo (URL)            |
| `RSS_ITEMn_EXTRA2`    | "Frist 6. desember" / "Løpende" |
| `RSS_ITEMn_EXTRA3`    | Place of work                  |
| `RSS_ITEMn_EXTRA4`    | Percentage, e.g. "100 %"       |
| `RSS_ITEMn_EXTRA5`    | Employment type, e.g. "Fast"   |

`pubDate` is when the ad was published, so a recurring send takes the ads
published since the last one.

Everything here is public: the API, the ad pages and the feed. No tokens.
The site's own code is in the private repo `Dagbladet-Dagen/stilling`.

Try it locally (Python 3.9+, curl):

```bash
python3 rss-feed.py
```
