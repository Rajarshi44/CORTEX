# Handoff Report: R3 Frontend UI Updates & Automated Acceptance Test Design
**Milestone**: M8 (Investigator Chat History Persistence)  
**Agent**: `explorer_chat_3`  
**Date**: 2026-09-23  

---

## 1. Observation

1. **Investigator Lens Turn State Storage (`frontend-next/src/app/(sheet)/investigator/page.tsx`)**:
   - In `investigator/page.tsx` (lines 52–53, 60):
     ```typescript
     const turns = useSheet((s) => s.investigatorTurns) as Turn[];
     const setTurns = useSheet((s) => s.setInvestigatorTurns);
     ...
     const nextId = useRef(turns.length > 0 ? Math.max(...turns.map(t => t.id)) + 1 : 1);
     ```
   - Observed Result: Chat turns are managed solely through `useSheet` Zustand store. There is no `session_id` maintained in local state or URL.

2. **Zustand Persistence Exclusions (`frontend-next/src/lib/store.ts`)**:
   - In `store.ts` (lines 46–47, 79–87):
     ```typescript
     investigatorTurns: import("./types").Turn[];
     setInvestigatorTurns: (turns: import("./types").Turn[] | ((prev: import("./types").Turn[]) => import("./types").Turn[])) => void;
     ...
     persist(
       (set, get) => ({
         ...
         investigatorTurns: [],
         setInvestigatorTurns: (turns) => set((state) => ({ investigatorTurns: typeof turns === 'function' ? turns(state.investigatorTurns) : turns })),
       }),
       {
         name: "cortex.sheet",
         partialize: (s) => ({ presentation: s.presentation, hiddenTypes: s.hiddenTypes, hiddenRelations: s.hiddenRelations, minPriority: s.minPriority, user: s.user, investigatorDetailLevel: s.investigatorDetailLevel }),
       },
     )
     ```
   - Observed Result: `investigatorTurns` is deliberately excluded from `partialize`. On page reload (`F5`) or navigation away from and back to the Investigator page, `investigatorTurns` re-initializes to `[]`. Furthermore, no `investigatorSessionId` field exists in `SheetState`.

3. **Client API Methods Omit Session Identifiers (`frontend-next/src/lib/api.ts` & `frontend-next/src/lib/agent.ts`)**:
   - In `frontend-next/src/lib/api.ts` (line 112):
     ```typescript
     ask: (question: string) => request<AssistantAnswer>("/api/assistant/ask", { method: "POST", body: JSON.stringify({ question }) }),
     ```
   - In `frontend-next/src/lib/agent.ts` (lines 83–96):
     ```typescript
     export async function streamAgent(
       question: string,
       history: { question: string; answer: string }[],
       onEvent: (e: AgentEvent) => void,
       signal?: AbortSignal,
     ): Promise<void> {
       ...
       const res = await fetch(`${API_BASE}/api/agent/stream`, {
         method: "POST", headers, signal,
         body: JSON.stringify({ question, history: history.slice(-6) }),
       });
     ```
   - Observed Result: Neither `api.ask` nor `streamAgent` accepts or passes a `session_id`. No API methods exist for querying `/api/assistant/sessions` or `/api/assistant/sessions/{id}`.

4. **Investigator Header UI Controls (`frontend-next/src/app/(sheet)/investigator/page.tsx`)**:
   - In `page.tsx` lines 282–313:
     `Header` renders the title `Investigator`, the detail level dropdown (`Detailed Analysis` / `Basic Summary`), and provider info.
   - Observed Result: There is no "+ New Chat" or "+ New Session" button to start a fresh investigation session or clear the current conversation history.

5. **Existing Backend Acceptance Tests (`backend/tests/`)**:
   - `backend/tests/test_m5_investigator_chat.py` (lines 49–132, 165–197) and `test_m4_ledger.py` (lines 31–67) establish the repository's standard testing pattern:
     - SQLite database fixture with `Base.metadata.create_all(engine)`.
     - Dependency override: `app.dependency_overrides[get_session] = override_get_session`.
     - Test client: `c = TestClient(app, raise_server_exceptions=True)`.
     - Graph and analysis cache invalidation: `graph_cache.invalidate()` and `analysis_service.invalidate()`.
     - User authentication via `create_token(user)`.
   - No `test_investigator.py` file currently exists in `backend/tests/`.

---

## 2. Logic Chain

1. **Session Identification & State Persistence**:
   - From Observation 1 and 2, conversation loss on page reload occurs because neither `investigatorSessionId` nor `investigatorTurns` is persisted.
   - Storing entire turn histories (including heavy visualizations, node highlights, and tool calls) directly inside Zustand `localStorage` risks exceeding browser quota limits (5–10MB).
   - In contrast, storing only `investigatorSessionId: string | null` in Zustand `partialize` (and syncing it to the URL query string `?session=...` via `nuqs`) is lightweight, shareable, and resilient to tab refreshes.
   - When the user refreshes, `investigatorSessionId` is immediately available from either the URL (`?session=...`) or `localStorage`.

2. **Session Hydration via API on Mount**:
   - From Observation 2 and 3, to display multi-turn conversations after a refresh, `page.tsx` must trigger a fetch to `GET /api/assistant/sessions/{session_id}` in a `useEffect`.
   - When the API response returns `messages`, each turn is mapped to a `Turn` object with `running: false`.
   - Tool calls (`calls`), visuals (`visuals`), highlights (`highlights`), and citations (`citations`) must be defaulted to empty arrays (`[]`) if omitted in stored messages, ensuring robust backwards-compatibility.

