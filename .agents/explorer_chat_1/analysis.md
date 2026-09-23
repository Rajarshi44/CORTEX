# R1 Database Persistence Architecture & Schema Investigation

## 1. Executive Summary

This investigation analyzes the database persistence architecture of the CORTEX platform (`backend/app/db.py`, `backend/app/auth.py`, `backend/app/main.py`) to specify the schema and integration pattern for **Milestone M8: Investigator Chat History Persistence**.

The platform uses **SQLAlchemy 2.0** with `DeclarativeBase` and `Mapped[...]` typed columns over SQLite (with PostgreSQL dialect compatibility). Foreign key enforcement is strictly enabled via `PRAGMA foreign_keys=ON`. Table creation is driven automatically on application startup by `Base.metadata.create_all(engine)` inside `init_db()`. No Alembic migration manager is configured; `create_all()` is idempotent and will automatically create newly registered tables on the next startup.

We recommend a **Dual-Capable / Hybrid Schema**:
1. **`ChatSession`** as the primary aggregate root storing session metadata (`id: UUID str(36)`, `user_id: int` FK to `users.id`, `title: str(255)`, timestamps `created_at`, `updated_at`, and structured JSON turn history `messages = mapped_column(JSON, default=list)`).
2. **`ChatMessage`** as an accompanying normalized relational table (`id: str(36)`, `session_id: str(36)` FK to `chat_sessions.id`, `role: str(16)`, `content: Text`, `extra_data: JSON`, `created_at: DateTime`).

This gives the implementing team the best of both worlds:
- Zero-overhead turn serialization and 1-query instant history retrieval for LLM context replay via `ChatSession.messages` (1:1 matching the frontend `Turn` interface and `InvestigatorAgent` history parameter).
- Granular relational tracking, cascade deletion, and SQL indexing via `ChatMessage`.

---

## 2. Deep Dive: Current Database Architecture (`backend/app/db.py`)

### 2.1 Base & Mapped Types
In `backend/app/db.py` (lines 30-31):
```python
class Base(DeclarativeBase):
    pass
```
All models inherit from `Base` using modern SQLAlchemy 2.0 syntax:
- Explicit type annotations: `Mapped[T]`
- Column specifications: `mapped_column(Type, ...)`
- Standard helper for timestamps: `utcnow()` (lines 26-27):
  ```python
  def utcnow() -> datetime:
      return datetime.now(timezone.utc)
  ```
  Note: In column definitions, `default=utcnow` passes the callable so timestamps reflect the insertion moment.

### 2.2 The `User` Model
`User` is defined in `backend/app/db.py` (lines 34-42):
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
**Key Observation**: `User.id` is an `Integer` primary key (autoincrementing). Therefore, any foreign key referencing `User` MUST be typed as `Integer`:
```python
user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
```

### 2.3 SQLite Configuration & Foreign Key Enforcement
Lines 246-258 of `backend/app/db.py`:
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
```
**Critical Consequence**:
- `PRAGMA foreign_keys=ON` is active on every SQLite connection.
- If a row references `users.id`, that user MUST exist in `users`, or SQLite throws `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
- `nullable=True` on `user_id` allows sessions in test fixtures or unauthenticated mock endpoints to operate cleanly without requiring synthetic user bootstrapping, while preserving full integrity when `user_id` is supplied.

### 2.4 Database Initialization & Lifecycle (`init_db()`)
In `backend/app/db.py` (lines 263-268):
```python
def init_db() -> None:
    from .graph import ledger  # noqa: F401  (registers the evidence_ledger table on Base)

    Base.metadata.create_all(engine)
    ledger.ensure_ledger_schema(engine)
```
In `backend/app/main.py` (lines 29-33):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        bootstrap_users(db)
        ...
