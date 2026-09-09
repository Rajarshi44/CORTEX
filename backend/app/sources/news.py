"""Crime news RSS connector (Times of India, The Hindu, Indian Express). Live OSINT feed -> narrative NER."""
from __future__ import annotations

import html as _html
import re
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..ingestion.pipeline import IngestionService, _dt
from .base import Connector, SourceReport, register

FEEDS = {
    "toi_crime": ("Times of India - Crime", "https://timesofindia.indiatimes.com/rssfeeds/-2128932452.cms"),
    "toi_mumbai": ("Times of India - Mumbai", "https://timesofindia.indiatimes.com/rssfeeds/-2128838597.cms"),
    "hindu_national": ("The Hindu - National", "https://www.thehindu.com/news/national/feeder/default.rss"),
    "ie_mumbai": ("Indian Express - Mumbai", "https://indianexpress.com/section/cities/mumbai/feed/"),
}
CRIME_KW = re.compile(r"\b(arrest|police|accused|fir|ndps|drug|seiz|murder|extort|gang|fraud|launder|smuggl|kidnap|"
                      r"chargesheet|absconding|wanted|raid|custody|cbi|ed |nia|racket|hawala|scam|cyber)\w*", re.I)


def _cdata(s: str) -> str:
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


@register
class NewsConnector(Connector):
    name = "news"
    title = "Crime news feeds (TOI / The Hindu / Indian Express)"
    description = "Live open-source intelligence: crime reporting run through the same entity extraction pipeline."
    homepage = FEEDS["toi_crime"][1]
    licence = "Publisher RSS terms (headline + summary only, linked to source)"
    attribution = "Times of India, The Hindu, The Indian Express"
    rate_limit = 2.0
    cache_ttl_hours = 6

    def items(self, feed: str) -> list[dict]:
        label, url = FEEDS[feed]
        r = self.fetch(url, cache_key=f"rss:{feed}")
        if not r.ok:
            return []
        out = []
        for it in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            g = lambda tag: (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", it, re.S) or [None, ""])[1]  # noqa: E731
            title, desc, link, pub = _cdata(g("title")), _cdata(g("description")), _cdata(g("link")), _cdata(g("pubDate"))
            if title:
                out.append({"feed": label, "title": title, "summary": desc[:1500], "link": link, "published": pub})
        return out

    def harvest(self, db: Session, feeds: list[str] | None = None, crime_only: bool = True, limit: int = 60, **_) -> SourceReport:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        svc = IngestionService(db)
        n, per_feed, blocked = 0, {}, []
        for f in feeds or list(FEEDS):
            items = self.items(f)
            if not items:
                blocked.append(f)
                continue
            kept = 0
            for it in items:
                text = f"{it['title']}. {it['summary']}"
                if crime_only and not CRIME_KW.search(text):
                    continue
                svc.ingest_text("NEWS", f"{it['feed']}: {it['title'][:160]}", text,
                                {"link": it["link"], "published": it["published"], "feed": it["feed"], "source": "news"},
                                _dt(it["published"]), finish=False)
                kept += 1
                n += 1
                if n >= limit:
                    break
            per_feed[f] = kept
            if n >= limit:
                break
        svc._finish()
        rep.records = rep.documents = n
        rep.status = "ok" if n else "unavailable"
        rep.details = {"per_feed": per_feed, "unreachable": blocked}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep
