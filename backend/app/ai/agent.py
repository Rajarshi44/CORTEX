"""
The investigator agent.

A tool-calling loop over the whole console: the model plans, calls retrieval tools, reads what
came back, calls more, and finally writes an answer with charts beside it. Everything it can
assert has to have come through a tool, and the loop streams as it goes so the analyst watches
the reasoning happen rather than staring at a spinner.

The stream is newline-delimited JSON, one event per line::

    {"type": "start",     "providers": [...], "provider": "gemini"}
    {"type": "step",      "n": 1}
    {"type": "tool_call", "id", "name", "input", "label"}
    {"type": "tool_done", "id", "name", "ms", "summary", "ok"}
    {"type": "text",      "delta": "..."}
    {"type": "visual",    "visual": {...}}          chart / network / table / timeline
    {"type": "fallback",  "from", "to", "reason"}   one provider handed over to the next
    {"type": "done",      "answer", "highlight_nodes", "citations", "visuals", "steps", "usage"}
    {"type": "error",     "message"}
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import networkx as nx
from sqlalchemy.orm import Session

from . import tools as T
from .providers import status as provider_status
from .providers import stream_with_fallback

log = logging.getLogger("cna.agent")

MAX_STEPS = 10
MAX_TOOL_CHARS = 14000

SYSTEM = """You are the investigator assistant inside CORTEX, a criminal-network analysis console used by Indian law enforcement analysts. You work on ONE case corpus that has already been ingested: FIRs, call-detail records, bank statements, surveillance logs, intelligence notes, court judgments, corporate filings, watchlists and news.

HOW YOU WORK
- Every factual claim you make must come from a tool result in THIS conversation. You have no memory of this corpus; if a tool did not return it, you do not know it.
- Plan, then retrieve. Chain tools: search_entities to get ids, then the analytical tools. Do not guess an entity id - ids look like uuids and only come from tool results.
- When a name is not found, say plainly that the corpus has no such entity and offer the closest matches the search returned. Never invent a person, a phone number, an amount or a date.
- Prefer several small precise calls over one broad one. Typically 3-6 tools for a real question.
- The corpus is the primary source. web_search and read_url reach the open internet for background the corpus lacks - use them when the question needs current or external context, and label those facts as open-web, unverified.
- Distinguish evidence from inference. Graph structure, link predictions and priority scores rank attention; they are not findings of guilt. Say which is which.

WHAT YOU SHOW
- Almost every answer deserves a visual. Call show_chart, show_network, show_table or show_timeline with data a tool already returned.
  - a ranking or a comparison -> show_chart kind "bar"
  - a split of a whole -> "donut"      - change over time -> "line" or "area"
  - calls by hour of day -> "hourly"   - headline figures -> "stat"
  - who is connected to whom, a path, an ego network, a community -> show_network with the entity ids
  - a chronology or a money trail in sequence -> show_timeline
  - a side-by-side of several entities -> show_table
- Render the visual BEFORE you write the prose that refers to it, and refer to it ("the chart below").
- Do not draw a chart of two numbers you already said in a sentence. One or two good visuals beat five weak ones.

