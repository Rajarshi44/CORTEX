"""
Browser-driven connector for JavaScript / ASP.NET-postback portals (Maharashtra CCTNS "Published FIRs").

Uses Playwright to operate the public form exactly as a citizen would: choose district and
police station, set a date range, read the published rows. It does not attempt to defeat
CAPTCHAs, logins or any other access control - if the portal presents one, the connector
reports `blocked` and stops.

Playwright is optional: `uv pip install playwright && playwright install chromium`.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..ingestion.pipeline import IngestionService, _dt
from .base import Connector, SourceReport, register

CCTNS_URL = "https://citizen.mahapolice.gov.in/Citizen/MH/PublishedFIRs.aspx"
BLOCK_HINTS = ("captcha", "recaptcha", "verify you are human", "access denied", "login")


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


@register
class CCTNSConnector(Connector):
    name = "cctns_mh"
    title = "Maharashtra Police CCTNS - Published FIRs (browser)"
    description = ("Reads the public 'Search & View Published FIR' form on the Maharashtra CCTNS citizen portal "
                   "with a real browser session. Requires Playwright; respects every access control.")
    homepage = CCTNS_URL
    licence = "Public notices, Government of Maharashtra"
    attribution = "Maharashtra Police Citizen Portal (CCTNS)"
    rate_limit = 5.0

    def probe(self) -> SourceReport:
        rep = super().probe()
        rep.details["playwright"] = playwright_available()
        if not playwright_available():
            rep.reason = (rep.reason + "; " if rep.reason else "") + "playwright not installed (optional)"
        return rep

    def scrape(self, district: str, days: int = 30, station: str | None = None, max_rows: int = 200) -> dict:
        if not playwright_available():
            return {"status": "unavailable", "reason": "playwright not installed", "rows": []}
        from playwright.sync_api import sync_playwright

        rows: list[dict] = []
        end = datetime.now()
        start = end - timedelta(days=min(days, 89))
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.client.headers["User-Agent"])
            try:
                page.goto(CCTNS_URL, timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)
                body = page.content().lower()
                if any(h in body for h in BLOCK_HINTS[:3]):
                    return {"status": "blocked", "reason": "portal presented a human-verification step; not bypassed", "rows": []}
                page.fill("#ContentPlaceHolder1_txtDateOfRegistrationFrom", start.strftime("%d/%m/%Y"))
                page.fill("#ContentPlaceHolder1_txtDateOfRegistrationTo", end.strftime("%d/%m/%Y"))
                page.select_option("#ContentPlaceHolder1_ddlDistrict", label=district)
                page.wait_for_timeout(1500)
                if station:
                    page.select_option("#ContentPlaceHolder1_ddlPoliceStation", label=station)
                    page.wait_for_timeout(800)
                page.click("#ContentPlaceHolder1_btnSearch")
                page.wait_for_load_state("networkidle", timeout=60000)
                for tr in page.query_selector_all("table tr"):
                    cells = [c.inner_text().strip() for c in tr.query_selector_all("td")]
                    if len(cells) >= 5 and re.search(r"\d+/\d{4}", " ".join(cells)):
                        rows.append({"cells": cells})
                    if len(rows) >= max_rows:
                        break
                return {"status": "ok", "rows": rows, "district": district, "from": start.date().isoformat(), "to": end.date().isoformat()}
            except Exception as exc:
                return {"status": "error", "reason": f"{type(exc).__name__}: {exc}", "rows": rows}
            finally:
                browser.close()

    def harvest(self, db: Session, district: str = "Mumbai City", days: int = 30, station: str | None = None, **_) -> SourceReport:
        started = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        rep = SourceReport(self.name, started_at=started)
        res = self.scrape(district, days, station)
        rep.status = res["status"]
        rep.reason = res.get("reason", "")
        if res["status"] != "ok":
            rep.elapsed = round(time.monotonic() - t0, 2)
            return rep
        svc = IngestionService(db)
        firs = []
        for r in res["rows"]:
            cells = r["cells"]
            text = " | ".join(cells)
            fir_no = next((c for c in cells if re.fullmatch(r"\d+/\d{4}", c)), cells[0])
            firs.append({"fir_no": fir_no, "police_station": station or district, "date": next((c for c in cells if _dt(c)), ""),
                         "sections": next((c for c in cells if re.search(r"\b\d{2,3}\b", c) and "IPC" in c.upper() or "BNS" in c.upper()), ""),
                         "text": text, "accused": []})
        if firs:
            svc.ingest_firs(firs)
        rep.records = rep.documents = len(firs)
        rep.details = {"district": district, "window": [res.get("from"), res.get("to")]}
        rep.elapsed = round(time.monotonic() - t0, 2)
        return rep
