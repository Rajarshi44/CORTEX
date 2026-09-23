# Handoff Report: R1 Database Persistence for Investigator Chat History

**Agent**: `explorer_chat_1`  
**Milestone**: M8 (Investigator Chat History Persistence)  
**Date**: 2026-09-23  

---

## 1. Observation

1. **Database Schema & Models (`backend/app/db.py`)**:
   - `User` model is defined at lines 34–42:
     ```python
     class User(Base):
         __tablename__ = "users"
         id: Mapped[int] = mapped_column(Integer, primary_key=True)
         username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
         password_hash: Mapped[str] = mapped_column(String(255))
         role: Mapped[str] = mapped_column(String(32), default="analyst")  # admin | analyst | viewer
         full_name: Mapped[str] = mapped_column(String(128), default="")
         created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
     ```
   - Primary key convention for entities and documents is `String(36)` UUID:
     - `Case.id`: `Mapped[str] = mapped_column(String(36), primary_key=True)` (line 46)
     - `Document.id`: `Mapped[str] = mapped_column(String(36), primary_key=True)` (line 56)
     - `Entity.id`: `Mapped[str] = mapped_column(String(36), primary_key=True)` (line 70)
     - `Relationship.id`: `Mapped[str] = mapped_column(String(36), primary_key=True)` (line 87)
     - `Alert.id`: `Mapped[str] = mapped_column(String(36), primary_key=True)` (line 136)
     - `Watch.id`: `Mapped[str] = mapped_column(String(36), primary_key=True)` (line 189)
   - JSON columns are extensively used for nested collections and rich payloads:
     - `Document.meta`: `Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)` (line 61)
     - `Entity.aliases`: `Mapped[list[str]] = mapped_column(JSON, default=list)` (line 74)
     - `TimelineEvent.details`: `Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)` (line 129)
     - `Alert.evidence`: `Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)` (line 144)
     - `AnalysisSnapshot.payload`: `Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)` (line 238)

2. **Engine, Pragmas & Session Management (`backend/app/db.py`)**:
   - Engine and SQLite WAL / foreign key pragmas at lines 246–260:
     ```python
     connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
     engine = create_engine(settings.database_url, connect_args=connect_args, json_serializer=json.dumps)

     if settings.database_url.startswith("sqlite"):
         @event.listens_for(engine, "connect")
         def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - trivial
             cur = dbapi_conn.cursor()
             cur.execute("PRAGMA journal_mode=WAL")
             cur.execute("PRAGMA synchronous=NORMAL")
             cur.execute("PRAGMA foreign_keys=ON")
             cur.close()

     SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
     ```
   - Notice: `PRAGMA foreign_keys=ON` is active on every connection.
   - `init_db()` is at lines 263–268:
     ```python
     def init_db() -> None:
         from .graph import ledger  # noqa: F401  (registers the evidence_ledger table on Base)

         Base.metadata.create_all(engine)
         ledger.ensure_ledger_schema(engine)
     ```

3. **Application Startup Hooks (`backend/app/main.py`)**:
   - `lifespan` hook calls `init_db()` at lines 29–33:
     ```python
     @asynccontextmanager
     async def lifespan(app: FastAPI):
         init_db()
         db = SessionLocal()
         try:
             bootstrap_users(db)
     ```
   - No database migrations (e.g., Alembic) exist in the repository. All schema management relies on SQLAlchemy `Base.metadata.create_all(engine)`.

