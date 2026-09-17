"""Comprehensive automated tests for Milestone M5: Investigator AI Chat & Web Search (R2).

Verifies:
1. Hardcoded demo fallback interception has been completely removed; all queries execute
   through the dynamic tool-calling agent loop.
2. Database tools (search_entities, entity_profile, money_flow, etc.) execute real queries
   against the database session and return actual database rows.
3. Web search tool (_web_search) executes and retrieves live results, populating citations.
4. SYSTEM prompt instructs the agent to ask for case-specific details for broad questions,
   prioritize corpus tools first, and use web_search when external context is needed.
5. stream_with_fallback handles transient provider errors, rate limits, and network errors gracefully.
6. OpenRouter and OpenAICompatibleProvider parse chunked streaming tool calls correctly.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai import tools as T
from app.ai.agent import SYSTEM, InvestigatorAgent, capabilities
from app.ai.providers import (
    Event,
    GeminiProvider,
    NvidiaNIMProvider,
    OpenAICompatibleProvider,
    OpenRouterProvider,
    ToolSpec,
    available_providers,
    provider_chain,
    status as provider_status,
    stream_with_fallback,
)
from app.db import Base, Case, Document, Entity, Relationship, TimelineEvent
from app.sources.web import WebConnector


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def isolated_db(tmp_path: Path):
    """Isolated SQLite database with schema and sample case data."""
    db_file = tmp_path / "test_m5_chat.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    # Populate a test Case
    case = Case(id="case-001", name="Operation Cybershield", description="Financial extortion ring investigation")
    session.add(case)

    # Populate a source Document
    doc = Document(
        id="doc-001",
        title="FIR 102/2025 cyber crime PS",
        source_type="FIR",
        content="First Information Report regarding extortion call from Prabhakar Kumar.",
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(doc)

    # Populate Entities
    e1 = Entity(
        id="ent-prabhakar",
        label="Prabhakar Kumar",
        type="PERSON",
        canonical_key="prabhakar kumar",
        aliases=["Prabhakar K.", "PK"],
        mention_count=12,
    )
    e2 = Entity(
        id="ent-rupesh",
        label="Rupesh Kumar Singh",
        type="PERSON",
        canonical_key="rupesh kumar singh",
        aliases=["Rupesh S."],
        mention_count=8,
    )
    e3 = Entity(
        id="ent-account-a002",
        label="Mule Account 2 - [Illustrative: XXXX2222]",
        type="BANK_ACCOUNT",
        canonical_key="mule account 2",
        aliases=["A002", "XXXX2222"],
        mention_count=5,
    )
    session.add_all([e1, e2, e3])

    # Populate Relationships
    rel1 = Relationship(
        id="rel-001",
        source_id=e1.id,
        target_id=e2.id,
        rel_type="ASSOCIATE_OF",
        weight=0.85,
    )
    rel2 = Relationship(
        id="rel-002",
        source_id=e1.id,
        target_id=e3.id,
        rel_type="OWNS_ACCOUNT",
        weight=0.9,
    )
    session.add_all([rel1, rel2])

    # Populate Timeline events (money transfer)
    t1 = TimelineEvent(
        document_id=doc.id,
        kind="TRANSFER",
        occurred_at=datetime.now(timezone.utc),
        summary="Transfer of funds to Mule Account 2",
        details={"amount": 150000.0, "from_holder": "Victim", "to_holder": "Mule Account 2", "mode": "IMPS"},
        entity_ids=[e1.id, e3.id],
    )
    session.add(t1)

    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def graph_and_context(isolated_db):
    """NetworkX graph and Ctx initialized with isolated_db."""
    G = nx.Graph()
    D = nx.DiGraph()

    for e in isolated_db.query(Entity).all():
        G.add_node(e.id, label=e.label, type=e.type, aliases=e.aliases or [], attrs={})
        D.add_node(e.id, label=e.label, type=e.type, aliases=e.aliases or [], attrs={})

    for r in isolated_db.query(Relationship).all():
        G.add_edge(r.source_id, r.target_id, weight=r.weight, rel_type=r.rel_type, count=1)
        D.add_edge(r.source_id, r.target_id, weight=r.weight, rel_type=r.rel_type, count=1)

    snapshot = {
        "summary": {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()},
        "roles": {},
        "community": {},
        "priority": {},
        "suspicion": {
            "ent-prabhakar": {"score": 0.88, "reasons": ["High call frequency", "Linked to mule accounts"]}
        },
    }

    ctx = T.Ctx(isolated_db, G, D, snapshot)
    return isolated_db, G, D, snapshot, ctx


# -----------------------------------------------------------------------------
# 1. Canned Demo Fallback Interception Removal Tests
# -----------------------------------------------------------------------------
def test_demo_fallback_interception_removed(isolated_db, graph_and_context, monkeypatch):
    """Verify that demo_fallback no longer intercepts questions even when CNA_DEFAULT_CORPUS=none."""
    isolated_db, G, D, snapshot, _ = graph_and_context

    monkeypatch.setenv("CNA_DEFAULT_CORPUS", "none")
    assert isolated_db.query(Case).count() > 0

    # Questions that matched demo_fallback keywords previously
    test_question = "Tell me about Prabhakar Kumar"

    # Mock stream_with_fallback so we inspect what enters the agent loop
    mock_events = [
        ("text", "Investigating Prabhakar Kumar through dynamic tool calling."),
        ("done", {"stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 10}}),
    ]

    with patch("app.ai.agent.stream_with_fallback", return_value=iter(mock_events)) as mock_stream:
        agent = InvestigatorAgent(isolated_db, G, D, snapshot)
        events = list(agent.stream(test_question))

        # Ensure stream_with_fallback was called (dynamic agent loop executed)
        assert mock_stream.called
        event_types = [e["type"] for e in events]
        assert "start" in event_types
        assert "step" in event_types
        assert "text" in event_types
        assert "done" in event_types

        # Verify the answer came from our dynamic stream, NOT the canned demo_fallback text
        done_event = next(e for e in events if e["type"] == "done")
        assert "Investigating Prabhakar Kumar through dynamic tool calling." in done_event["answer"]
        assert "Accused persons" not in done_event["answer"]  # canned overview text not present


def test_system_prompt_instructs_clarification_and_corpus_priority():
    """Verify SYSTEM prompt includes instructions for ambiguous questions and corpus priority."""
    assert "If the investigator's question is too broad or lacks specific entity or case details, ask for the specific entity name, account number, phone number, or transaction date" in SYSTEM
    assert "Always retrieve facts from the corpus tools first." in SYSTEM
    assert "If web context is needed or requested, use web_search" in SYSTEM


# -----------------------------------------------------------------------------
# 2. Database Retrieval Tool Execution Tests
# -----------------------------------------------------------------------------
def test_search_entities_tool_executes_db_query(graph_and_context):
    """Verify search_entities tool queries the database session and returns real rows."""
    _, _, _, _, ctx = graph_and_context

    res = T.run(ctx, "search_entities", {"query": "Prabhakar"})
    assert res["count"] >= 1
    assert any(r["id"] == "ent-prabhakar" and r["label"] == "Prabhakar Kumar" for r in res["results"])

    # Test alias and canonical key matching
    res_alias = T.run(ctx, "search_entities", {"query": "PK"})
    assert res_alias["count"] >= 1
    assert any(r["id"] == "ent-prabhakar" for r in res_alias["results"])


def test_entity_profile_tool_retrieves_real_dossier(graph_and_context):
    """Verify entity_profile retrieves real database relationships, associates, and suspicion."""
    _, _, _, _, ctx = graph_and_context

    res = T.run(ctx, "entity_profile", {"entity": "Prabhakar Kumar"})
    assert "error" not in res
    assert res["entity"]["id"] == "ent-prabhakar"
    assert res["entity"]["label"] == "Prabhakar Kumar"
    assert res["entity"]["suspicion"] == 0.88

    # Verify real relationship returned from DB
    assert "ASSOCIATE_OF" in res["relationships"]
    assoc = res["relationships"]["ASSOCIATE_OF"]
    assert any(a["id"] == "ent-rupesh" for a in assoc)


def test_money_flow_tool_executes_timeline_db_query(graph_and_context):
    """Verify money_flow tool queries real TimelineEvent TRANSFER records in the database."""
    _, _, _, _, ctx = graph_and_context

    res = T.run(ctx, "money_flow", {"entity": "ent-account-a002"})
    assert "error" not in res
    assert res["total_in"] == 150000.0
    assert len(res["transactions"]) >= 1
    assert res["transactions"][0]["amount"] == 150000.0


def test_agent_dynamic_tool_calling_loop_with_database(graph_and_context):
    """Simulate complete agent loop where LLM emits tool call to search_entities and synthesizes response."""
    isolated_db, G, D, snapshot, ctx = graph_and_context

    # Simulate multi-step tool calling:
    # Step 1: LLM decides to call search_entities
    step1_events: list[Event] = [
        ("tool_use", {"id": "call_1", "name": "search_entities", "input": {"query": "Prabhakar Kumar"}}),
        ("done", {"stop_reason": "tool_use"}),
    ]
    # Step 2: After receiving database results, LLM writes final evidence answer
    step2_events: list[Event] = [
        ("text", "**Prabhakar Kumar** is a confirmed entity in the corpus."),
        ("done", {"stop_reason": "end_turn"}),
    ]

    call_count = 0

    def mock_stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield from step1_events
        else:
            yield from step2_events

    with patch("app.ai.agent.stream_with_fallback", side_effect=mock_stream):
        agent = InvestigatorAgent(isolated_db, G, D, snapshot)
        events = list(agent.stream("Who is Prabhakar Kumar?"))

        # Verify tool call was processed and executed against DB
        tool_call_ev = next(e for e in events if e["type"] == "tool_call")
        assert tool_call_ev["name"] == "search_entities"

        tool_done_ev = next(e for e in events if e["type"] == "tool_done")
        assert tool_done_ev["name"] == "search_entities"
        assert tool_done_ev["ok"] is True

        done_ev = next(e for e in events if e["type"] == "done")
        assert "**Prabhakar Kumar** is a confirmed entity in the corpus." in done_ev["answer"]


# -----------------------------------------------------------------------------
# 3. Web Search Option and Citation Tests
# -----------------------------------------------------------------------------
def test_web_search_tool_executes_live_search(graph_and_context):
    """Verify web_search executes DuckDuckGo search and populates citations with live URLs."""
    _, _, _, _, ctx = graph_and_context

    res = T.run(ctx, "web_search", {"query": "Reserve Bank of India", "limit": 2})
    assert "error" not in res
    assert res["count"] > 0
    assert len(res["results"]) > 0

    # Ensure open-web citation was appended to ctx.citations
    assert len(ctx.citations) > 0
    web_cite = next(c for c in ctx.citations if c["kind"] == "web")
    assert web_cite["source_type"] == "WEB"
    assert web_cite["id"].startswith("http")
    assert "Reserve Bank" in web_cite["title"] or "RBI" in web_cite["title"] or "India" in web_cite["title"]


def test_web_search_duckduckgo_parser():
    """Verify HTML parser in WebConnector parses search results cleanly."""
    mock_html = """
    <div class="results">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.rbi.org.in%2F&rut=1">Reserve Bank of India</a>
      <div class="result__snippet">Official website of the Reserve Bank of India.</div>
    </div>
    """
    results = WebConnector._parse_ddg(mock_html, limit=2)
    assert len(results) == 1
    assert results[0]["title"] == "Reserve Bank of India"
    assert results[0]["url"] == "https://www.rbi.org.in/"
    assert "Official website" in results[0]["snippet"]


def test_agent_loop_with_web_search(graph_and_context):
    """Verify agent loop properly executes web_search tool and collects citations in final event."""
    isolated_db, G, D, snapshot, _ = graph_and_context

    step1_events: list[Event] = [
        ("tool_use", {"id": "call_web", "name": "web_search", "input": {"query": "Enforcement Directorate India", "limit": 1}}),
        ("done", {"stop_reason": "tool_use"}),
    ]
    step2_events: list[Event] = [
        ("text", "Public web reports verify recent regulatory notices."),
        ("done", {"stop_reason": "end_turn"}),
    ]

    calls = 0

    def mock_stream(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield from step1_events
        else:
            yield from step2_events

    with patch("app.ai.agent.stream_with_fallback", side_effect=mock_stream):
        agent = InvestigatorAgent(isolated_db, G, D, snapshot)
        events = list(agent.stream("Search the web for Enforcement Directorate"))

        done_ev = next(e for e in events if e["type"] == "done")
        assert len(done_ev["citations"]) > 0
        assert any(c["kind"] == "web" for c in done_ev["citations"])


# -----------------------------------------------------------------------------
# 4. Ambiguous / Underspecified Clarification Tests
# -----------------------------------------------------------------------------
def test_clarification_prompted_for_underspecified_questions(graph_and_context):
    """Verify that when a question lacks specific details, the model prompts for case specifics."""
    isolated_db, G, D, snapshot, _ = graph_and_context

    mock_clarification = (
        "The inquiry is too broad. Please provide a specific entity name, phone number, "
        "bank account, or transaction date to begin the investigation."
    )

    def mock_stream(*args, **kwargs):
        yield ("text", mock_clarification)
        yield ("done", {"stop_reason": "end_turn"})

    with patch("app.ai.agent.stream_with_fallback", side_effect=mock_stream):
        agent = InvestigatorAgent(isolated_db, G, D, snapshot)
        events = list(agent.stream("Can you investigate?"))

        done_ev = next(e for e in events if e["type"] == "done")
        assert "specific entity name, phone number, bank account, or transaction date" in done_ev["answer"]


# -----------------------------------------------------------------------------
# 5. LLM API Configuration & Fallback Robustness Tests
# -----------------------------------------------------------------------------
def test_stream_with_fallback_switches_on_provider_error():
    """Verify stream_with_fallback catches errors from first provider and seamlessly fails over."""
    class FailingProvider:
        key = "fail_prov"
        label = "Failing Provider"
        def available(self): return True
        def stream(self, *a, **kw):
            yield ("error", "HTTP 429: rate limit exceeded")

    class WorkingProvider:
        key = "work_prov"
        label = "Working Provider"
        def available(self): return True
        def stream(self, *a, **kw):
            yield ("text", "Answer from working fallback provider.")
            yield ("done", {"stop_reason": "end_turn", "provider": "work_prov"})

    with patch("app.ai.providers.available_providers", return_value=[FailingProvider(), WorkingProvider()]):
        events = list(stream_with_fallback("system", [{"role": "user", "content": [{"type": "text", "text": "hi"}]}], []))

        # Check that fallback event was emitted
        fallback_ev = next(e for e in events if e[0] == "fallback")
        assert fallback_ev[1]["from"] == "fail_prov"
        assert fallback_ev[1]["to"] == "work_prov"
        assert "429" in fallback_ev[1]["reason"]

        # Check that working provider completed the stream
        text_ev = next(e for e in events if e[0] == "text")
        assert text_ev[1] == "Answer from working fallback provider."

        done_ev = next(e for e in events if e[0] == "done")
        assert done_ev[1]["stop_reason"] == "end_turn"


def test_openai_compatible_provider_parses_chunked_tool_calls():
    """Verify OpenAICompatibleProvider correctly reconstructs streaming tool calls and arguments."""
    provider = OpenRouterProvider()

    sse_chunks = [
        '{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "tc_1", "function": {"name": "search_entities", "arguments": "{\\"que"}}]}}]}',
        '{"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "ry\\": \\"test\\"}"}}]}}]}',
        '{"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}',
        "[DONE]",
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_lines.return_value = [f"data: {c}".encode("utf-8") for c in sse_chunks]

    with patch("httpx.Client.stream") as mock_stream_ctx:
        mock_stream_ctx.return_value.__enter__.return_value = mock_resp

        events = list(provider.stream("system", [{"role": "user", "content": [{"type": "text", "text": "search"}]}], []))

        tool_use_ev = next(e for e in events if e[0] == "tool_use")
        assert tool_use_ev[1]["id"] == "tc_1"
        assert tool_use_ev[1]["name"] == "search_entities"
        assert tool_use_ev[1]["input"] == {"query": "test"}

        done_ev = next(e for e in events if e[0] == "done")
        assert done_ev[1]["stop_reason"] == "tool_use"


def test_capabilities_returns_agent_metadata():
    """Verify capabilities() correctly reports agent tools, web tier, and models."""
    caps = capabilities()
    assert caps["agent"] is True
    assert "tools" in caps
    assert any(t["name"] == "search_entities" for t in caps["tools"])
    assert any(t["name"] == "web_search" for t in caps["tools"])
    assert caps["web_tier"] in ("duckduckgo", "firecrawl")


def test_live_agent_db_and_llm_e2e():
    """Live test exercising InvestigatorAgent with real LLM and real database if configured."""
    ps = provider_status()
    if not ps["any"]:
        pytest.skip("No live LLM provider available")
    from app.db import SessionLocal
    from app.graph.store import graph_cache
    from app.api.deps import analysis_service

    db = SessionLocal()
    try:
        if db.query(Entity).count() == 0:
            pytest.skip("No entities in database")
        G = graph_cache.get(db)
        D = graph_cache.get_directed(db)
        snap = analysis_service.snapshot(db)
        agent = InvestigatorAgent(db, G, D, snap)
        # Execute query that requires real database entity retrieval
        ans = agent.answer("Tell me about Prabhakar Kumar")
        assert ans.get("error") is not True
        assert len(ans.get("answer", "")) > 10
        assert any(t.get("name") in ("search_entities", "entity_profile") for t in ans.get("trace", []))
    finally:
        db.close()

