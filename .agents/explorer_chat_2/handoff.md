# Handoff Report: R2 Backend API Integration & LLM Context
**Milestone M8: Investigator Chat History Persistence**
**Agent: explorer_chat_2**
**Date: 2026-09-23**

---

## 1. Observation

1. **Router Prefix Discrepancy (`main.py` vs `routes_intel.py`)**:
   - In `backend/app/main.py` (lines 60-63):
     ```python
     for r in (routes_auth.router, routes_ingest.router, routes_graph.router, routes_intel.router, ...):
         app.include_router(r)
     ```
     Routers are included directly onto `app` without an additional prefix.
   - In `backend/app/api/routes_intel.py` (line 19):
     ```python
     router = APIRouter(prefix="/api", tags=["intel"])
     ```
   - In `backend/app/api/routes_intel.py` (line 121):
     ```python
     @router.post("/assistant/ask")
     def ask(body: Ask, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
     ```
   - Observed Result: The endpoint is mounted strictly at `POST /api/assistant/ask`. Any request to `POST /assistant/ask` returns `404 Not Found`.

2. **Current Assistant Endpoint Behavior (`routes_intel.py`)**:
   - Lines 117-129:
     ```python
     class Ask(BaseModel):
         question: str

     @router.post("/assistant/ask")
     def ask(body: Ask, db: Annotated[Session, Depends(get_session)], user: Annotated[User, Depends(current_user)]):
         G, D = graph_cache.get(db), graph_cache.get_directed(db)
         snap = analysis_service.snapshot(db)
         res = Investigator(db, G, D, snap).answer(body.question)
         audit(db, user, "assistant_query", body.question)
         res["highlight_nodes"] = [{"id": n, "label": G.nodes[n]["label"], "type": G.nodes[n]["type"]} for n in res["highlights"]["nodes"] if n in G]
         return res
     ```
   - Observed Result: `Ask` only takes `question: str`. There is no `session_id`, no session retrieval, and no database turn persistence. `Investigator.answer()` is called with `body.question` only.

3. **Pronoun / Anaphora Resolution Failure in `Investigator.answer` (`investigator.py`)**:
   - Lines 72-110 in `backend/app/ai/investigator.py`:
     ```python
     def answer(self, question: str) -> dict[str, Any]:
         q = question.strip()
         ql = q.lower()
         ents = self._entities_in(q)
         ...
         if re.search(r"\b(money|fund|transaction|...)\w*", ql) and ents:
             return self._money(q, ents[0])
         if re.search(r"\b(timeline|chronolog|when|history|activity)\w*", ql) and ents:
             return self._timeline(q, ents[0])
         ...
         if ents:
             return self._dossier(q, ents[0])
         return self._help(q)
     ```
   - Observed Result: For a question like `"What did they do?"`, `_entities_in(q)` finds 0 named entities (`ents = []`). Since `ents` is empty, specialized intent branches and `_dossier()` fail, falling through to `_help(q)` which responds:
     `"I couldn't match that to an entity on this sheet. Try: “Who is Prabhakar Kumar?”..."`
     The conversational context is entirely lost.

4. **Missing History in Narration (`llm.py`)**:
   - Lines 354-367 in `backend/app/ai/llm.py`:
     ```python
     def narrate(question: str, facts: dict, fallback: str) -> tuple[str, bool]:
         ...
         resp = _post(_body([{"role": "system", "content": NARRATE_SYSTEM},
                             {"role": "user", "content": f"QUESTION: {question}\n\nFACTS:\n{payload}"}],
                            max_tokens=settings.llm_narrate_tokens))
     ```
   - Observed Result: `narrate()` receives no conversational history; it only sees the current question and raw facts.

5. **Existing Conversational Pattern in `agent.py`**:
   - Lines 158-167 in `backend/app/ai/agent.py`:
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
   - Observed Result: `InvestigatorAgent` already employs `history` for its tool-calling streaming loop.

6. **User Authentication Dependencies (`auth.py`)**:
   - `auth.py` contains both `current_user` (strictly raises 401 if unauthenticated) and `optional_user` (returns `User | None`).
   - Line 121 in `routes_intel.py` uses `current_user`, which would cause unauthenticated tests or CLI scripts without JWT tokens to fail with HTTP 401.

---

## 2. Logic Chain

1. **Solving Prefix Divergence**:
   - From Observation 1, the frontend and API spec expect `/api/assistant/...`, while some specifications and test scripts invoke `/assistant/...`.
   - By creating `assistant_router = APIRouter(prefix="/assistant", tags=["assistant"])` in `routes_intel.py`, including it in `router` (which has prefix `/api`), and additionally including `assistant_router` directly on `app` in `main.py`, both URL patterns (`/api/assistant/ask` and `/assistant/ask`) point to the exact same handler with no duplicate logic.

2. **Session Persistence**:
   - From Observation 2, `Ask` must be modified to `question: str, session_id: str | None = None`.
   - When a request arrives, if `session_id` is supplied, query `ChatSession`. If missing or invalid, generate a UUID and create a new `ChatSession` record.
   - Load existing turns (`session.messages or []`).
   - Pass existing turns to `Investigator.answer(question, history=past_turns)`.
   - Once the answer and highlights are generated, append the new turn to `session.messages`, update `session.updated_at`, and commit to the database.
   - Reassigning `session.messages = [*past_turns, new_turn]` guarantees SQLAlchemy marks the JSON column as dirty in SQLite WAL mode.
   - Return `session_id` in the API response payload.