3. **Session Lifecycle & "New Chat" Flow**:
   - From Observation 4, an investigator needs a clean way to start a new case or topic.
   - Adding a "+ New Chat" button in the `Header` that invokes `abortRef.current?.abort()`, resets `setTurns([])`, sets `setSessionId(null)`, clears the URL query parameter `?session=`, and deletes `cortex.investigator.session_id` from `localStorage` gives users an intuitive and deterministic reset mechanism.

4. **Multi-Turn Context & Pronoun Retention in Acceptance Tests**:
   - From Observation 3 and sibling reports (`explorer_chat_1`, `explorer_chat_2`), sequential calls to `/assistant/ask` sharing the same `session_id` must maintain context.
   - In Turn 1: *"Who is the mastermind?"*, the system ranks key players and identifies *"Prabhakar Kumar"*.
   - In Turn 2: *"What did they do?"*, the pronoun *"they"* references the entity from Turn 1 (*"Prabhakar Kumar"*).
   - An automated acceptance test must execute these two sequential calls using `TestClient(app)`, assert that Turn 2's answer references *"Prabhakar"*, verify the `ChatSession` row in SQLite contains both turns, and verify `GET /api/assistant/sessions/{session_id}` returns the complete conversation.

---

## 3. Caveats

1. **Backend Endpoint Dependency**:
   - The frontend session hydration and the automated test rely on the backend changes designed by `explorer_chat_1` (`ChatSession` model in `backend/app/db.py`) and `explorer_chat_2` (`/assistant/ask` accepting `session_id`, history injection, and `/assistant/sessions` routes).
2. **Streaming vs Non-Streaming Session Persistence**:
   - The frontend currently streams via `streamAgent` (`/api/agent/stream`), while acceptance tests evaluate `POST /assistant/ask`. Both endpoints must support `session_id` and persist to `ChatSession`.
3. **LLM Provider Availability in CI/CD**:
   - Tests run in environments without live API keys (`CNA_GEMINI_API_KEY`). The acceptance test is designed to verify context retention using the deterministic fallback (`_dossier()` / `_key_players()`), ensuring 100% deterministic test execution without depending on external network calls.

---

## 4. Conclusion

1. **Frontend Updates (R3)**:
   - `frontend-next/src/lib/store.ts`: Add `investigatorSessionId: string | null` and setter; include in `partialize`.
   - `frontend-next/src/lib/api.ts`: Augment `ask(question, session_id?)` and add `chatSessions()`, `chatSession(id)`, `deleteChatSession(id)`.
   - `frontend-next/src/lib/agent.ts`: Augment `streamAgent` with optional `session_id?: string | null` and update `AgentEvent.done` to include `session_id?: string`.
   - `frontend-next/src/app/(sheet)/investigator/page.tsx`:
     - Bind `?session=` via `useQueryState("session", parseAsString)`.
     - Hydrate turns from `api.chatSession(activeSessionId)` on mount / session switch.
     - Add "+ New Chat" button in `Header` with full state and URL cleanup.
     - Pass active `session_id` into `streamAgent()`.
2. **Acceptance Test Suite (`backend/tests/test_investigator.py`)**:
   - Provide a 6-test automated acceptance suite in `backend/tests/test_investigator.py`:
     - `test_investigator_multi_turn_context_retention`: Two sequential calls with same `session_id`, verifying Turn 2 resolves *"they"* to *"Prabhakar"*.
     - `test_investigator_session_database_persistence`: Direct SQLite inspection of `ChatSession` row and its messages.
     - `test_investigator_session_retrieval_api`: `GET /api/assistant/sessions/{session_id}` returns persisted conversation.
     - `test_investigator_unprefixed_endpoint_alias`: `POST /assistant/ask` works without `/api`.
     - `test_investigator_auto_session_id_when_omitted`: Auto-assigns session UUID when omitted.
     - `test_investigator_sessions_list_and_deletion`: Verifies `GET /assistant/sessions` and `DELETE /assistant/sessions/{id}`.
     - `test_investigator_session_isolation`: Verifies independent session IDs do not leak context.

---

## 5. Verification Method

1. **Verify Automated Acceptance Test Suite**:
   Once the backend and test file are placed by the implementer, run the pytest command:
   ```powershell
   backend/venv/Scripts/python.exe -m pytest backend/tests/test_investigator.py -v
   ```
   **Expected Result**: All 6 tests pass with 0 failures.

2. **Verify Frontend Build & Type Check**:
   In `frontend-next/`:
   ```powershell
   cd "c:\Users\NIRJHAR BARMA\Desktop\batcave\frontend-next"
   npm run build
   ```
   **Expected Result**: TypeScript compiler and Next.js build pass with 0 errors.

3. **Verify Interactive Browser Multi-Turn & Reload**:
   - Navigate to `http://localhost:3000/investigator`.
   - Ask: *"Who is the mastermind?"* -> The URL updates to `http://localhost:3000/investigator?session=<uuid>`. Turn 1 displays answer identifying Prabhakar Kumar.
   - Ask: *"What did they do?"* -> Turn 2 displays answer detailing Prabhakar Kumar's actions, burner calls, and mule transfers.
   - Press `F5` (Refresh) -> The page loads `?session=<uuid>` from URL, triggers `api.chatSession`, and re-renders both Turn 1 and Turn 2.
   - Click `+ New Chat` -> The conversation clears, URL updates to `http://localhost:3000/investigator`, and fresh prompt is ready.

4. **Invalidation Conditions**:
   - If Turn 2 returns *"I couldn't match that to an entity on this sheet. Try: “Who is Prabhakar Kumar?”"*, then history context injection in `Investigator.answer()` has failed.
   - If `F5` clears the chat despite having `?session=...` in the URL, verify `useEffect` hydration in `page.tsx` and check whether `GET /api/assistant/sessions/{id}` returns 200.