```
- `Base.metadata.create_all(engine)` inspects all subclasses of `Base` registered in memory.
- It executes `CREATE TABLE IF NOT EXISTS` for all registered models.
- There is **no Alembic migration tool** in the project.
- **Result for new models**: Adding `ChatSession` and `ChatMessage` to `backend/app/db.py` ensures they are automatically created the moment the server boots up or a test fixture executes `Base.metadata.create_all(engine)`. No manual DDL migration is required.

---

## 3. User Authentication & Multi-Tenancy

### 3.1 Authentication Mechanism (`backend/app/auth.py`)
- Authentication uses JWT tokens signed with `settings.jwt_secret`.
- `current_user` dependency (lines 46-56):
  ```python
  def current_user(token: Annotated[str | None, Depends(oauth2)], db: Annotated[Session, Depends(get_session)]) -> User:
      if not token:
          raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
      try:
          payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
      except jwt.PyJWTError:
          raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
      user = db.query(User).filter(User.username == payload.get("sub")).first()
      if not user:
          raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
      return user
  ```
- `optional_user` dependency (lines 59-66) returns `User | None` if unauthenticated.
- `bootstrap_users(db)` creates two default users if the table is empty:
  - Admin: `admin` (`bootstrap_admin_password`)
  - Analyst: `analyst` (`bootstrap_analyst_password`)

### 3.2 Session Isolation
To maintain analyst privacy and data boundaries:
- All queries listing or retrieving sessions must filter by `ChatSession.user_id == user.id`:
  ```python
  sessions = db.query(ChatSession).filter(ChatSession.user_id == user.id).order_by(ChatSession.updated_at.desc()).all()
  ```
- Non-admin users attempting to access another user's session must receive a `404 Not Found` (or `403 Forbidden`).

---

## 4. Storage Architecture Comparison: JSON Column vs Relational Table

| Dimension | Pure JSON Column (`ChatSession.messages`) | Relational Table (`ChatMessage`) | Hybrid (Recommended) |
| :--- | :--- | :--- | :--- |
| **Model Structure** | 1 table (`chat_sessions`) | 2 tables (`chat_sessions` + `chat_messages`) | 2 tables, with turn payload in session + message rows |
| **Query Complexity** | Single indexed `SELECT * FROM chat_sessions WHERE id = :id` | `JOIN` or two queries (`SELECT * FROM chat_messages WHERE session_id = :id ORDER BY created_at ASC`) | Single query for fast chat load; relational table for auditing & individual message operations |
| **Turn Matching with Agent** | Exact 1:1 match with `InvestigatorAgent` history: `[{"question": ..., "answer": ...}]` | Requires pairing consecutive `user` and `assistant` rows into turns | `messages` JSON column retains complete paired turn structure seamlessly |
| **Rich Payloads (Visuals, Tool Traces)** | Natural JSON embedding (charts, nodes, citations, tools) | Stored in JSON `extra_data` column on `assistant` message row | Both options available |
| **Concurrency / Mutation** | Must reassign `session.messages = [*session.messages, turn]` to trigger SQLAlchemy dirty flag | `db.add(ChatMessage(...))` tracks row individually | Clean turn appending via list reassignment |
| **Cascade Deletion** | Trivial (single row deletion) | Enforced via `ForeignKey(..., ondelete="CASCADE")` | Handled via DB-level foreign key CASCADE |

### Key SQLAlchemy Pitfall & Solution for JSON Column
In SQLAlchemy, mutating an in-place Python list attribute (e.g. `session.messages.append(...)`) does **NOT** flag the column as modified unless `MutableList` is used or the list is reassigned.
**Best Practice**:
Always reassign the list when appending:
```python
session.messages = list(session.messages or []) + [new_turn]
session.updated_at = utcnow()
db.commit()
```
This guarantees that SQLAlchemy emits the `UPDATE chat_sessions SET messages = ?, updated_at = ? WHERE id = ?` statement on commit.

---

## 5. Concrete Schema Design

### 5.1 Python Code Specification for `backend/app/db.py`

```python
import uuid
from typing import Any
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# --------------------------------------------------------------------------------------
# Chat Session & Message Persistence (M8)
# --------------------------------------------------------------------------------------

class ChatSession(Base):
    """An ongoing or historical investigator conversation session.
    
    Tied to the authenticated User. Stores the high-level metadata (title, timestamps)
    and retains the sequence of turns in `messages` as a structured JSON list for instant
    retrieval and LLM context reconstruction.
    """
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    case_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="New Investigation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)
    
    # Structured JSON turns: list of turn dicts containing {id, question, answer, highlights, visuals, citations, timestamp}
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    # Relationships
    user: Mapped[User | None] = relationship()
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )

    __table_args__ = (
        Index("ix_chat_sessions_user_updated", "user_id", "updated_at"),
    )


