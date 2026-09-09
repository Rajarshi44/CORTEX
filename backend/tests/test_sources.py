"""Offline unit tests for the source-connector infrastructure and parsers (no network)."""
from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from app.sources import REGISTRY, base
from app.sources.courts import _party_type, _split_parties
from app.sources.indiagov import WantedListsConnector
from app.sources.news import _cdata


# ----------------------------------------------------------------------------- infra
def test_registry_has_all_connectors():
    assert {"gleif", "opensanctions", "icij", "courts", "benchmarks", "wanted", "news", "datagovin", "ncrb", "cctns_mh"} <= set(REGISTRY)
    for cls in REGISTRY.values():
        info = cls().info()
        assert info["licence"] and info["attribution"], f"{cls.name} must declare licence + attribution"


def test_disk_cache_roundtrip_and_ttl(tmp_path: Path):
    c = base.DiskCache(tmp_path, ttl_hours=1)
    assert c.get("k") is None
    c.put("k", b"hello", {"url": "x"})
    assert c.get("k") == b"hello"
    c.ttl = base.timedelta(seconds=-1)  # force expiry
    assert c.get("k") is None
    assert c.get("k", ignore_ttl=True) == b"hello"


def test_rate_limiter_spaces_requests():
    rl = base.RateLimiter(default_interval=0.15)
    t0 = time.monotonic()
    rl.wait("h")
    rl.wait("h")
    rl.wait("h")
    assert time.monotonic() - t0 >= 0.28


def test_offline_mode_serves_stale_cache_or_reports(tmp_path: Path, monkeypatch):
    conn = base.Connector(offline=True)
    conn.cache = base.DiskCache(tmp_path, ttl_hours=1)
    r = conn.fetch("https://example.invalid/x")
    assert r.status == "unavailable" and "offline" in r.reason
    conn.cache.put("https://example.invalid/x", b"cached-body")
    r = conn.fetch("https://example.invalid/x")
    assert r.ok and r.from_cache and r.content == b"cached-body"


def test_blocked_status_on_403(monkeypatch, tmp_path: Path):
    conn = base.Connector()
    conn.cache = base.DiskCache(tmp_path)
    monkeypatch.setattr(base.robots, "allowed", lambda url, agent="*": True)

    def fake_request(self, method, url, **kw):
        return httpx.Response(403, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.Client, "request", fake_request)
    r = conn.fetch("https://gov.example/portal", use_cache=False)
    assert r.status == "blocked" and r.http_status == 403


def test_robots_disallow_is_respected(monkeypatch, tmp_path: Path):
    conn = base.Connector()
    conn.cache = base.DiskCache(tmp_path)
    monkeypatch.setattr(base.robots, "allowed", lambda url, agent="*": False)
    r = conn.fetch("https://www.ncrb.gov.in/anything", use_cache=False)
    assert r.status == "blocked" and "robots" in r.reason


def test_legacy_ssl_context_is_permissive_client_side():
    ctx = base.legacy_ssl_context()
    assert ctx.check_hostname is False


# ----------------------------------------------------------------------------- parsers
@pytest.mark.parametrize("title,expected", [
    ("VIJAY SINGH @ VIJAY KR. SHARMA", ["VIJAY SINGH @ VIJAY KR. SHARMA"]),
    ("NARESH KUMAR & ANR.", ["NARESH KUMAR"]),
    ("RAM LAL AND OTHERS ETC.", ["RAM LAL"]),
    ("M/S LALTA PRASAD VAISH & SONS THROUGH ITS PARTNER", ["M/S LALTA PRASAD VAISH"]),
    ("THE STATE OF BIHAR", ["THE STATE OF BIHAR"]),
    ("KUMAR", []),
])
def test_split_parties(title, expected):
    assert _split_parties(title) == expected


def test_party_type():
    assert _party_type("THE STATE OF MAHARASHTRA") == "ORGANIZATION"
    assert _party_type("NARCOTICS CONTROL BUREAU") == "ORGANIZATION"
    assert _party_type("Sunita Devi") == "PERSON"


def test_wanted_name_cleaner_rejects_chrome():
    w = WantedListsConnector()
    assert w._clean_person("Hardeep Singh Nijjar") == "Hardeep Singh Nijjar"
    assert w._clean_person("Sandeep Dange Aliases") == "Sandeep Dange"
    for junk in ("text size increase", "Act Media Press Release Photo", "Proclaimed Offender", "Cases View",
                 "NIA National Investigation Agency", "Abu 123", "Ramchandra Kalsangra Sandeep Dange Junaid"):
        assert w._clean_person(junk) is None, junk


def test_wanted_alt_text_extraction():
    html = '<img alt="Abdul Majeed Sofi"><img alt="emblem"><img alt="Mubarak Shah"><p>Most wanted accused Junaid Ahmed absconding.</p>'
    names = WantedListsConnector().extract_names(html)
    assert names[:2] == ["Abdul Majeed Sofi", "Mubarak Shah"]
    assert "Junaid Ahmed" in names


def test_rss_cdata():
    assert _cdata("<![CDATA[Punjab cop <b>buys</b> drugs &amp; more]]>") == "Punjab cop buys drugs & more"