HOW YOU WRITE
- Lead with the answer in one sentence. Then the evidence. Analyst register: precise, unhedged where the data is solid, explicit where it is thin.
- Bold entity names on first use. Give counts, amounts (INR, Indian digit grouping) and dates exactly as the tools returned them.
- Cite the source of a claim inline where it matters: the alert kind, the document title, the watchlist, the URL.
- Close with one line: the single next investigative step you would take.
- Keep it tight. Six to twelve lines of prose for most questions. Markdown: bold, bullets, headings. No preamble, no restating the question, no "as an AI".
- If the corpus genuinely cannot answer, say so in one line and name what data would be needed."""


def _label_for(name: str, args: dict) -> str:
    """A short human line describing a tool call, for the live trace."""
    a = args or {}
    first = next((str(a[k]) for k in ("query", "entity", "name", "document_id", "url", "title", "source") if a.get(k)), "")
    return {
        "search_entities": f"Searching the corpus for “{first}”",
        "entity_profile": f"Pulling the dossier on {first}",
        "find_path": f"Tracing a route: {a.get('source', '')} → {a.get('target', '')}",
        "neighbors": f"Listing what sits next to {first}",
        "money_flow": f"Following the money for {first}",
        "call_pattern": f"Reading the call pattern of {first}",
        "entity_timeline": f"Building the chronology for {first}",
        "list_alerts": "Reviewing anomaly alerts",
        "network_overview": "Taking in the whole network",
        "key_players": "Ranking the key players",
        "communities": "Detecting communities",
        "predict_links": "Predicting unobserved links",
        "disruption_impact": f"Modelling the removal of {first}",
        "aggregate": f"Counting {a.get('dataset', '')} by {a.get('group_by', '')}",
        "search_documents": f"Searching documents for “{first}”",
        "read_document": "Reading a source document",
        "case_linkage": "Comparing cases for a shared offender",
        "screen_sanctions": f"Screening {first or 'the corpus'} against watchlists",
        "corporate_registry": f"Checking the corporate registry for {first}",
        "offshore_leaks": f"Searching offshore leaks for {first}",
        "crime_news": "Checking the crime wires",
        "web_search": f"Searching the open web for “{first}”",
        "read_url": "Reading a web page",
        "show_chart": f"Drawing: {a.get('title', 'chart')}",
        "show_network": f"Drawing the link chart: {a.get('title', '')}",
        "show_table": f"Laying out: {a.get('title', '')}",
        "show_timeline": f"Plotting the timeline: {a.get('title', '')}",
        "highlight_on_chart": "Raising entities on the sheet",
    }.get(name, f"Running {name}")


def _summarise(name: str, result: Any) -> str:
    """One line describing what a tool returned, shown in the collapsed trace."""
    if not isinstance(result, dict):
        return "done"
    if err := result.get("error"):
        return str(err)[:120]
    if "rendered" in result:
        return f"{result['rendered']} rendered"
    if "paths" in result:
        n = len(result["paths"])
        return f"{n} path{'' if n == 1 else 's'}, {result.get('degrees_of_separation', '?')} hops" if n else "no path"
    # A dossier is best described by who it is about; only fall through to counting when the
    # result has no subject. Counting first made `entity_profile` report "0 alerts".
    if "entity" in result and isinstance(result["entity"], dict) and result["entity"].get("label"):
        return result["entity"]["label"]
    counts = (("results", "result"), ("alerts", "alert"), ("neighbors", "neighbour"),
              ("events", "event"), ("hits", "hit"), ("buckets", "bucket"),
              ("key_players", "player"), ("communities", "community"),
              ("predictions", "prediction"), ("items", "item"), ("links", "linked pair"))
    # prefer a key that actually found something; an empty list is only worth reporting
    # when nothing else did
    for require_nonempty in (True, False):
        for key, word in counts:
            v = result.get(key)
            if isinstance(v, list) and (v or not require_nonempty):
                return f"{len(v)} {word}{'' if len(v) == 1 else 's'}"
    if "summary" in result:
        s = result["summary"]
        return f"{s.get('nodes', 0)} entities, {s.get('edges', 0)} links"
    if "total_in" in result:
        return f"in ₹{result['total_in']:,.0f} / out ₹{result['total_out']:,.0f}"
    if "total_calls" in result:
        return f"{result['total_calls']} calls"
    if "content" in result:
        return f"{len(result['content'])} chars"
    return "done"


def _clip(payload: Any) -> str:
    s = json.dumps(payload, default=str, ensure_ascii=False)
    if len(s) <= MAX_TOOL_CHARS:
        return s
    return s[:MAX_TOOL_CHARS] + f'... [truncated, {len(s)} chars total; narrow the query to see the rest]"'


def _corpus_note(ctx: T.Ctx) -> str:
    s = ctx.snap.get("summary", {})
    types = ", ".join(f"{k} {v}" for k, v in sorted((s.get("node_types") or {}).items(), key=lambda kv: -kv[1])[:8])
    rels = ", ".join(f"{k} {v}" for k, v in sorted((s.get("relationship_types") or {}).items(), key=lambda kv: -kv[1])[:10])
    return (f"\n\nTHIS CORPUS RIGHT NOW: {s.get('nodes', 0)} entities and {s.get('edges', 0)} relationships; "
            f"{s.get('actors', 0)} actors in {s.get('communities', 0)} communities, {s.get('persons_of_interest', 0)} persons of interest. "
            f"Entity types: {types}. Relationship types: {rels}. "
            f"Analytics computed at {ctx.snap.get('computed_at', 'unknown')}.")


class InvestigatorAgent:
    def __init__(self, db: Session, G: nx.Graph, D: nx.DiGraph, snapshot: dict):
        self.ctx = T.Ctx(db, G, D, snapshot)

    # ------------------------------------------------------------------ history
    @staticmethod
    def _history(turns: list[dict] | None) -> list[dict]:
        """Prior turns as plain text; tool traffic is not replayed, only what was said."""
        out: list[dict] = []
        for t in (turns or [])[-6:]:
            if q := (t.get("question") or t.get("q") or "").strip():
                out.append({"role": "user", "content": [{"type": "text", "text": q}]})
            if a := (t.get("answer") or t.get("a") or "").strip():
                out.append({"role": "assistant", "content": [{"type": "text", "text": a[:2500]}]})
        return out

    # ------------------------------------------------------------------ loop
    def stream(self, question: str, history: list[dict] | None = None) -> Iterator[dict]:
        providers = provider_status()
        if not providers["any"]:
            yield {"type": "error",
                   "message": "No language-model provider is configured. Set CNA_GEMINI_API_KEY (or CNA_NVIDIA_API_KEY, "
                              "or CNA_ANTHROPIC_API_KEY) in backend/.env and restart the API."}
            return

        specs = T.specs()
        system = SYSTEM + _corpus_note(self.ctx)
        messages = self._history(history) + [{"role": "user", "content": [{"type": "text", "text": question}]}]
        yield {"type": "start", "providers": providers["providers"], "provider": providers["active"]["key"],
               "model": providers["active"]["model"], "tools": len(specs)}

        answer_parts: list[str] = []
        seen_visuals = 0
        usage: dict[str, Any] = {}
        step = 0
        t_start = time.monotonic()

        while step < MAX_STEPS:
            step += 1
            yield {"type": "step", "n": step}
            turn_text: list[str] = []
            calls: list[dict] = []
            stop_reason = "end_turn"
            failed = None

            for kind, payload in stream_with_fallback(system, messages, specs, max_tokens=4096):
                if kind == "text":
                    turn_text.append(payload)
                    yield {"type": "text", "delta": payload}
                elif kind == "tool_use":
                    calls.append(payload)
                elif kind == "fallback":
                    yield {"type": "fallback", **payload}
                elif kind == "done":
                    stop_reason = payload.get("stop_reason", "end_turn")
                    if payload.get("usage"):
                        for k, v in payload["usage"].items():
                            if isinstance(v, int):
                                usage[k] = usage.get(k, 0) + v
                    usage["provider"] = payload.get("provider")
                    usage["model"] = payload.get("model")
                elif kind == "error":
                    failed = str(payload)

            if failed and not calls and not "".join(turn_text).strip():
                yield {"type": "error", "message": failed}
                return

            text = "".join(turn_text)
            if text.strip():
                answer_parts.append(text)

            if not calls:
                break

            # record the assistant turn exactly as the model produced it
            assistant_content: list[dict] = ([{"type": "text", "text": text}] if text.strip() else [])
            assistant_content += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["input"]} for c in calls]
            messages.append({"role": "assistant", "content": assistant_content})

            results: list[dict] = []
            for c in calls:
                yield {"type": "tool_call", "id": c["id"], "name": c["name"], "input": c["input"],
                       "label": _label_for(c["name"], c["input"])}
                t0 = time.monotonic()
                res = T.run(self.ctx, c["name"], c["input"])
                ms = int((time.monotonic() - t0) * 1000)
                ok = not (isinstance(res, dict) and res.get("error"))
                yield {"type": "tool_done", "id": c["id"], "name": c["name"], "ms": ms,
                       "summary": _summarise(c["name"], res), "ok": ok}
                results.append({"type": "tool_result", "tool_use_id": c["id"], "name": c["name"],
                                "content": _clip(res)})
                while seen_visuals < len(self.ctx.visuals):
                    yield {"type": "visual", "visual": self.ctx.visuals[seen_visuals]}
                    seen_visuals += 1
            messages.append({"role": "user", "content": results})

            if stop_reason not in ("tool_use", "end_turn", None):
                break

        answer = "".join(answer_parts).strip()
        if not answer:
            answer = ("I could not compose an answer from the retrieved facts. Try narrowing the question to one "
                      "entity or one pattern.")
        G = self.ctx.G
        highlight_ids = list(dict.fromkeys([h for h in self.ctx.highlights if h in G]))[:60]
        # de-duplicate citations, keeping first sighting order
        cites: list[dict] = []
        seen_c: set[str] = set()
        for c in self.ctx.citations:
            key = f"{c['kind']}:{c['id']}"
            if key in seen_c:
                continue
            seen_c.add(key)
            cites.append(c)
        yield {"type": "done", "answer": answer, "steps": step, "seconds": round(time.monotonic() - t_start, 2),
               "highlight_nodes": [{"id": n, "label": G.nodes[n]["label"], "type": G.nodes[n]["type"]} for n in highlight_ids],
               "highlights": {"nodes": highlight_ids, "edges": []},
               "visuals": self.ctx.visuals, "citations": cites[:20], "usage": usage}

    # ------------------------------------------------------------------ non-streaming
    def answer(self, question: str, history: list[dict] | None = None) -> dict:
        """Same loop, collected into one response - for clients that cannot stream."""
        trace: list[dict] = []
        final: dict = {}
        for ev in self.stream(question, history):
            if ev["type"] in ("tool_call", "tool_done", "fallback"):
                trace.append(ev)
            elif ev["type"] == "done":
                final = ev
            elif ev["type"] == "error":
                return {"answer": ev["message"], "error": True, "trace": trace, "visuals": [],
                        "highlight_nodes": [], "highlights": {"nodes": [], "edges": []}, "citations": []}
        final["trace"] = trace
        final["question"] = question
        return final


def capabilities() -> dict:
    ps = provider_status()
    from ..sources.web import tier as web_tier

    return {
        "agent": True,
        "providers": ps["providers"],
        "provider": ps["active"],
        "llm": ps["any"],
        "model": ps["active"]["model"] if ps["active"] else None,
        "tools": T.tool_catalogue(),
        "web_tier": web_tier(),
        "max_steps": MAX_STEPS,
        "examples": [
            "Who runs this network, and what makes you say so?",
            "Trace the money out of the largest account and chart where it goes.",
            "How are the top two key players connected? Draw the path.",
            "Which communities are suspicious? Compare them in a table.",
            "Show the call pattern of the most active phone by hour of day.",
            "What happens to the network if we arrest the top broker?",
            "Any of our people on sanctions or wanted lists?",
            "What is publicly reported about the biggest company in this corpus?",
        ],
    }
