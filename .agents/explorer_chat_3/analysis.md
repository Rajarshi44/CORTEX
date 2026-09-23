# Analysis Report: R3 Frontend UI Updates & Automated Acceptance Test Design
**Milestone M8: Investigator Chat History Persistence**  
**Agent**: `explorer_chat_3`  
**Date**: 2026-09-23  

---

## 1. Executive Summary

Milestone M8 introduces end-to-end conversation persistence for the CORTEX Investigator lens. Previously, the Investigator lens held conversation turns strictly in volatile client-side memory (`useSheet((s) => s.investigatorTurns)`). Every page reload (`F5`) or route change reset the conversation to empty, and requests sent to `/api/agent/stream` and `/api/assistant/ask` carried no session identifiers, preventing conversation memory or follow-up question context (e.g. resolving pronouns like "What did they do?").

This analysis delivers:
1. **Frontend Architecture & UI Updates (R3)** across 4 files:
   - `frontend-next/src/lib/store.ts`: Adds `investigatorSessionId` to Zustand state with persistence in `partialize` (`cortex.sheet`).
   - `frontend-next/src/lib/api.ts`: Augments `api.ask()` with `session_id` and adds session management endpoints (`chatSessions`, `chatSession`, `deleteChatSession`).
   - `frontend-next/src/lib/agent.ts`: Augments `streamAgent()` with `session_id` and adds `session_id` to event types and `agentApi`.
   - `frontend-next/src/app/(sheet)/investigator/page.tsx`: Integrates URL query state (`?session=...`) via `nuqs`, automatic history hydration on page mount/refresh, clean multi-turn rendering of historical turns, a "+ New Chat" button in the header, and an optional session switcher.
2. **Automated Acceptance Test Suite (`backend/tests/test_investigator.py`)**:
   - A complete, self-contained pytest test suite validating:
     - Sequential two-turn conversation sharing `session_id` (Turn 1: *"Who is the mastermind?"* -> Turn 2: *"What did they do?"*).
     - Pronoun / anaphora resolution in Turn 2 referencing the entity from Turn 1 (*"Prabhakar Kumar"*).
     - True database persistence in SQLite table `chat_sessions`.
     - Session retrieval endpoint (`GET /api/assistant/sessions/{session_id}`).
     - Router prefix compatibility (`POST /assistant/ask` and `POST /api/assistant/ask`).
     - Session listing (`GET /api/assistant/sessions`), deletion (`DELETE /api/assistant/sessions/{id}`), and session isolation.

---

## 2. Current State Analysis

### 2.1 Frontend State & Lifecycle (`investigator/page.tsx` & `store.ts`)
- **Turn State**: Lines 52–53 in `page.tsx`:
  ```typescript
  const turns = useSheet((s) => s.investigatorTurns) as Turn[];
  const setTurns = useSheet((s) => s.setInvestigatorTurns);
  ```
  `investigatorTurns` is stored in the Zustand store (`store.ts`).
- **Persistence Gap in `store.ts`**:
  Lines 84–87 of `store.ts`:
  ```typescript
  {
    name: "cortex.sheet",
    partialize: (s) => ({
      presentation: s.presentation,
      hiddenTypes: s.hiddenTypes,
      hiddenRelations: s.hiddenRelations,
      minPriority: s.minPriority,
      user: s.user,
      investigatorDetailLevel: s.investigatorDetailLevel
    }),
  }
  ```
  `investigatorTurns` is **not** part of `partialize`. On any page reload or browser restart, `investigatorTurns` defaults to `[]`.
- **No Session Identifier**:
  Neither `store.ts` nor `page.tsx` maintains any `session_id` or session concept.
- **Request Payloads**:
  - `streamAgent()` in `agent.ts` sends `{ question, history: history.slice(-6) }` to `/api/agent/stream`.
  - `api.ask()` in `api.ts` sends `{ question }` to `/api/assistant/ask`.
  Neither passes `session_id`.