class ChatMessage(Base):
    """Normalized individual message record in a chat session.
    
    Used for fine-grained audit logging, relational queries, or individual turn tracking.
    """
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), index=True)  # "user" | "assistant" | "system"
    content: Mapped[str] = mapped_column(Text, default="")
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # highlights, visuals, citations, tool calls
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="chat_messages")

    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )
```

### 5.2 Field-by-Field Breakdown

#### `ChatSession`
- `id`: `String(36)`, UUIDv4 string, primary key.
- `user_id`: `Integer`, nullable FK to `users.id` with `ondelete="CASCADE"`. Indexed.
- `case_id`: `String(36)`, nullable FK to `cases.id` with `ondelete="SET NULL"`. Indexed.
- `title`: `String(255)`, human-readable title. Defaults to `"New Investigation"` or truncated initial query (e.g. `question[:60]`).
- `created_at`: `DateTime`, defaults to `utcnow`. Indexed.
- `updated_at`: `DateTime`, defaults to `utcnow`, auto-updated on change. Indexed.
- `messages`: `JSON`, defaults to empty list `[]`. Stores complete turn history.
- `Index("ix_chat_sessions_user_updated", "user_id", "updated_at")`: Optimizes `SELECT ... WHERE user_id = ? ORDER BY updated_at DESC`.

#### `ChatMessage`
- `id`: `String(36)`, UUIDv4 string, primary key.
- `session_id`: `String(36)`, FK to `chat_sessions.id` with `ondelete="CASCADE"`. Indexed.
- `role`: `String(16)`, `"user"`, `"assistant"`, or `"system"`. Indexed.
- `content`: `Text`, verbatim markdown / message text.
- `extra_data`: `JSON`, dictionary storing `highlights`, `visuals`, `citations`, and `calls`.
- `created_at`: `DateTime`, defaults to `utcnow`. Indexed.
- `Index("ix_chat_messages_session_created", "session_id", "created_at")`: Optimizes chronological ordering of session messages.

---

## 6. Integration Contract for API Endpoints (`routes_intel.py` / `routes_agent.py`)

### 6.1 `POST /api/assistant/ask`
**Request Payload**:
```json
{
  "question": "Who runs this network, and what makes you say so?",
  "session_id": "optional-uuid-string-or-null"
}
```

**Flow**:
1. Check `session_id`:
   - If provided: retrieve `ChatSession` from DB where `id == session_id` and `user_id == user.id`. If not found, create new or raise 404.
   - If not provided or null: instantiate new `ChatSession(id=str(uuid.uuid4()), user_id=user.id, title=question[:60])`.
2. Extract past history turns from `session.messages`:
   ```python
   history = [
       {"question": turn["question"], "answer": turn["answer"]}
       for turn in session.messages
       if turn.get("question") and turn.get("answer")
   ]
   ```
3. Execute agent logic with history context:
   ```python
   # Using Investigator or InvestigatorAgent
   res = investigator.answer(body.question, history=history)
   ```
4. Append new turn to `session.messages`:
   ```python
   new_turn = {
       "id": str(uuid.uuid4()),
       "question": body.question,
       "answer": res["answer"],
       "highlight_nodes": res.get("highlight_nodes", []),
       "highlights": res.get("highlights", {}),
       "visuals": res.get("visuals", []),
       "citations": res.get("citations", []),
       "timestamp": utcnow().isoformat()
   }
   session.messages = list(session.messages or []) + [new_turn]
   session.updated_at = utcnow()
   db.add(session)
   db.commit()
   ```
5. Return response containing `session_id`:
   ```python
   res["session_id"] = session.id
   return res
   ```

### 6.2 `GET /api/assistant/sessions`
Returns list of sessions for current user:
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "Who runs this network, and what makes you...",
    "created_at": "2026-09-23T12:00:00Z",
    "updated_at": "2026-09-23T12:05:00Z",
    "turn_count": 3
  }
]
```

### 6.3 `GET /api/assistant/sessions/{session_id}`
Returns complete session detail and turns:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Who runs this network...",
  "created_at": "2026-09-23T12:00:00Z",
  "updated_at": "2026-09-23T12:05:00Z",
  "messages": [...]
}
```

### 6.4 `DELETE /api/assistant/sessions/{session_id}`
Deletes session and cascades to all associated messages.