4. **Investigator Q&A History Format (`backend/app/ai/agent.py` & `routes_intel.py`)**:
   - `InvestigatorAgent._history(turns)` at lines 158–166 of `backend/app/ai/agent.py`:
     ```python
     @staticmethod
     def _history(turns: list[dict] | None) -> list[dict]:
         out: list[dict] = []
         for t in (turns or [])[-6:]:
             if q := (t.get("question") or t.get("q") or "").strip():
                 out.append({"role": "user", "content": [{"type": "text", "text": q}]})
             if a := (t.get("answer") or t.get("a") or "").strip():
                 out.append({"role": "assistant", "content": [{"type": "text", "text": a[:2500]}]})
         return out
     ```
   - In `backend/app/api/routes_intel.py` lines 121–129:
     ```python
     @router.post("/assistant/ask")
     def ask(body: Ask, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
         G, D = graph_cache.get(db), graph_cache.get_directed(db)
         snap = analysis_service.snapshot(db)
         res = Investigator(db, G, D, snap).answer(body.question)
         audit(db, user, "assistant_query", body.question)
         res["highlight_nodes"] = [{"id": n, "label": G.nodes[n]["label"], "type": G.nodes[n]["type"]} for n in res["highlights"]["nodes"] if n in G]
         return res
     ```

5. **Frontend History Expectations (`frontend-next/src/app/(sheet)/investigator/page.tsx`)**:
   - Turns are represented in UI state with `Turn`: `id`, `q`, `text`, `calls`, `visuals`, `highlights`, `citations`. Currently held in `useSheet((s) => s.investigatorTurns)` in Zustand, which is NOT persisted in `partialize` and lost on page reload.

---

## 2. Logic Chain

1. **Foreign Key Typing and Nullability** (from Observation 1 and 2):
   - `User.id` is defined as `Integer` (int). Therefore, any foreign key pointing to `users.id` must be typed as `Integer`, not `String(36)`.
   - Because `PRAGMA foreign_keys=ON` is strictly enforced on all SQLite connections, any non-null `user_id` pointing to an uncommitted or missing user ID will raise `IntegrityError`.
   - In tests and unauthenticated environments, queries may run without an authenticated user.
   - **Inference**: `user_id` MUST be defined as `Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)`.

2. **JSON Column vs Relational ChatMessage** (from Observation 1 and 4):
   - Across `backend/app/db.py`, document metadata, timeline details, alert evidence, and analysis snapshots all use `JSON` columns.
   - An investigator response contains rich composite structures: charts, graph nodes/edges, tables, timelines (`visuals`), tool calls (`calls`), citations, and highlights.
   - A normalized `chat_messages` table would either require additional child tables (`chat_visuals`, `chat_citations`) or a JSON `meta` column inside `ChatMessage` anyway, while introducing join overhead and multi-row write transactions.
   - In contrast, storing `messages` as a structured JSON list on `ChatSession` provides `O(1)` atomic reads and writes, zero join complexity, and directly maps to `InvestigatorAgent._history(turns)`.
   - **Inference**: A JSON column `messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)` on `ChatSession` is the cleanest, most performant, and most idiomatic design for this codebase.

3. **Table Initialization and Zero-Migration Deployment** (from Observation 2 and 3):
   - `backend/app/main.py` runs `init_db()` in its lifespan handler, which executes `Base.metadata.create_all(engine)`.
   - Pytest fixtures in `backend/tests/` similarly execute `Base.metadata.create_all(engine)`.
   - **Inference**: Simply adding `ChatSession(Base)` to `backend/app/db.py` ensures that all tables are created automatically on application launch and during test runs, with zero Alembic migrations needed.

4. **SQLAlchemy Mutation Tracking Trap**:
   - In SQLAlchemy, mutating an in-place Python list on a JSON column (`session.messages.append(turn)`) does not trigger dirty-attribute tracking. Calling `db.commit()` without reassigning the list or calling `flag_modified` results in a silent failure to persist.
   - **Inference**: All helper functions that mutate `messages` must explicitly reassign the attribute: `session.messages = list(session.messages or []) + [turn]`.

---

## 3. Caveats

1. **SQLite JSON Storage**:
   SQLite stores JSON as text under the hood. For conversations exceeding 100 turns, serializing large visualization blobs could grow the session row size. However, investigator sessions typically span 5–20 turns, and LLM context window limits (`max_turns=6`) make this well within standard limits.