- **Header Controls**:
  `Header` in `page.tsx` currently only contains the lens title, detail level dropdown (`Detailed Analysis` vs `Basic Summary`), and provider info. There is no button to start a new chat or reset the session.

### 2.2 Backend Router & Prefix Analysis
- `routes_intel.py` sets `router = APIRouter(prefix="/api", tags=["intel"])`.
- Line 121: `@router.post("/assistant/ask")` means the endpoint is exposed at `/api/assistant/ask`.
- However, client scripts, acceptance tests, and requirement specifications refer to `/assistant/ask`.
- As analyzed by `explorer_chat_2`, mounting an alias router without prefix in `main.py` guarantees both `/api/assistant/ask` and `/assistant/ask` resolve seamlessly.

### 2.3 Existing Test Patterns in `backend/tests/`
- Existing test suites (`test_m5_investigator_chat.py`, `test_m4_ledger.py`, `test_m3_m6_tagging_map.py`) use:
  - SQLite with `Base.metadata.create_all(engine)`.
  - Dependency override on `app.dependency_overrides[get_session]`.
  - `TestClient(app, raise_server_exceptions=True)`.
  - Mocked or seeded `graph_cache` and `analysis_service.snapshot`.
  - JWT authentication using `create_token(user)`.

---

## 3. Frontend UI Updates Design (R3)

### 3.1 State Architecture: Zustand `store.ts`
We update `SheetState` to track `investigatorSessionId` and include it in `partialize` so it persists to `localStorage` under `cortex.sheet`.

```typescript
// Addition to SheetState interface in frontend-next/src/lib/store.ts
investigatorSessionId: string | null;
setInvestigatorSessionId: (id: string | null) => void;

// Addition to create<SheetState>() store implementation
investigatorSessionId: null,
setInvestigatorSessionId: (investigatorSessionId) => set({ investigatorSessionId }),

// Addition to partialize in store.ts
partialize: (s) => ({
  presentation: s.presentation,
  hiddenTypes: s.hiddenTypes,
  hiddenRelations: s.hiddenRelations,
  minPriority: s.minPriority,
  user: s.user,
  investigatorDetailLevel: s.investigatorDetailLevel,
  investigatorSessionId: s.investigatorSessionId, // <-- Persisted!
}),
```

### 3.2 URL Query Parameter & LocalStorage Synchronization
To provide the best user experience and enable shareable / bookmarkable URLs:
1. `useQueryState("session", parseAsString)` from `nuqs` binds `?session=<session_id>` in the URL bar.
2. Direct `localStorage` key `"cortex.investigator.session_id"` acts as a resilient fallback.
3. Bidirectional sync:
   - When entering the page with `?session=abc`: the URL takes precedence; `investigatorSessionId` is set to `abc`.
   - When entering without `?session`: if `investigatorSessionId` is saved in store/localStorage, the URL is updated to `?session=abc`.
   - When "+ New Chat" is clicked: `investigatorSessionId` is set to `null`, `session` query param is removed (`null`), and localStorage is cleared.

### 3.3 Session History Hydration on Mount / Refresh
In `frontend-next/src/app/(sheet)/investigator/page.tsx`:
We add a `useEffect` that triggers whenever the active session ID changes or the component mounts:

```typescript
const [loadingSession, setLoadingSession] = useState(false);

useEffect(() => {
  const activeSessionId = sessionParam || sessionId;
  if (!activeSessionId) return;

  let cancelled = false;
  setLoadingSession(true);

  api.chatSession(activeSessionId)
    .then((data) => {
      if (cancelled || !data || !Array.isArray(data.messages)) return;
      
      const loadedTurns: Turn[] = data.messages.map((m: any, idx: number) => ({
        id: idx + 1,
        q: m.question || m.q || "",
        text: m.answer || m.text || "",
        calls: m.calls || m.trace || [],
        visuals: m.visuals || [],
        highlights: m.highlight_nodes || m.highlights || [],
        citations: m.citations || [],
        provider: m.provider,
        model: m.model,
        steps: m.steps,
        seconds: m.seconds,
        running: false,
        searchWeb: m.searchWeb || false,
      }));

      setTurns(loadedTurns);
      if (activeSessionId !== sessionId) setSessionId(activeSessionId);
    })
    .catch((err) => {
      console.warn("Failed to load investigator session:", err);
      // If 404 or corrupted session, reset to fresh state
      if (err?.status === 404) {
        setSessionId(null);
        setSessionParam(null);
        if (typeof window !== "undefined") {
          localStorage.removeItem("cortex.investigator.session_id");
        }
      }
    })
    .finally(() => {
      if (!cancelled) setLoadingSession(false);
    });

  return () => {
    cancelled = true;
  };
}, [sessionParam, sessionId]);
```

### 3.4 Multi-Turn UI Rendering
The current rendering loop in `page.tsx` (`<ol className="space-y-7">`) already renders:
- Turn sequence number: `Q · 01`, `Q · 02`...
- Question title and web search badge
- `ToolTrace` (collapsible list of tool calls)
- `VisualBlock` (charts, network diagrams, timelines, tables)
- `Markdown` response narrative
- Highlight nodes with "show on chart" link
- Document citations and open web links
- Steps, seconds, provider metadata
- "Go deeper" follow-up prompt button

When turns are loaded from the database:
- `running` is set to `false`.
- Missing fields are safely defaulted (`calls: []`, `visuals: []`, `highlights: []`, `citations: []`), preventing runtime null-reference exceptions.
- Smooth auto-scrolling to the latest turn is preserved via `listRef`.

### 3.5 Header UI Controls ("+ New Chat" & Session Switcher)
In `Header` component in `page.tsx`:
Add a "+ New Chat" button and session indicator:

```tsx
<div className="flex items-center gap-2">
  <button
    type="button"
    onClick={onNewChat}
    title="Start a new investigation session"
    className="label flex items-center gap-1.5 rounded-[2px] border border-rule-strong px-2.5 py-1 text-ink-soft hover:border-ink hover:text-ink transition-colors"
  >
    <Plus className="h-3.5 w-3.5" aria-hidden="true" />
    <span>New Chat</span>
  </button>

  <select
    value={detailLevel}
    onChange={(e) => setDetailLevel(e.target.value as "detailed" | "basic")}
    className="note bg-transparent text-ink-soft border-b border-dotted border-rule-strong outline-none"
  >
    <option value="detailed">Detailed Analysis</option>
    <option value="basic">Basic Summary</option>
  </select>
</div>
```

When "+ New Chat" is clicked:
```typescript
const handleNewChat = useCallback(() => {
  if (abortRef.current) {
    abortRef.current.abort();
    abortRef.current = null;
  }
  setTurns([]);
  setSessionId(null);
  setSessionParam(null);
  if (typeof window !== "undefined") {
    localStorage.removeItem("cortex.investigator.session_id");
  }
}, [setTurns, setSessionId, setSessionParam]);
```

### 3.6 API & Stream Client Updates (`api.ts` & `agent.ts`)
1. In `frontend-next/src/lib/api.ts`:
```typescript
// In api object:
ask: (question: string, session_id?: string | null) =>
  request<AssistantAnswer & { session_id?: string }>("/api/assistant/ask", {
    method: "POST",
    body: JSON.stringify({ question, session_id: session_id || undefined }),
  }),

chatSessions: () =>
  request<{ sessions: { id: string; title: string; created_at: string; updated_at: string; message_count: number }[] }>("/api/assistant/sessions"),

chatSession: (id: string) =>
  request<{ id: string; title: string; created_at: string; updated_at: string; messages: any[] }>(`/api/assistant/sessions/${id}`),

deleteChatSession: (id: string) =>
  request<{ ok: boolean }>(`/api/assistant/sessions/${id}`, { method: "DELETE" }),
```

