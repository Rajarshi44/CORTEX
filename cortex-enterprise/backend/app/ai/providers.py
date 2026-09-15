"""
Provider-agnostic tool-calling LLM layer.

The investigator agent needs one thing from a model: a streaming conversation that can call
tools. Three back-ends speak that dialect here - Google Gemini, NVIDIA NIM (OpenAI-compatible)
and Anthropic - behind one canonical message format and one normalised event stream, so the
agent loop never learns which vendor answered.

Canonical messages (Anthropic-shaped, because it is the most explicit of the three)::

    {"role": "user",      "content": [{"type": "text", "text": "..."}]}
    {"role": "assistant", "content": [{"type": "text", "text": "..."},
                                      {"type": "tool_use", "id": "t1", "name": "...", "input": {...}}]}
    {"role": "user",      "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "<json>"}]}

Normalised events yielded by `stream()`::

    ("text",  "delta")                              incremental assistant prose
    ("tool_use", {"id", "name", "input"})           a complete tool call
    ("done",  {"stop_reason", "usage", "provider"}) end of one assistant turn
    ("error", "reason")                             provider failed; caller may fall back

Every provider degrades to the next one in the chain, so a throttled key or a dead region
never takes the agent down.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger("cna.llm.providers")

Event = tuple[str, Any]

# JSON-Schema keywords the stricter (OpenAPI-derived) providers reject outright.
_UNSUPPORTED_SCHEMA_KEYS = {"$schema", "additionalProperties", "definitions", "$defs", "examples",
                            "default", "exclusiveMinimum", "exclusiveMaximum", "const", "patternProperties"}


def _env(*names: str, setting: str | None = None) -> str | None:
    """First of these environment variables that is set, else the matching `Settings` field.

    Both are checked because a key can arrive either way: exported in the shell, or written into
    a .env file that `Settings` parses under the `CNA_` prefix.
    """
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    if setting:
        v = getattr(settings, setting, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


# --------------------------------------------------------------------------------------- schema
def clean_schema(schema: dict, upper_types: bool = False) -> dict:
    """Strip JSON-Schema keywords the OpenAPI-subset providers choke on; optionally uppercase types."""
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in _UNSUPPORTED_SCHEMA_KEYS:
            continue
        if k == "type" and upper_types and isinstance(v, str):
            out[k] = v.upper()
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: clean_schema(pv, upper_types) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            out[k] = clean_schema(v, upper_types)
        elif k in ("anyOf", "oneOf") and isinstance(v, list):
            out[k] = [clean_schema(x, upper_types) for x in v]
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------------------- base
class Provider:
    key: str = ""
    label: str = ""
    model: str = ""

    def available(self) -> bool:
        return False

    def stream(self, system: str, messages: list[dict], tools: list[ToolSpec], max_tokens: int = 4096,
               temperature: float = 0.2) -> Iterator[Event]:  # pragma: no cover - interface
        raise NotImplementedError

    @staticmethod
    def _sse_data(resp: httpx.Response) -> Iterator[str]:
        """Yield the payload of every `data:` line in an SSE response."""
        for raw in resp.iter_lines():
            line = raw.decode() if isinstance(raw, bytes) else raw
            if line.startswith("data:"):
                yield line[5:].strip()


# --------------------------------------------------------------------------------------- Gemini
class GeminiProvider(Provider):
    """Google Gemini via the public generativelanguage REST endpoint (SSE streaming)."""

    key = "gemini"
    label = "Google Gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self):
        self.api_key = _env("CNA_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", setting="gemini_api_key")
        self.model = _env("CNA_GEMINI_MODEL", "GEMINI_MODEL", setting="gemini_model") or "gemini-2.5-flash"

    def available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _to_contents(messages: list[dict]) -> list[dict]:
        """Canonical messages -> Gemini `contents`.

        Gemini has no tool-call ids: it matches a functionResponse to a functionCall by name,
        which is why every tool_result block in this codebase also carries the tool's name.
        """
        contents: list[dict] = []
        for m in messages:
            parts: list[dict] = []
            for b in m["content"]:
                if b["type"] == "text" and b.get("text"):
                    parts.append({"text": b["text"]})
                elif b["type"] == "tool_use":
                    parts.append({"functionCall": {"name": b["name"], "args": b.get("input") or {}}})
                elif b["type"] == "tool_result":
                    payload = b.get("content")
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except json.JSONDecodeError:
                            payload = {"result": payload}
                    if not isinstance(payload, dict):
                        payload = {"result": payload}
                    parts.append({"functionResponse": {"name": b.get("name") or "tool", "response": payload}})
            if not parts:
                continue
            contents.append({"role": "model" if m["role"] == "assistant" else "user", "parts": parts})
        return contents

    def stream(self, system: str, messages: list[dict], tools: list[ToolSpec], max_tokens: int = 4096,
               temperature: float = 0.2) -> Iterator[Event]:
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._to_contents(messages),
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description,
                 "parameters": clean_schema(t.input_schema, upper_types=True)} for t in tools]}]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        url = f"{self.BASE}/{self.model}:streamGenerateContent"
        calls, usage, stop = 0, {}, "end_turn"
        with httpx.Client(timeout=httpx.Timeout(240.0, connect=20.0)) as client:
            with client.stream("POST", url, params={"alt": "sse", "key": self.api_key}, json=body) as resp:
                if resp.status_code >= 400:
                    yield ("error", f"gemini HTTP {resp.status_code}: {resp.read().decode('utf-8', 'replace')[:400]}")
                    return
                for data in self._sse_data(resp):
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if "error" in chunk:
                        yield ("error", f"gemini: {chunk['error'].get('message', 'unknown')}")
                        return
                    if um := chunk.get("usageMetadata"):
                        usage = {"input_tokens": um.get("promptTokenCount"), "output_tokens": um.get("candidatesTokenCount")}
                    for cand in chunk.get("candidates", []):
                        for part in (cand.get("content") or {}).get("parts", []):
                            if part.get("thought"):
                                continue
                            if part.get("text"):
                                yield ("text", part["text"])
                            if fc := part.get("functionCall"):
                                calls += 1
                                stop = "tool_use"
                                yield ("tool_use", {"id": f"gm{calls}_{fc['name']}", "name": fc["name"],
                                                    "input": fc.get("args") or {}})
                        if cand.get("finishReason") in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT"):
                            yield ("error", f"gemini stopped: {cand['finishReason']}")
                            return
        yield ("done", {"stop_reason": stop, "usage": usage, "provider": self.key, "model": self.model})


# --------------------------------------------------------------------------------------- NVIDIA NIM
class NvidiaNIMProvider(Provider):
    """NVIDIA NIM - OpenAI-compatible chat completions with tool calling."""

    key = "nvidia"
    label = "NVIDIA NIM"
    BASE = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(self):
        self.api_key = _env("CNA_NVIDIA_API_KEY", "NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY", "NGC_API_KEY", setting="nvidia_api_key")
        self.model = _env("CNA_NVIDIA_MODEL", "NVIDIA_MODEL", setting="nvidia_model") or "meta/llama-3.3-70b-instruct"
        self.base_url = _env("CNA_NVIDIA_BASE_URL", setting="nvidia_base_url") or self.BASE

    def available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _to_openai(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "assistant":
                text = "".join(b.get("text", "") for b in m["content"] if b["type"] == "text")
                calls = [{"id": b["id"], "type": "function",
                          "function": {"name": b["name"], "arguments": json.dumps(b.get("input") or {})}}
                         for b in m["content"] if b["type"] == "tool_use"]
                msg: dict[str, Any] = {"role": "assistant", "content": text or ""}
                if calls:
                    msg["tool_calls"] = calls
                out.append(msg)
                continue
            # A user turn carrying tool results becomes one `tool` message per result.
            for r in (b for b in m["content"] if b["type"] == "tool_result"):
                content = r.get("content")
                out.append({"role": "tool", "tool_call_id": r["tool_use_id"],
                            "content": content if isinstance(content, str) else json.dumps(content)})
            texts = [b["text"] for b in m["content"] if b["type"] == "text" and b.get("text")]
            if texts:
                out.append({"role": "user", "content": "\n".join(texts)})
        return out

    def stream(self, system: str, messages: list[dict], tools: list[ToolSpec], max_tokens: int = 4096,
               temperature: float = 0.2) -> Iterator[Event]:
        body: dict[str, Any] = {"model": self.model, "messages": self._to_openai(system, messages),
                                "stream": True, "temperature": temperature, "max_tokens": max_tokens}
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": clean_schema(t.input_schema)}}
                             for t in tools]
            body["tool_choice"] = "auto"
        pending: dict[int, dict] = {}
        usage, stop = {}, "end_turn"
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "text/event-stream"}
        with httpx.Client(timeout=httpx.Timeout(240.0, connect=20.0)) as client:
            with client.stream("POST", self.base_url, json=body, headers=headers) as resp:
                if resp.status_code >= 400:
                    yield ("error", f"nvidia HTTP {resp.status_code}: {resp.read().decode('utf-8', 'replace')[:400]}")
                    return
                for data in self._sse_data(resp):
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if u := chunk.get("usage"):
                        usage = {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")}
                    for ch in chunk.get("choices", []):
                        delta = ch.get("delta") or {}
                        if txt := delta.get("content"):
                            yield ("text", txt)
                        for tc in delta.get("tool_calls") or []:
                            slot = pending.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                            if tc.get("id"):
                                slot["id"] = tc["id"]
                            fn = tc.get("function") or {}
                            if fn.get("name"):
                                slot["name"] = fn["name"]
                            if fn.get("arguments"):
                                slot["args"] += fn["arguments"]
                        if ch.get("finish_reason") == "tool_calls":
                            stop = "tool_use"
        # Tool calls arrive as argument fragments, so they can only be emitted once the stream ends.
        for i in sorted(pending):
            slot = pending[i]
            if not slot["name"]:
                continue
            stop = "tool_use"
            try:
                args = json.loads(slot["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield ("tool_use", {"id": slot["id"] or f"nv{i}_{slot['name']}", "name": slot["name"], "input": args})
        yield ("done", {"stop_reason": stop, "usage": usage, "provider": self.key, "model": self.model})


# --------------------------------------------------------------------------------------- Anthropic
class AnthropicProvider(Provider):
    key = "anthropic"
    label = "Anthropic Claude"

    def __init__(self):
        self.api_key = _env("CNA_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", setting="anthropic_api_key")
        self.model = settings.llm_model

    def available(self) -> bool:
        return bool(self.api_key and settings.llm_enabled)

    def stream(self, system: str, messages: list[dict], tools: list[ToolSpec], max_tokens: int = 4096,
               temperature: float = 0.2) -> Iterator[Event]:
        try:
            import anthropic
        except ImportError:
            yield ("error", "anthropic sdk not installed")
            return
        client = anthropic.Anthropic(api_key=self.api_key, timeout=240.0, max_retries=1)
        payload = [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]
        # tool_result blocks carry a `name` for Gemini's benefit; Anthropic rejects the extra key.
        clean = [{"role": m["role"],
                  "content": [{k: v for k, v in b.items() if not (k == "name" and b["type"] == "tool_result")}
                              for b in m["content"]]} for m in messages]
        try:
            with client.messages.stream(model=self.model, max_tokens=max_tokens, system=system,
                                        tools=payload, messages=clean) as s:
                for ev in s:
                    if ev.type == "content_block_delta" and getattr(ev.delta, "type", "") == "text_delta":
                        yield ("text", ev.delta.text)
                final = s.get_final_message()
        except Exception as exc:
            yield ("error", f"anthropic: {exc}")
            return
        for b in final.content:
            if getattr(b, "type", "") == "tool_use":
                yield ("tool_use", {"id": b.id, "name": b.name, "input": b.input})
        yield ("done", {"stop_reason": final.stop_reason, "provider": self.key, "model": self.model,
                        "usage": {"input_tokens": final.usage.input_tokens, "output_tokens": final.usage.output_tokens}})


# --------------------------------------------------------------------------------------- chain
def provider_chain() -> list[Provider]:
    """Configured preference order, best first. `CNA_LLM_PROVIDERS` overrides (comma separated)."""
    catalogue = {p.key: p for p in (GeminiProvider(), NvidiaNIMProvider(), AnthropicProvider())}
    order = [s.strip().lower() for s in (_env("CNA_LLM_PROVIDERS", setting="llm_providers") or "gemini,nvidia,anthropic").split(",") if s.strip()]
    return [catalogue[k] for k in order if k in catalogue]


def available_providers() -> list[Provider]:
    return [p for p in provider_chain() if p.available()]


def status() -> dict:
    rows = [{"key": p.key, "label": p.label, "model": p.model, "available": p.available()} for p in provider_chain()]
    live = [r for r in rows if r["available"]]
    return {"providers": rows, "active": live[0] if live else None, "any": bool(live)}


def stream_with_fallback(system: str, messages: list[dict], tools: list[ToolSpec], max_tokens: int = 4096,
                         temperature: float = 0.2) -> Iterator[Event]:
    """Try each configured provider in turn.

    A provider that fails *before emitting anything* is skipped and the next one takes the turn.
    One that fails mid-answer surfaces the error instead: the turn is already partly spoken, and
    restarting it elsewhere would duplicate text in front of the analyst.
    """
    chain = available_providers()
    if not chain:
        yield ("error", "no LLM provider configured - set CNA_GEMINI_API_KEY, CNA_NVIDIA_API_KEY or CNA_ANTHROPIC_API_KEY")
        return
    last = ""
    for i, p in enumerate(chain):
        produced = False
        failed = False
        try:
            for kind, payload in p.stream(system, messages, tools, max_tokens, temperature):
                if kind == "error":
                    last, failed = str(payload), True
                    log.warning("provider %s failed: %s", p.key, last)
                    if produced:
                        yield ("error", last)
                        return
                    break
                produced = True
                yield (kind, payload)
        except Exception as exc:
            last, failed = f"{p.key}: {type(exc).__name__}: {exc}", True
            log.warning("provider %s raised: %s", p.key, exc)
            if produced:
                yield ("error", last)
                return
        if not failed:
            return
        if i < len(chain) - 1:
            yield ("fallback", {"from": p.key, "to": chain[i + 1].key, "reason": last[:200]})
    yield ("error", last or "all providers failed")