2. **User Tenancy Scoping**:
   If an analyst logs in as user A, should user A be able to see sessions created by user B? The helper functions support optional filtering by `user_id`, allowing the endpoint layer (`explorer_chat_2`) to decide whether sessions are user-scoped or team-wide.
3. **Model Placement**:
   `ChatSession` can be placed directly in `backend/app/db.py`. If a separate models file is ever created in the future, it would require refactoring `db.py` imports.
4. **Live E2E Test vs Unit Tests**:
   `test_live_agent_db_and_llm_e2e` in `backend/tests/test_m5_investigator_chat.py` executes against live LLM providers if an API key is in the environment. If the upstream provider returns an error (e.g. model deprecation or quota), that specific e2e test will fail even though the codebase and all other 116 unit/mocked tests pass completely.


---

## 4. Conclusion

1. **Recommended Model (`ChatSession` in `backend/app/db.py`)**:
   ```python
   import uuid
   from datetime import datetime
   from typing import Any
   from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
   from sqlalchemy.orm import Mapped, mapped_column, relationship

   class ChatSession(Base):
       __tablename__ = "chat_sessions"

       id: Mapped[str] = mapped_column(
           String(36),
           primary_key=True,
           default=lambda: str(uuid.uuid4())
       )
       user_id: Mapped[int | None] = mapped_column(
           Integer,
           ForeignKey("users.id", ondelete="SET NULL"),
           nullable=True,
           index=True
       )
       title: Mapped[str] = mapped_column(String(255), default="Investigation Session")
       created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
       updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)
       messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

       user: Mapped[User | None] = relationship("User", foreign_keys=[user_id])

       __table_args__ = (
           Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
       )
   ```

2. **Core Helper Functions**:
   - `create_chat_session(db, user_id=None, title="Investigation Session", initial_messages=None) -> ChatSession`
   - `get_chat_session(db, session_id, user_id=None) -> ChatSession | None`
   - `append_chat_turn(db, session_id, question, answer, visuals=None, highlights=None, highlight_nodes=None, citations=None, calls=None, metadata=None, title=None) -> ChatSession | None`
   - `list_chat_sessions(db, user_id=None, limit=50, offset=0) -> list[ChatSession]`
   - `delete_chat_session(db, session_id, user_id=None) -> bool`
   - `format_session_history_for_llm(session, max_turns=6) -> list[dict[str, str]]`

3. **Complete reference implementation details and trade-offs are preserved in `analysis.md`**.

---

## 5. Verification Method

1. **Verify Schema Creation**:
   Run Python interactive shell or pytest using the project test command to verify that `Base.metadata.create_all(engine)` registers and creates `chat_sessions`:
   ```powershell
   cd "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend"
   python -c "from app.db import Base, engine, init_db; init_db(); assert 'chat_sessions' in Base.metadata.tables; print('chat_sessions verified!')"
   ```
2. **Verify Helper CRUD Operations**:
   Execute a quick test script checking session creation, turn appending, JSON persistence, and session retrieval:
   ```powershell
   python -c "from app.db import SessionLocal, create_chat_session, append_chat_turn, get_chat_session; db=SessionLocal(); s=create_chat_session(db, title='Test'); append_chat_turn(db, s.id, 'Who is X?', 'X is mastermind'); s2=get_chat_session(db, s.id); assert len(s2.messages)==1; assert s2.messages[0]['question']=='Who is X?'; print('CRUD verified!')"
   ```
3. **Run Existing Test Suite**:
   Verify no regressions in existing tests:
   ```powershell
   cd "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend"
   pytest tests/test_m5_investigator_chat.py -v
   ```
4. **Invalidation Conditions**:
   - If SQLite rejects foreign keys on `chat_sessions.user_id`, ensure `nullable=True` is set and `user_id` matches an existing row in `users.id` (or is `None`).
   - If appended messages disappear after commit, verify list reassignment (`session.messages = list(...)`) rather than in-place `.append()`.