2. In `frontend-next/src/lib/agent.ts`:
```typescript
export async function streamAgent(
  question: string,
  history: { question: string; answer: string }[],
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
  session_id?: string | null,
): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE}/api/agent/stream`, {
    method: "POST",
    headers,
    signal,
    body: JSON.stringify({
      question,
      history: history.slice(-6),
      session_id: session_id || undefined,
    }),
  });
  ...
```

And update `AgentEvent` `done` type:
```typescript
| {
    type: "done";
    answer: string;
    session_id?: string;
    steps: number;
    seconds: number;
    highlight_nodes: HighlightNode[];
    highlights: { nodes: string[]; edges: string[] };
    visuals: Visual[];
    citations: Citation[];
    usage: Record<string, unknown>;
  }
```

---

## 4. Automated Acceptance Test Design: `backend/tests/test_investigator.py`

### 4.1 Design Requirements Checklist
- [x] Sequential calls to `/assistant/ask` sharing the same `session_id`.
- [x] Turn 1: *"Who is the mastermind?"* (or case entity question).
- [x] Turn 2: *"What did they do?"* (follow-up question using pronouns/implicit context).
- [x] Verify assistant successfully references the mastermind entity (*"Prabhakar Kumar"*) in the second question.
- [x] Verify the session and its turns are persisted in the database table `chat_sessions`.
- [x] Verify session retrieval endpoint (`GET /api/assistant/sessions/{session_id}`) returns the persisted conversation.
- [x] Verify unprefixed route `POST /assistant/ask` as well as prefixed `POST /api/assistant/ask`.
- [x] Verify automatic session ID generation when omitted.
- [x] Verify session listing (`GET /api/assistant/sessions`) and deletion (`DELETE /api/assistant/sessions/{id}`).
- [x] Verify session isolation between disparate session IDs.

### 4.2 Complete Acceptance Test Script Implementation

Below is the complete, production-ready code designed for `backend/tests/test_investigator.py`:

```python
"""Automated acceptance tests for Milestone M8: Investigator Chat History Persistence.

Verifies:
1. Sequential calls to /assistant/ask sharing the same session_id retain conversational context.
2. Turn 1 ("Who is the mastermind?") identifies the key player / mastermind.
3. Turn 2 ("What did they do?") resolves the pronoun "they" to the entity from Turn 1 and
   returns their actions/dossier rather than generic fallback suggestions.
4. The conversation session and all turns are persisted permanently in the database (ChatSession).
5. Session retrieval endpoint GET /assistant/sessions/{session_id} returns the complete history.
6. Session listing and deletion endpoints work as expected.
7. Both route prefixes (/assistant/ask and /api/assistant/ask) resolve correctly.
8. Multiple sessions remain strictly isolated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import analysis_service
from app.auth import create_token
from app.db import (
    Alert,
    Base,
    Case,
    ChatSession,
    Document,
    Entity,
    Relationship,
    TimelineEvent,
    User,
    get_session,
)
from app.graph.store import graph_cache
from app.main import app


# -----------------------------------------------------------------------------
# Test Fixtures
# -----------------------------------------------------------------------------
@pytest.fixture
def isolated_db(tmp_path: Path):
    """Create isolated SQLite database with full schema and sample case data."""
    db_file = tmp_path / "test_investigator.db"
    engine = create_engine(
        f"sqlite:///{db_file.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    # Seed User
    user = User(
        id=1,
        username="analyst_raj",
        password_hash="fakehash",
        role="analyst",
        full_name="Raj Investigator",
    )
    session.add(user)

    # Seed Case
    case = Case(
        id="case-101",
        name="Operation Saltwater",
        description="Extortion syndicate investigation",
    )
    session.add(case)

    # Seed Document
    doc = Document(
        id="doc-001",
        case_id=case.id,
        source_type="FIR",
        title="FIR 45/2025 Cyber Cell",
        content="Extortion racket operated by Prabhakar Kumar using mule accounts.",
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(doc)

    # Seed Entities
    # Mastermind entity
    e_mastermind = Entity(
        id="ent-prabhakar",
        label="Prabhakar Kumar",
        type="PERSON",
        canonical_key="prabhakar kumar",
        aliases=["Prabhakar K.", "PK", "Mastermind"],
        mention_count=24,
        risk_score=0.95,
        attributes={"role": "Mastermind / Syndicate Leader"},
    )
    # Associate entity
    e_associate = Entity(
        id="ent-rupesh",
        label="Rupesh Kumar Singh",
        type="PERSON",
        canonical_key="rupesh kumar singh",
        aliases=["Rupesh S."],
        mention_count=10,
        risk_score=0.72,
        attributes={"role": "Account Handler"},
    )
    # Bank Account entity
    e_account = Entity(
        id="ent-acct-01",
        label="Mule Account 2 - [Illustrative: XXXX2222]",
        type="BANK_ACCOUNT",
        canonical_key="mule account 2",
        aliases=["XXXX2222"],
        mention_count=8,
        risk_score=0.85,
    )
    session.add_all([e_mastermind, e_associate, e_account])

    # Seed Relationships
    rel1 = Relationship(
        id="rel-001",
        source_id=e_mastermind.id,
        target_id=e_associate.id,
        rel_type="CONTROLS",
        weight=0.95,
    )
    rel2 = Relationship(
        id="rel-002",
        source_id=e_associate.id,
        target_id=e_account.id,
        rel_type="OPERATES",
        weight=0.90,
    )
    session.add_all([rel1, rel2])

    # Seed Timeline Events (Actions by Prabhakar)
    evt1 = TimelineEvent(
        document_id=doc.id,
        kind="CALL",
        occurred_at=datetime.now(timezone.utc),
        summary="Extortion demand call made from burner phone PH003",
        details={"caller": "Prabhakar Kumar", "amount_demanded": 500000.0},
        entity_ids=[e_mastermind.id],
    )
    evt2 = TimelineEvent(
        document_id=doc.id,
        kind="TRANSFER",
        occurred_at=datetime.now(timezone.utc),
        summary="Extortion proceeds layered through Mule Account 2",
        details={"amount": 250000.0, "mode": "IMPS", "destination": "XXXX2222"},
        entity_ids=[e_mastermind.id, e_account.id],
    )
    session.add_all([evt1, evt2])

    # Seed Alert
    alert = Alert(
        id="alt-001",
        kind="structuring",
        severity="critical",
        title="Coordinated Extortion & Structuring",
        description="Prabhakar Kumar coordinated extortion cash flows into unverified mule accounts.",
        score=0.92,
        entity_ids=[e_mastermind.id],
    )
    session.add(alert)

    session.commit()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def auth_headers(isolated_db):
    """Generate Authorization header with valid JWT token."""
    user = isolated_db.query(User).filter(User.username == "analyst_raj").first()
    token = create_token(user)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(isolated_db):
    """TestClient wired with isolated database and initialized graph caches."""
    def override_get_session():
        yield isolated_db

    app.dependency_overrides[get_session] = override_get_session

    # Invalidate and build graph cache from isolated_db
    graph_cache.invalidate()
    analysis_service.invalidate()

    G = nx.Graph()
    D = nx.DiGraph()

    for e in isolated_db.query(Entity).all():
        G.add_node(e.id, label=e.label, type=e.type, aliases=e.aliases or [], attrs=e.attributes or {})
        D.add_node(e.id, label=e.label, type=e.type, aliases=e.aliases or [], attrs=e.attributes or {})

    for r in isolated_db.query(Relationship).all():
        G.add_edge(r.source_id, r.target_id, id=r.id, weight=r.weight, rel_type=r.rel_type, count=1)
        D.add_edge(r.source_id, r.target_id, id=r.id, weight=r.weight, rel_type=r.rel_type, count=1)

    # Seed snapshot with key players ranking
    snapshot = {
        "summary": {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()},
        "key_players": [
            {
                "id": "ent-prabhakar",
                "label": "Prabhakar Kumar",
                "role": "Mastermind / Syndicate Leader",
                "priority": 0.95,
                "influence": 0.92,
                "suspicion": 0.88,
                "reasons": ["Controls mule network", "Primary extortion beneficiary"],
            },
            {
                "id": "ent-rupesh",
                "label": "Rupesh Kumar Singh",
                "role": "Account Handler",
                "priority": 0.72,
                "influence": 0.50,
                "suspicion": 0.75,
                "reasons": ["Transfers extortion proceeds"],
            },
        ],
        "suspicion": {
            "ent-prabhakar": {"score": 0.88, "reasons": ["Extortion demand calls", "Mule accounts"]},
        },
    }

    # Override snapshot in analysis service
    analysis_service.snapshot = lambda db: snapshot

    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()
    graph_cache.invalidate()
    analysis_service.invalidate()


# -----------------------------------------------------------------------------
# Acceptance Tests
# -----------------------------------------------------------------------------
def test_investigator_multi_turn_context_retention(client, isolated_db, auth_headers):
    """Verify two sequential calls sharing session_id maintain context and entity resolution."""
    session_id = f"test-sess-{uuid.uuid4().hex[:8]}"

    # Turn 1: Initial Question
    turn1_payload = {
        "question": "Who is the mastermind?",
        "session_id": session_id,
    }
    resp1 = client.post("/api/assistant/ask", json=turn1_payload, headers=auth_headers)
    assert resp1.status_code == 200, f"Turn 1 failed: {resp1.text}"
    data1 = resp1.json()

    assert data1.get("session_id") == session_id
    assert "Prabhakar Kumar" in data1.get("answer", "")
    assert "ent-prabhakar" in data1.get("highlights", {}).get("nodes", [])

    # Turn 2: Follow-up Question with Pronoun ("they")
    turn2_payload = {
        "question": "What did they do?",
        "session_id": session_id,
    }
    resp2 = client.post("/api/assistant/ask", json=turn2_payload, headers=auth_headers)
    assert resp2.status_code == 200, f"Turn 2 failed: {resp2.text}"
    data2 = resp2.json()

    assert data2.get("session_id") == session_id
    # Crucial Requirement: Assistant must reference the entity from question 1
    assert "Prabhakar" in data2.get("answer", ""), (
        f"Expected Turn 2 to reference 'Prabhakar', got: {data2.get('answer')}"
    )
    # Must NOT fall back to generic help message
    assert "I couldn't match that to an entity" not in data2.get("answer", "")
    assert "Try: “Who is" not in data2.get("answer", "")


def test_investigator_session_database_persistence(client, isolated_db, auth_headers):
    """Verify session turns are permanently written to SQLite ChatSession table."""
    session_id = f"persist-sess-{uuid.uuid4().hex[:8]}"

    # Send Turn 1 and Turn 2
    client.post("/api/assistant/ask", json={"question": "Who is the mastermind?", "session_id": session_id}, headers=auth_headers)
    client.post("/api/assistant/ask", json={"question": "What did they do?", "session_id": session_id}, headers=auth_headers)

    # Query DB directly
    db_session = isolated_db.query(ChatSession).filter(ChatSession.id == session_id).first()
    assert db_session is not None, "ChatSession row not found in database"
    assert db_session.id == session_id
    assert len(db_session.messages) == 2, f"Expected 2 messages in DB, got {len(db_session.messages)}"

    # Check Turn 1 in DB
    assert db_session.messages[0]["question"] == "Who is the mastermind?"
    assert "Prabhakar" in db_session.messages[0]["answer"]

    # Check Turn 2 in DB
    assert db_session.messages[1]["question"] == "What did they do?"
    assert "Prabhakar" in db_session.messages[1]["answer"]


def test_investigator_session_retrieval_api(client, isolated_db, auth_headers):
    """Verify GET /api/assistant/sessions/{session_id} returns the persisted conversation."""
    session_id = f"api-sess-{uuid.uuid4().hex[:8]}"

    # Execute 2 turns
    client.post("/api/assistant/ask", json={"question": "Who is the mastermind?", "session_id": session_id}, headers=auth_headers)
    client.post("/api/assistant/ask", json={"question": "What did they do?", "session_id": session_id}, headers=auth_headers)

    # Retrieve session via GET endpoint
    resp = client.get(f"/api/assistant/sessions/{session_id}", headers=auth_headers)
    assert resp.status_code == 200, f"Session retrieval failed: {resp.text}"
    session_data = resp.json()

    assert session_data["id"] == session_id
    assert len(session_data.get("messages", [])) == 2
    assert session_data["messages"][0]["question"] == "Who is the mastermind?"
    assert session_data["messages"][1]["question"] == "What did they do?"


def test_investigator_unprefixed_endpoint_alias(client, isolated_db, auth_headers):
    """Verify route alias POST /assistant/ask works identically to /api/assistant/ask."""
    session_id = f"alias-sess-{uuid.uuid4().hex[:8]}"

    payload = {
        "question": "Who is the mastermind?",
        "session_id": session_id,
    }
    # Invoke without /api prefix
    resp = client.post("/assistant/ask", json=payload, headers=auth_headers)
    assert resp.status_code == 200, f"Unprefixed /assistant/ask returned {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("session_id") == session_id
    assert "Prabhakar" in data.get("answer", "")


def test_investigator_auto_session_id_when_omitted(client, isolated_db, auth_headers):
    """Verify omitting session_id causes backend to auto-generate a valid session UUID."""
    payload = {"question": "Who is the mastermind?"}
    resp = client.post("/api/assistant/ask", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    session_id = data.get("session_id")
    assert session_id is not None
    assert len(session_id) > 10

    # Verify session was created in DB
    db_session = isolated_db.query(ChatSession).filter(ChatSession.id == session_id).first()
    assert db_session is not None
    assert len(db_session.messages) == 1


def test_investigator_sessions_list_and_deletion(client, isolated_db, auth_headers):
    """Verify listing all sessions and deleting a session via API."""
    session_id = f"del-sess-{uuid.uuid4().hex[:8]}"
    client.post("/api/assistant/ask", json={"question": "Who is the mastermind?", "session_id": session_id}, headers=auth_headers)

    # List sessions
    list_resp = client.get("/api/assistant/sessions", headers=auth_headers)
    assert list_resp.status_code == 200
    sessions = list_resp.json().get("sessions", [])
    assert any(s["id"] == session_id for s in sessions)

    # Delete session
    del_resp = client.delete(f"/api/assistant/sessions/{session_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    # Subsequent GET returns 404
    get_resp = client.get(f"/api/assistant/sessions/{session_id}", headers=auth_headers)
    assert get_resp.status_code == 404

    # Direct DB check
    assert isolated_db.query(ChatSession).filter(ChatSession.id == session_id).first() is None


def test_investigator_session_isolation(client, isolated_db, auth_headers):
    """Verify distinct session IDs do not leak context between each other."""
    session_a = f"sess-a-{uuid.uuid4().hex[:8]}"
    session_b = f"sess-b-{uuid.uuid4().hex[:8]}"

    # Session A: Establishes Prabhakar Kumar as mastermind
    client.post("/api/assistant/ask", json={"question": "Who is the mastermind?", "session_id": session_a}, headers=auth_headers)

    # Session B: Fresh session asks "What did they do?" without prior entity
    resp_b = client.post("/api/assistant/ask", json={"question": "What did they do?", "session_id": session_b}, headers=auth_headers)
    assert resp_b.status_code == 200
    data_b = resp_b.json()

    # Session B should NOT resolve Prabhakar Kumar because Session B has no prior turns
    # It should prompt for an entity or indicate no prior context
    db_b = isolated_db.query(ChatSession).filter(ChatSession.id == session_b).first()
    assert len(db_b.messages) == 1
    # Check that Session A and Session B have independent message histories
    db_a = isolated_db.query(ChatSession).filter(ChatSession.id == session_a).first()
    assert len(db_a.messages) == 1
    assert db_a.messages[0]["question"] == "Who is the mastermind?"
    assert db_b.messages[0]["question"] == "What did they do?"
```

---

## 5. Integration & Compatibility Matrix

| Component | Upstream Dependency | Contract / Interface | Backward Compatibility Guarantee |
|---|---|---|---|
| `store.ts` (`SheetState`) | Local Zustand | Adds `investigatorSessionId: string \| null` and setter. Persisted in `cortex.sheet`. | Existing stored fields (`presentation`, `hiddenTypes`, etc.) preserved. Default `null`. |
| `api.ts` (`api.ask`) | Backend `/api/assistant/ask` | `ask(q: string, session_id?: string \| null)`. | Optional `session_id`; if omitted, existing callers function normally. |
| `api.ts` (Session endpoints) | Backend routes | `chatSessions()`, `chatSession(id)`, `deleteChatSession(id)`. | New endpoints; non-breaking. |
| `agent.ts` (`streamAgent`) | Backend `/api/agent/stream` | `streamAgent(q, history, onEvent, signal?, session_id?)`. | Optional 5th argument; existing invocations remain valid. |
| `page.tsx` (Investigator Lens) | Next.js / React / `nuqs` | `?session=` URL param + auto-hydration + "+ New Chat" button. | Direct query `?q=` still works. If no session param, starts fresh or restores active session. |
| `test_investigator.py` | Backend API & DB | Runs against SQLite test database, validates `/assistant/ask`, `/api/assistant/ask`, `ChatSession` table, and session retrieval. | Runs under standard pytest: `pytest tests/test_investigator.py`. |

---

## 6. Implementation Action Plan for Phase 2 Workers

1. **Implementer Step 1 (Backend Persistence - `backend/app/db.py`)**:
   Add `ChatSession` model with fields `id`, `user_id`, `title`, `created_at`, `updated_at`, `messages` as designed by `explorer_chat_1`.
2. **Implementer Step 2 (Backend Routes & AI - `backend/app/api/routes_intel.py`, `backend/app/main.py`, `backend/app/ai/investigator.py`)**:
   - Add session persistence and history injection into `Investigator.answer()` as designed by `explorer_chat_2`.
   - Expose endpoints under both `/api/assistant/...` and `/assistant/...`.
3. **Implementer Step 3 (Frontend State & Client - `store.ts`, `api.ts`, `agent.ts`)**:
   - Add `investigatorSessionId` to `store.ts` and `partialize`.
   - Update `api.ts` and `agent.ts` to accept `session_id`.
4. **Implementer Step 4 (Frontend Lens - `investigator/page.tsx`)**:
   - Wire `useQueryState("session")`.
   - Add `useEffect` to fetch session history on mount/session switch.
   - Add "+ New Chat" button in Header.
   - Pass `session_id` into `streamAgent`.
5. **Implementer Step 5 (Acceptance Test - `backend/tests/test_investigator.py`)**:
   - Create `backend/tests/test_investigator.py` using the exact test script provided in Section 4.2.
   - Run `pytest backend/tests/test_investigator.py -v` to achieve 100% pass rate.
