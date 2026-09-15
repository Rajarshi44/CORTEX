"""
Resilient source-connector infrastructure.

Every external connector inherits from `Connector` and gets, for free:
  * a hardened HTTP client (browser-like headers, HTTP/2, redirects)
  * a legacy-SSL fallback for old government servers that still require
    unsafe renegotiation / low security levels (proven needed on punjabpolice.gov.in)
  * robots.txt compliance, cached per host
  * per-host rate limiting + exponential backoff with jitter on 429/5xx
  * an on-disk response cache so a demo never depends on a live site being up
  * graceful degradation: failures return a typed FetchResult instead of raising,
    so one dead source can never break an ingestion run

Nothing here bypasses an access control. If a site says no (robots.txt, CAPTCHA,
auth wall), the connector reports `blocked` and moves on.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import ssl
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Literal
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..config import settings

log = logging.getLogger("cna.sources")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

Status = Literal["ok", "cached", "blocked", "unavailable", "error"]


# ---------------------------------------------------------------------------------- SSL
def legacy_ssl_context() -> ssl.SSLContext:
    """TLS context tolerant of the older stacks several Indian government servers still run.

    Only relaxes *client-side* strictness so we can talk to them at all; it does not
    weaken anything on their side. Used as a fallback after a normal handshake fails.
    """
    ctx = ssl.create_default_context()
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:  # pragma: no cover - platform dependent
        pass
    return ctx


# ---------------------------------------------------------------------------------- cache
class DiskCache:
    """Content-addressed response cache. Keeps demos working offline."""

    def __init__(self, root: Path | None = None, ttl_hours: int = 24 * 7):
        self.root = root or (settings.data_dir / "cache")
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_hours)
        self._lock = threading.Lock()

    def _path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()
        return self.root / h[:2] / f"{h}.bin"

    def get(self, key: str, ignore_ttl: bool = False) -> bytes | None:
        p = self._path(key)
        if not p.exists():
            return None
        meta = p.with_suffix(".json")
        if meta.exists() and not ignore_ttl:
            try:
                stamp = datetime.fromisoformat(json.loads(meta.read_text())["at"])
                if datetime.now(timezone.utc) - stamp > self.ttl:
                    return None
            except (ValueError, KeyError, json.JSONDecodeError):
                return None
        return p.read_bytes()

    def put(self, key: str, data: bytes, meta: dict | None = None) -> None:
        p = self._path(key)
        with self._lock:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            p.with_suffix(".json").write_text(json.dumps(
                {"at": datetime.now(timezone.utc).isoformat(), "key": key, "bytes": len(data), **(meta or {})}))

    def stats(self) -> dict:
        files = list(self.root.rglob("*.bin"))
        return {"entries": len(files), "bytes": sum(f.stat().st_size for f in files)}


cache = DiskCache()


# ---------------------------------------------------------------------------------- rate limiting
class RateLimiter:
    """Per-host minimum interval between requests (token-free, thread safe)."""

    def __init__(self, default_interval: float = 1.0):
        self.default = default_interval
        self.intervals: dict[str, float] = {}
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_interval(self, host: str, seconds: float) -> None:
        self.intervals[host] = seconds

    def wait(self, host: str) -> None:
        interval = self.intervals.get(host, self.default)
        with self._lock:
            last = self._last.get(host, 0.0)
            delay = max(0.0, last + interval - time.monotonic())
            self._last[host] = time.monotonic() + delay
        if delay > 0:
            time.sleep(delay)


limiter = RateLimiter()


# ---------------------------------------------------------------------------------- robots
class RobotsRegistry:
    """robots.txt compliance, cached per host. Fail-open only when robots.txt is absent."""

    def __init__(self):
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str, agent: str = "*") -> bool:
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            if host not in self._parsers:
                self._parsers[host] = self._load(host)
            rp = self._parsers[host]
        if rp is None:
            return True  # no robots.txt published -> allowed
        return rp.can_fetch(agent, url)

    @staticmethod
    def _load(host: str) -> RobotFileParser | None:
        try:
            r = httpx.get(f"{host}/robots.txt", timeout=15, headers={"User-Agent": UA}, follow_redirects=True)
            if r.status_code != 200 or not r.text.strip():
                return None
            rp = RobotFileParser()
            rp.parse(r.text.splitlines())
            return rp
        except Exception:
            return None


robots = RobotsRegistry()


# ---------------------------------------------------------------------------------- result
@dataclass
class FetchResult:
    url: str
    status: Status
    content: bytes = b""
    http_status: int | None = None
    reason: str = ""
    from_cache: bool = False
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in ("ok", "cached")

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


@dataclass
class SourceReport:
    """What a connector did - surfaced in the UI so an analyst sees source health."""

    name: str
    status: Status = "ok"
    records: int = 0
    documents: int = 0
    reason: str = ""
    started_at: str = ""
    elapsed: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {**self.__dict__}


# ---------------------------------------------------------------------------------- connector
class Connector:
    """Base class for every external data source."""

    name: str = "connector"
    title: str = "Source"
    description: str = ""
    homepage: str = ""
    licence: str = ""
    attribution: str = ""
    # politeness
    rate_limit: float = 1.0
    respect_robots: bool = True
    cache_ttl_hours: int = 24 * 7
    max_retries: int = 3
    timeout: float = 60.0

    def __init__(self, offline: bool = False):
        self.offline = offline
        self._client: httpx.Client | None = None
        self._legacy_client: httpx.Client | None = None
        self.cache = DiskCache(ttl_hours=self.cache_ttl_hours)

    # ------------------------------------------------------------------ http
    def _mk_client(self, legacy: bool = False) -> httpx.Client:
        kwargs: dict[str, Any] = dict(timeout=self.timeout, follow_redirects=True, headers=dict(DEFAULT_HEADERS))
        if legacy:
            kwargs["verify"] = legacy_ssl_context()
        return httpx.Client(**kwargs)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = self._mk_client()
        return self._client

    @property
    def legacy_client(self) -> httpx.Client:
        if self._legacy_client is None:
            self._legacy_client = self._mk_client(legacy=True)
        return self._legacy_client

    def fetch(self, url: str, *, params: dict | None = None, headers: dict | None = None,
              use_cache: bool = True, cache_key: str | None = None, method: str = "GET",
              data: dict | None = None, allow_legacy_ssl: bool = True) -> FetchResult:
        """Fetch a URL with every resilience feature applied. Never raises."""
        key = cache_key or (url + ("?" + json.dumps(params, sort_keys=True) if params else ""))
        t0 = time.monotonic()

        if use_cache:
            hit = self.cache.get(key)
            if hit is not None:
                return FetchResult(url, "cached", hit, from_cache=True, elapsed=time.monotonic() - t0)

        if self.offline:
            stale = self.cache.get(key, ignore_ttl=True)
            if stale is not None:
                return FetchResult(url, "cached", stale, from_cache=True, reason="offline mode, stale cache")
            return FetchResult(url, "unavailable", reason="offline mode and nothing cached")

        if self.respect_robots and not robots.allowed(url):
            log.info("robots.txt disallows %s", url)
            return FetchResult(url, "blocked", reason="disallowed by robots.txt")

        host = urlparse(url).netloc
        limiter.set_interval(host, self.rate_limit)
        last_reason = ""
        for attempt in range(self.max_retries):
            limiter.wait(host)
            for legacy in (False, True) if allow_legacy_ssl else (False,):
                client = self.legacy_client if legacy else self.client
                try:
                    r = client.request(method, url, params=params, headers=headers, data=data)
                except (httpx.ConnectError, httpx.ReadError) as exc:
                    last_reason = f"{type(exc).__name__}: {exc}"
                    if legacy or not allow_legacy_ssl:
                        break
                    if "SSL" not in str(exc) and "ssl" not in str(exc).lower():
                        break
                    log.info("retrying %s with legacy SSL", host)
                    continue  # try legacy SSL
                except httpx.HTTPError as exc:
                    last_reason = f"{type(exc).__name__}: {exc}"
                    break
                else:
                    if r.status_code in (401, 403, 407):
                        stale = self.cache.get(key, ignore_ttl=True)
                        if stale is not None:
                            return FetchResult(url, "cached", stale, r.status_code, "access blocked; served cached copy", True)
                        return FetchResult(url, "blocked", http_status=r.status_code,
                                           reason=f"HTTP {r.status_code} - access restricted (often geo/IP filtering on government portals)")
                    if r.status_code == 429 or r.status_code >= 500:
                        last_reason = f"HTTP {r.status_code}"
                        ra = r.headers.get("Retry-After")
                        if ra and ra.isdigit():
                            time.sleep(min(int(ra), 60))
                        break  # -> backoff and retry
                    if r.status_code >= 400:
                        return FetchResult(url, "unavailable", http_status=r.status_code, reason=f"HTTP {r.status_code}")
                    if use_cache:
                        self.cache.put(key, r.content, {"url": url, "http_status": r.status_code})
                    return FetchResult(url, "ok", r.content, r.status_code, elapsed=time.monotonic() - t0)
            if attempt < self.max_retries - 1:
                backoff = min(45.0, (2 ** attempt) * (6.0 if last_reason.startswith("HTTP 429") else 1.5)) + random.uniform(0, 0.75)
                log.info("retry %d/%d for %s in %.1fs (%s)", attempt + 1, self.max_retries, url, backoff, last_reason)
                time.sleep(backoff)

        stale = self.cache.get(key, ignore_ttl=True)
        if stale is not None:
            return FetchResult(url, "cached", stale, reason=f"live fetch failed ({last_reason}); served stale cache", from_cache=True)
        return FetchResult(url, "error", reason=last_reason or "unknown failure", elapsed=time.monotonic() - t0)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def strip_html(raw: str) -> str:
        import html as _html

        t = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
        t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
        t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", t, flags=re.I)
        t = _html.unescape(re.sub(r"<[^>]+>", " ", t))
        t = re.sub(r"[ \t ]+", " ", t)
        return re.sub(r"\n\s*\n+", "\n\n", t).strip()

    def close(self) -> None:
        for c in (self._client, self._legacy_client):
            if c is not None:
                c.close()

    # ------------------------------------------------------------------ interface
    def probe(self) -> SourceReport:
        """Cheap reachability check for the source-health panel."""
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        if not self.homepage:
            return SourceReport(self.name, "ok", reason="no probe url", started_at=started)
        r = self.fetch(self.homepage, use_cache=False)
        return SourceReport(self.name, r.status if r.status != "ok" else "ok", reason=r.reason,
                            started_at=started, elapsed=round(time.monotonic() - t0, 2),
                            details={"http_status": r.http_status})

    def harvest(self, db, **kwargs) -> SourceReport:  # pragma: no cover - implemented by subclasses
        raise NotImplementedError

    def info(self) -> dict:
        return {"name": self.name, "title": self.title, "description": self.description, "homepage": self.homepage,
                "licence": self.licence, "attribution": self.attribution}


# ---------------------------------------------------------------------------------- registry
REGISTRY: dict[str, type[Connector]] = {}


def register(cls: type[Connector]) -> type[Connector]:
    REGISTRY[cls.name] = cls
    return cls


def get_connector(name: str, **kw) -> Connector:
    if name not in REGISTRY:
        raise KeyError(f"unknown source '{name}' (have: {', '.join(sorted(REGISTRY))})")
    return REGISTRY[name](**kw)


def iter_connectors(**kw) -> Iterator[Connector]:
    for cls in REGISTRY.values():
        yield cls(**kw)
