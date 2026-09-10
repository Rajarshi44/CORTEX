"""
Optional LLM layer, served through OpenRouter (OpenAI-compatible chat completions).

The system is fully functional without it. When a key is configured it (a) augments
rule-based NER on unstructured text as extraction tier 3, and (b) writes natural-language
investigator briefings grounded in retrieved graph facts.

Two properties matter more here than model quality, because this output can end up as a
line on a chart that names a real person:

  * SPAN GROUNDING - the model must return the exact verbatim quote it based each relation
    on. The quote is checked against the source text; anything that does not appear is
    dropped. A hallucinated relationship is therefore structurally impossible to store,
    rather than merely discouraged by the prompt.
  * REPRODUCIBILITY - temperature 0 plus a disk cache keyed by (model, text). A document is
    extracted once; re-running the pipeline yields identical relations, so the graph does not
    drift between runs.

Everything is tagged `extractor="llm"` downstream, which the chart draws as a dotted line and
the analyst can filter off entirely. Any failure degrades silently to the deterministic path.

Default model is a reasoning model, so `llm_reasoning_effort` defaults to "none": we want the
tool call, not the essay. Free-tier endpoints return 429/502 under load, which is retried.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import settings
from ..ingestion.ner import ExtractedRelation, ExtractionResult, Mention
from ..ingestion.quality import is_junk

log = logging.getLogger("cna.llm")

REL_TYPES = ["MET", "REPORTS_TO", "USES_PHONE", "RESIDES_AT", "ASSOCIATED_VEHICLE", "OWNS",
             "DIRECTOR_OF", "SEEN_AT", "COMMUNICATED_WITH", "ASSOCIATE_OF", "TRANSFERRED_TO"]

ENTITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "entities": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION", "BANK_ACCOUNT"]},
            "text": {"type": "string", "description": "exact surface text as it appears in the document"},
            "alias": {"type": "string"}, "role": {"type": "string"}}, "required": ["type", "text"]}},
        "relations": {"type": "array", "items": {"type": "object", "properties": {
            "source": {"type": "string"}, "target": {"type": "string"},
            "type": {"type": "string", "enum": REL_TYPES},
            "quote": {"type": "string", "description": "exact verbatim span from the document that states this relationship"}},
            "required": ["source", "target", "type", "quote"]}},
    },
    "required": ["entities", "relations"],
}

EXTRACT_PROMPT = (
    "You are an intelligence analyst reading Indian police / intelligence text.\n"
    "Extract every person, phone number, vehicle registration, organisation, bank account and location, "
    "plus the explicit relationships between them.\n"
    "Rules you must follow:\n"
    "  1. Use the EXACT surface text from the document for `text`; do not normalise or translate it.\n"
    "  2. A person written as 'X @ Y' has name X and alias Y.\n"
    "  3. For every relation give `quote`: the exact verbatim span of the document that states it. "
    "Copy it character for character. A relation without a real quote will be discarded.\n"
    "  4. Do NOT record a relationship the text denies, doubts or negates. "
    "'A denied meeting B' is not a MET relation.\n"
    "  5. Record only what the text states. Do not infer from world knowledge.\n\n"
    "DOCUMENT:\n"
)

NARRATE_SYSTEM = (
    "You are an investigative analyst assistant inside a criminal network analysis system used by Indian law "
    "enforcement. Answer the investigator's question using ONLY the supplied facts (JSON). Be precise: cite entity "
    "names, counts, dates and amounts from the facts; never invent details. Use short markdown with bold key names. "
    "Flag uncertainty explicitly. End with one line suggesting the next investigative step. "
    "Do not assert guilt; these are leads, not findings."
)

_RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


# --------------------------------------------------------------------------------- config
def available() -> bool:
    return bool(settings.llm_enabled and _api_key())


def _api_key() -> str | None:
    if settings.llm_provider == "anthropic":
        return settings.anthropic_api_key
    return settings.openrouter_api_key or settings.anthropic_api_key


def status() -> dict:
    """What the console reports on the AI panel."""
    return {"available": available(), "provider": settings.llm_provider, "model": settings.llm_model,
            "grounded": True, "cached": settings.llm_cache_enabled,
            "reasoning_effort": settings.llm_reasoning_effort}


# --------------------------------------------------------------------------------- cache
def _cache_path(kind: str, key: str) -> Path:
    d = settings.data_dir / "cache" / "llm" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def _cache_get(kind: str, key: str) -> Any | None:
    if not settings.llm_cache_enabled:
        return None
    p = _cache_path(kind, key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _cache_put(kind: str, key: str, value: Any) -> None:
    if not settings.llm_cache_enabled:
        return
    try:
        _cache_path(kind, key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:  # pragma: no cover - disk
        log.debug("llm cache write failed: %s", exc)


# --------------------------------------------------------------------------------- transport
def _post(body: dict) -> dict | None:
    """One chat-completion call with retry on the statuses free endpoints actually return."""
    key = _api_key()
    if not key:
        return None
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               # OpenRouter attribution headers; harmless elsewhere.
               "HTTP-Referer": "https://github.com/cortex-cna", "X-Title": "CORTEX Criminal Network Analysis"}
    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    delay = 2.0
    for attempt in range(settings.llm_max_retries + 1):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=settings.llm_timeout)
        except httpx.HTTPError as exc:
            log.warning("LLM transport error (attempt %d): %s", attempt + 1, exc)
            if attempt == settings.llm_max_retries:
                return None
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code in _RETRY_STATUS and attempt < settings.llm_max_retries:
            log.warning("LLM HTTP %s, retrying in %.0fs", r.status_code, delay)
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code != 200:
            log.warning("LLM HTTP %s: %s", r.status_code, r.text[:300])
            return None
        data = r.json()
        # OpenRouter reports upstream failures inside a 200 body
        if isinstance(data.get("error"), dict):
            msg = data["error"].get("message", "")
            if attempt < settings.llm_max_retries:
                log.warning("LLM upstream error, retrying: %s", msg[:160])
                time.sleep(delay)
                delay *= 2
                continue
            log.warning("LLM upstream error: %s", msg[:200])
            return None
        return data
    return None


def _body(messages: list[dict], *, max_tokens: int, tool: dict | None = None) -> dict:
    body: dict[str, Any] = {"model": settings.llm_model, "temperature": 0, "max_tokens": max_tokens,
                            "messages": messages}
    if tool:
        body["tools"] = [{"type": "function", "function": tool}]
        body["tool_choice"] = {"type": "function", "function": {"name": tool["name"]}}
    if settings.llm_reasoning_effort and settings.llm_reasoning_effort != "none":
        body["reasoning"] = {"effort": settings.llm_reasoning_effort}
    else:
        # The default model reasons before answering. With no `reasoning` key at all, some providers
        # return that reasoning inside `content` - so the console showed "The user is asking..., I
        # need to..." as the answer, then ran out of budget mid-sentence. Ask for it to be excluded.
        body["reasoning"] = {"exclude": True}
    return body


def _tool_arguments(data: dict) -> dict | None:
    """Pull the structured payload out, tolerating models that answer in prose with JSON inside."""
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError):
        return None
    for call in msg.get("tool_calls") or []:
        args = call.get("function", {}).get("arguments")
        if isinstance(args, dict):
            return args
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                continue
    content = msg.get("content") or ""
    m = re.search(r"\{.*\}", content, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


# --------------------------------------------------------------------------------- grounding
def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# "Salim Qureshi @ Salim Bhai" is one surface string but two facts. Models return it whole, so the
# alias is split off here rather than becoming part of the person's name on the chart.
_ALIAS_SPLIT_RE = re.compile(r"\s*(?:@|\balias\b|\burf\b)\s*", re.I)


def _split_alias(text: str) -> tuple[str, str | None]:
    parts = [p.strip(" ,.'\"") for p in _ALIAS_SPLIT_RE.split(text, maxsplit=1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return text, None


def _find_span(text: str, needle: str) -> int:
    """Locate `needle` in `text`, tolerating whitespace differences only. -1 if genuinely absent."""
    if not needle:
        return -1
    pos = text.find(needle)
    if pos >= 0:
        return pos
    # whitespace-insensitive fallback: the model reflowed a line break, the words are still real
    flat, target = _norm_ws(text).lower(), _norm_ws(needle).lower()
    return _norm_ws(text).lower().find(target) if target and target in flat else -1


# --------------------------------------------------------------------------------- extraction
def extract_entities_llm(text: str) -> ExtractionResult | None:
    """Extract entities and relations from law-enforcement prose, as rule-compatible objects.

    Every returned relation is backed by a quote that was verified to occur in `text`.
    """
    if not available() or len(text) < 40:
        return None
    snippet_text = text[:settings.llm_max_input_chars]
    key = _cache_key(settings.llm_model, "extract-v2", snippet_text)
    data = _cache_get("extract", key)
    if data is None:
        resp = _post(_body([{"role": "user", "content": EXTRACT_PROMPT + snippet_text}],
                           max_tokens=settings.llm_max_tokens,
                           tool={"name": "record_extraction",
                                 "description": "Record the entities and relationships found in the document",
                                 "parameters": ENTITY_SCHEMA}))
        if resp is None:
            return None
        data = _tool_arguments(resp)
        if data is None:
            log.warning("LLM returned no structured extraction (model may have exhausted its token budget on reasoning)")
            return None
        _cache_put("extract", key, data)

    mentions: list[Mention] = []
    by_text: dict[str, Mention] = {}
    for e in data.get("entities", []):
        surface = (e.get("text") or "").strip()
        if not surface or e.get("type") not in ("PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION", "BANK_ACCOUNT"):
            continue
        pos = snippet_text.find(surface)
        if pos < 0:  # not literally in the document: not a mention, whatever the model believes
            continue
        t, alias = (_split_alias(surface) if e["type"] == "PERSON" else (surface, None))
        alias = e.get("alias") or alias
        if t != surface:  # the span shrinks to the name, dropping the "@ alias" tail
            shift = surface.find(t)
            pos = pos + (shift if shift >= 0 else 0)
        if e["type"] == "PERSON":
            rejected, _why = is_junk("PERSON", t)
            if rejected:  # "his cousin", "the accused": grammar pointing at a person, not an identity
                continue
        attrs = {k: v for k, v in (("alias", alias), ("role", e.get("role"))) if v}
        m = Mention(e["type"], t, pos, pos + len(t), 0.8, attrs)
        mentions.append(m)
        by_text[t.lower()] = m
        if alias:  # so a relation naming the alias still resolves to this person
            by_text.setdefault(alias.lower(), m)
        if surface.lower() != t.lower():
            by_text.setdefault(surface.lower(), m)

    rels: list[ExtractedRelation] = []
    dropped = 0
    for r in data.get("relations", []):
        s = by_text.get((r.get("source") or "").strip().lower())
        t = by_text.get((r.get("target") or "").strip().lower())
        if not s or not t or s is t or r.get("type") not in REL_TYPES:
            dropped += 1
            continue
        quote = (r.get("quote") or r.get("evidence") or "").strip()
        if _find_span(snippet_text, quote) < 0:  # unverifiable claim, discard it
            dropped += 1
            continue
        rels.append(ExtractedRelation(s, t, r["type"], 0.75, quote[:300]))
    if dropped:
        log.info("LLM extraction: kept %d relations, dropped %d as ungrounded", len(rels), dropped)
    return ExtractionResult(mentions, rels, [], [])


# --------------------------------------------------------------------------------- narration
# Openers a reasoning model uses when it is thinking out loud rather than answering. Narration that
# starts this way is a monologue, not an answer, and the deterministic text it was asked to improve
# on is strictly better than a truncated transcript of the model talking to itself.
_MONOLOGUE_RE = re.compile(
    r"^\s*(?:the user (?:is |wants|asks|asked)|i (?:need|should|will|'ll|am asked|have)\b|"
    r"let me\b|okay[,.]|first[,.] i\b|we are given|looking at the (?:json|facts)|"
    r"based on the (?:json|provided json)\b)", re.I)
# The model's own reasoning tags, where a provider passes them through verbatim.
_THINK_RE = re.compile(r"<(?:think|thinking|reasoning)>.*?</(?:think|thinking|reasoning)>\s*", re.S | re.I)


def _usable_narration(text: str, finish_reason: str | None) -> str | None:
    """The narration if it is an answer, otherwise None so the caller keeps its own text.

    A reasoning model fails two ways here, and both are worse than the deterministic sentence the
    narration was asked to improve on: it thinks out loud into `content`, or it spends the budget
    thinking and the answer stops mid-word. The provider reports the second itself, so that is what
    is trusted rather than a guess from the text's length.
    """
    text = _THINK_RE.sub("", text).strip()
    if not text:
        return None
    if _MONOLOGUE_RE.search(text):
        log.info("narration rejected: reads as chain-of-thought, keeping the deterministic answer")
        return None
    if finish_reason == "length":
        log.info("narration rejected: hit the token ceiling mid-answer, keeping the deterministic answer")
        return None
    return text


def narrate(question: str, facts: dict, fallback: str) -> tuple[str, bool]:
    """Turn retrieved graph facts into an analyst-style answer. Returns (text, used_llm)."""
    if not available():
        return fallback, False
    payload = json.dumps(facts, default=str)[:settings.llm_max_input_chars]
    key = _cache_key(settings.llm_model, "narrate-v2", question, payload)
    cached = _cache_get("narrate", key)
    if cached:
        return cached, True
    resp = _post(_body([{"role": "system", "content": NARRATE_SYSTEM},
                        {"role": "user", "content": f"QUESTION: {question}\n\nFACTS:\n{payload}"}],
                       max_tokens=settings.llm_narrate_tokens))
    if resp is None:
        return fallback, False
    try:
        choice = resp["choices"][0]
        text = (choice["message"].get("content") or "").strip()
    except (KeyError, IndexError):
        return fallback, False
    good = _usable_narration(text, choice.get("finish_reason") or choice.get("native_finish_reason"))
    if good is None:
        return fallback, False
    _cache_put("narrate", key, good)
    return good, True


def strip_markdown(s: str) -> str:
    return re.sub(r"[*_`#]", "", s)