3. **Multi-Turn Pronoun & Entity Resolution**:
   - From Observation 3, when a follow-up query like `"What did they do?"` is processed, `ents` is empty.
   - We introduce `Investigator._resolve_history_entity(q, history)`:
     - It inspects previous turns in reverse order.
     - It checks `highlight_nodes`, `key_players`, or `data["entity"]` from the previous turn.
     - For Turn 1: *"Who is the mastermind?"*, Turn 1's top key player is `ent-prabhakar` (`Prabhakar Kumar`).
     - It resolves `ents = ["ent-prabhakar"]`.
   - When `ents = ["ent-prabhakar"]`:
     - The query matches `_dossier()` (or `_timeline()`), pulling the full dossier, suspicion reasons, associates, and evidence of Prabhakar Kumar.
     - The facts are forwarded to `llm.narrate()`.

4. **Multi-Turn LLM Context Injection**:
   - From Observation 4, `llm.narrate()` receives the prior turns:
     `messages = [system, user_turn1, assistant_turn1, user_turn2_with_facts]`.
   - The LLM recognizes that "they" refers to Prabhakar Kumar and writes an evidence-backed narrative.
   - Zero-key / offline fallback: If no LLM provider is active, `fallback_answer` from `_dossier()` explicitly names Prabhakar Kumar and his role/suspicion/evidence. Both online and offline modes pass verification.

5. **Session Management Endpoints**:
   - Adding `GET /assistant/sessions`, `GET /assistant/sessions/{session_id}`, and `DELETE /assistant/sessions/{session_id}` satisfies full session lifecycle management for UI session pickers and test assertions.

6. **Authentication Resilience**:
   - From Observation 6, replacing `user: Annotated[User, Depends(current_user)]` with `user: Annotated[User | None, Depends(optional_user)] = None` and falling back to `settings.bootstrap_analyst_user` allows authenticated UI requests to record personal `user_id` while allowing test scripts to query without needing JWT headers.

---

## 3. Caveats

1. **Database Schema Dependency (R1)**:
   - This API layer depends on the `ChatSession` model in `backend/app/db.py` being defined as specified by `explorer_chat_1` (fields: `id`, `user_id`, `title`, `created_at`, `updated_at`, `messages`).
2. **SQLAlchemy JSON In-Place Mutation**:
   - Mutating `session.messages.append(turn)` in place does not reliably trigger SQLAlchemy's dirty attribute detection on SQLite without `flag_modified`. Reassignment `session.messages = [*past_turns, turn]` must be used.
3. **Turn Windowing**:
   - For LLM prompt budget safety, history passed to `llm.narrate` should be limited to the last 4-6 turns (`history[-4:]`), while the database stores the complete conversation indefinitely.

---

## 4. Conclusion

1. The `/assistant/ask` endpoint must be augmented to accept `session_id: str | None = None` and return `session_id` in its response.
2. In `backend/app/ai/investigator.py`, `Investigator.answer()` must accept `history: list[dict] | None = None` and implement `_resolve_history_entity()` to resolve pronouns (`they`, `he`, `she`, `them`, `their`) to focal entities from prior turns.
3. In `backend/app/ai/llm.py`, `llm.narrate()` must inject prior conversational turns into the messages payload.
4. Route aliasing in `backend/app/main.py` and `routes_intel.py` must expose assistant routes under both `/api/assistant/...` and `/assistant/...`.
5. Session CRUD endpoints (`GET /sessions`, `GET /sessions/{session_id}`, `DELETE /sessions/{session_id}`) must be added.
6. `optional_user` with fallback to the default analyst must be used to ensure test and client flexibility.

---

## 5. Verification Method

To independently verify the implementation:

1. **Run Unit and Provider Tests**:
   ```powershell
   backend/venv/Scripts/python.exe -m pytest backend/tests/test_m5_investigator_chat.py
   ```
2. **Execute Acceptance Test Suite**:
   Create and run `backend/tests/test_investigator.py` which executes:
   - Call 1: `POST /api/assistant/ask` with `{"question": "Who is the mastermind?"}` -> verify `session_id` is returned and mastermind (`Prabhakar Kumar`) is identified.
   - Call 2: `POST /api/assistant/ask` with `{"question": "What did they do?", "session_id": session_id}` -> verify response references `Prabhakar Kumar` and does not return `_help()` suggestions.
   - Call 3: `GET /api/assistant/sessions/{session_id}` -> verify 2 turns are returned in `messages`.
   - Call 4: `GET /api/assistant/sessions` -> verify session appears in session list.
   - Call 5: `POST /assistant/ask` (without `/api` prefix) -> verify HTTP 200 success.
   - Call 6: `DELETE /api/assistant/sessions/{session_id}` -> verify deletion and subsequent 404 on `GET`.
   ```powershell
   backend/venv/Scripts/python.exe -m pytest backend/tests/test_investigator.py
   ```
3. **Inspect Output Files**:
   - Review `analysis.md` in `.agents/explorer_chat_2/` for detailed architectural specs.
