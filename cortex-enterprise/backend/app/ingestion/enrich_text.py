"""
Fetch the body of documents that were stored as headlines only, then extract from the real text.

An RSS feed gives a headline and a one-line teaser. That is enough to know a story exists and
nothing like enough to learn who did what to whom, which is why the sheet ended up with 4,900
pieces of evidence and only fourteen of them extracted from prose. The relationships an
investigator wants - A was arrested with B, C was named by D - live in the article body.

This pass walks documents whose content is shorter than a paragraph, re-fetches the page they
came from, extracts the readable text, and re-runs entity and relation extraction over it. It is
polite (the shared connector honours robots.txt and per-host rate limits), idempotent (a document
already carrying a body is skipped), and safe to interrupt: each document is committed on its own.

    python -m app.ingestion.enrich_text --limit 40
    python -m app.ingestion.enrich_text --limit 40 --llm      # also run the tier-3 extractor
"""
from __future__ import annotations

import argparse
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Document
from ..sources.base import Connector

log = logging.getLogger("cna.enrich")

# Below this a "document" is a headline, not an account of anything.
THIN_CONTENT_CHARS = 400

# Page furniture that survives tag stripping and would otherwise become evidence.
BOILERPLATE = re.compile(
    r"(?:^|\n)\s*(?:advertisement|also read|read more|trending|subscribe|sign in|follow us|"
    r"download the app|click here|share this|photo credit|image credit|copyright|all rights reserved|"
    r"related stories|top stories|most popular|newsletter)\b.*", re.I)
WHITESPACE = re.compile(r"[ \t]*\n[ \t]*")


class _Fetcher(Connector):
    """Reuses the shared fetch stack: robots.txt, per-host rate limit, retries, disk cache."""

    name = "article"
    title = "Article body fetcher"
    description = "Re-fetches a stored document's own URL to recover its readable text."
    homepage = ""
    licence = "respects each publisher's robots.txt"

    def harvest(self, db: Session, **kwargs: Any):  # pragma: no cover - not a harvest source
        raise NotImplementedError


def readable_text(html: str) -> str:
    """Strip a page down to its prose. Deliberately simple: no extra dependency, and a bad
    extraction is visible as short output rather than as silent nonsense."""
    body = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form|noscript)[^>]*>.*?</\1>", " ", html)
    # article/main first; most Indian news sites mark one or the other
    m = re.search(r"(?is)<article[^>]*>(.*?)</article>", body) or re.search(r"(?is)<main[^>]*>(.*?)</main>", body)
    if m:
        body = m.group(1)
    text = Connector.strip_html(body)
    text = BOILERPLATE.sub("", text)
    text = WHITESPACE.sub("\n", text)
    # collapse the navigation debris that survives as many short lines
    lines = [ln.strip() for ln in text.split("\n")]
    keep = [ln for ln in lines if len(ln) > 40 or ln.endswith((".", "?", "!"))]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()


def enrich(db: Session, limit: int = 50, source_types: tuple[str, ...] = ("NEWS", "INTEL"),
           use_llm: bool = False, min_chars: int = THIN_CONTENT_CHARS, reextract: bool = False) -> dict[str, Any]:
    """`reextract` re-runs extraction over documents that already carry a body, which is what you
    want after an extraction pass failed but the fetched text was saved. Fetches come from the
    disk cache, so a re-extract costs no requests to the publisher."""
    from .pipeline import IngestionService
    from .provenance import source_url

    from ..db import Evidence

    docs = [d for d in db.execute(select(Document).where(Document.source_type.in_(source_types))).scalars()
            if reextract or len(d.content or "") < min_chars]
    # Resume rather than redo: a document that already carries extracted evidence is done. This
    # makes the pass restartable after an interruption without duplicating anything.
    done = {d for (d,) in db.execute(select(Evidence.document_id).distinct().where(
        Evidence.extractor.in_(("rules", "llm", "neural"))))}
    docs = [d for d in docs if d.id not in done][:limit]
    fetcher = _Fetcher()
    svc = IngestionService(db, use_llm=use_llm)
    report: dict[str, Any] = {"considered": len(docs), "fetched": 0, "skipped_no_url": 0,
                              "skipped_unreadable": 0, "failed": 0, "chars_before": 0, "chars_after": 0,
                              "entities_before": svc.resolver.new_entities, "examples": []}
    try:
        for d in docs:
            url = source_url(d.source_type, d.meta or {}, d.title or "")
            if not url or not url.startswith("http") or "search?" in url:
                report["skipped_no_url"] += 1
                continue
            r = fetcher.fetch(url, cache_key=f"article:{d.id}")
            if not r.ok:
                report["failed"] += 1
                continue
            text = readable_text(r.text)
            floor = min_chars if reextract else max(min_chars, len(d.content or ""))
            if len(text) < floor:
                report["skipped_unreadable"] += 1
                continue
            try:
                d.content = text[:40_000]
                # the body is new information about an existing document, so extraction re-runs over it
                res = svc.ner.extract(d.content)
                anchor = svc.resolver.resolve("REPORT", d.title[:120],
                                              {"document_id": d.id, "url": url, "source_type": d.source_type})
                svc._apply_extraction(d, d.content, res, d.occurred_at, anchor, extractor="rules")
                if use_llm:
                    svc._enrich(d, d.content, d.occurred_at, anchor)
                # Flush per document rather than once at the end: evidence rows carry a foreign key
                # onto their relationship, and a single batch across every article lets the inserts
                # be reordered under it. Small transactions also make the run interruptible.
                svc._finish()
            except Exception as exc:
                # A rollback un-persists entities the resolver still holds in its in-memory index,
                # so every later document would reference ids that no longer exist and fail too.
                # Rebuilding the service reloads that index from what is actually committed.
                db.rollback()
                svc = IngestionService(db, use_llm=use_llm)
                report["failed"] += 1
                report.setdefault("errors", []).append(f"{d.title[:48]}: {type(exc).__name__} {str(exc)[:90]}")
                log.warning("enrichment failed for %s: %s", d.title[:60], str(exc)[:200])
                continue
            report["chars_before"] += len(d.content or "")
            report["chars_after"] += len(text)
            report["fetched"] += 1
            if len(report["examples"]) < 5:
                report["examples"].append({"title": d.title[:60], "chars": len(text),
                                           "mentions": len(res.mentions), "relations": len(res.relations)})
    finally:
        fetcher.close()
    report["entities_created"] = svc.resolver.new_entities - report.pop("entities_before")
    report["relationships_created"] = svc.stats.relationships_created
    return report


if __name__ == "__main__":  # pragma: no cover
    import json

    from ..db import SessionLocal

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--llm", action="store_true", help="also run the tier-3 LLM extractor (slow)")
    ap.add_argument("--types", default="NEWS,INTEL")
    ap.add_argument("--reextract", action="store_true", help="re-run extraction over bodies already stored")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = SessionLocal()
    try:
        print(json.dumps(enrich(db, args.limit, tuple(args.types.split(",")), args.llm, reextract=args.reextract), indent=1, default=str))
    finally:
        db.close()
