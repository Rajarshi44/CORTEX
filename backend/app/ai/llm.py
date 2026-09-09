"""
Optional LLM layer (Anthropic Claude). The system is fully functional without it;
when CNA_ANTHROPIC_API_KEY is set it (a) augments rule-based NER on unstructured text and
(b) writes natural-language investigator briefings grounded in retrieved graph facts.

All calls are guarded: any failure degrades to the deterministic path.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

from ..config import settings
from ..ingestion.ner import ExtractedRelation, ExtractionResult, Mention

log = logging.getLogger("cna.llm")

ENTITY_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION", "BANK_ACCOUNT"]},
            "text": {"type": "string"}, "alias": {"type": "string"}, "role": {"type": "string"}}, "required": ["type", "text"]}},
        "relations": {"type": "array", "items": {"type": "object", "properties": {
            "source": {"type": "string"}, "target": {"type": "string"},
            "type": {"type": "string", "enum": ["MET", "REPORTS_TO", "USES_PHONE", "RESIDES_AT", "ASSOCIATED_VEHICLE", "OWNS",
                                                 "DIRECTOR_OF", "SEEN_AT", "COMMUNICATED_WITH", "ASSOCIATE_OF", "TRANSFERRED_TO"]},
            "evidence": {"type": "string"}}, "required": ["source", "target", "type"]}},
    },
    "required": ["entities", "relations"],
}


def available() -> bool:
    return bool(settings.llm_enabled and settings.anthropic_api_key)


@lru_cache(maxsize=1)
def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=40.0, max_retries=1)


def extract_entities_llm(text: str) -> ExtractionResult | None:
    """Ask Claude to extract entities/relations from law-enforcement text; returned as rule-compatible objects."""
    if not available() or len(text) < 40:
        return None
    prompt = (
        "You are an intelligence analyst. Extract every person, phone number, vehicle registration, organisation, "
        "bank account and location from the following Indian police / intelligence text, plus explicit relationships "
        "between them. Use the exact surface text for `text`. Persons get `alias` if written as 'X @ Y'. "
        "Return ONLY JSON matching the tool schema.\n\nTEXT:\n" + text[:6000]
    )
    try:
        resp = _client().messages.create(
            model=settings.llm_model, max_tokens=2048,
            tools=[{"name": "record_extraction", "description": "Record extracted entities and relations", "input_schema": ENTITY_SCHEMA}],
            tool_choice={"type": "tool", "name": "record_extraction"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # pragma: no cover - network
        log.warning("LLM extraction unavailable: %s", exc)
        return None
    data = next((b.input for b in resp.content if getattr(b, "type", "") == "tool_use"), None)
    if not data:
        return None
    mentions: list[Mention] = []
    by_text: dict[str, Mention] = {}
    for e in data.get("entities", []):
        t = (e.get("text") or "").strip()
        if not t:
            continue
        pos = text.find(t)
        if pos < 0:
            continue
        attrs = {k: v for k, v in (("alias", e.get("alias")), ("role", e.get("role"))) if v}
        m = Mention(e["type"], t, pos, pos + len(t), 0.8, attrs)
        mentions.append(m)
        by_text[t.lower()] = m
    rels: list[ExtractedRelation] = []
    for r in data.get("relations", []):
        s, t = by_text.get((r.get("source") or "").lower()), by_text.get((r.get("target") or "").lower())
        if s and t and s is not t:
            rels.append(ExtractedRelation(s, t, r["type"], 0.75, (r.get("evidence") or "")[:300]))
    return ExtractionResult(mentions, rels, [], [])


def narrate(question: str, facts: dict, fallback: str) -> tuple[str, bool]:
    """Turn retrieved graph facts into an analyst-style answer. Returns (text, used_llm)."""
    if not available():
        return fallback, False
    system = (
        "You are an investigative analyst assistant inside a criminal network analysis system used by Indian law enforcement. "
        "Answer the investigator's question using ONLY the supplied facts (JSON). Be precise, cite entity names, counts, dates "
        "and amounts from the facts; never invent details. Use short markdown with bold key names. Flag uncertainty. "
        "End with one line of suggested next investigative step."
    )
    try:
        resp = _client().messages.create(
            model=settings.llm_model, max_tokens=900, system=system,
            messages=[{"role": "user", "content": f"QUESTION: {question}\n\nFACTS:\n{json.dumps(facts, default=str)[:14000]}"}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content).strip()
        return (text or fallback), bool(text)
    except Exception as exc:  # pragma: no cover - network
        log.warning("LLM narration unavailable: %s", exc)
        return fallback, False


def strip_markdown(s: str) -> str:
    return re.sub(r"[*_`#]", "", s)
