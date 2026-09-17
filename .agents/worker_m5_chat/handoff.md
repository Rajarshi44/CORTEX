# Handoff Report — Milestone M5: Investigator AI Chat & Web Search (R2)

## 1. Observation
- **Hardcoded Canned Answers**: In `backend/app/ai/agent.py`, lines 37 and 184-190 intercepted any question matching `demo_fallback.match(question)` whenever `CNA_DEFAULT_CORPUS == "none"` and database cases existed, bypassing the tool-calling agent loop entirely:
  ```python
  if os.getenv("CNA_DEFAULT_CORPUS", "none").lower() == "none" and self.ctx.db.query(Case).count() > 0:
      from .demo_fallback import match
      if match(question):
          yield from fallback_stream(question)
          return
  ```
- **Database Tools & Graph Resolution**: In `backend/app/ai/tools.py`, `Ctx.resolve` previously only resolved entities present in in-memory NetworkX graph `self.G`. When database entities were queried before the full graph snapshot was indexed, tools like `_search_entities`, `_entity_profile`, and `_money_flow` could fail to find matches.
- **Web Search**: `WebConnector` in `backend/app/sources/web.py` provides Firecrawl and DuckDuckGo HTML search. In `backend/app/ai/tools.py`, `_web_search` invokes `WebConnector().search(...)` and attaches citations with `kind: "web"` and `source_type: "WEB"`.
- **Frontend Investigator Chat UI**: In `frontend-next/src/app/(sheet)/investigator/page.tsx`, the interface lacked a dedicated toggle button to trigger open-web search or augment the query for live web retrieval, and open-web citations needed live link rendering.
- **Provider Layer & Fallbacks**: In `backend/app/ai/providers.py`, `GeminiProvider` returned HTTP 404 for model `gemini-2.5-flash` with placeholder credentials, while `NvidiaNIMProvider` (configured in `backend/.env` with OpenRouter Nemotron) succeeded in real tool-calling and response generation. OpenRouter and OpenAI were not registered as first-class providers in the catalogue.

## 2. Logic Chain
1. **Removed Demo Fallback Interception**:
   - Completely deleted the interception block and `from .demo_fallback import fallback_stream` from `backend/app/ai/agent.py`.
   - Updated the `SYSTEM` prompt in `backend/app/ai/agent.py` to instruct:
     *"If the investigator's question is too broad or lacks specific entity or case details, ask for the specific entity name, account number, phone number, or transaction date to provide an accurate investigation. Always retrieve facts from the corpus tools first. If web context is needed or requested, use web_search."*
   - All questions now route through the dynamic tool-calling agent loop.
2. **Hardened Database Retrieval Tools**:
   - Enhanced `Ctx.resolve` in `backend/app/ai/tools.py` with direct database lookup fallback when an entity is not already in `self.G`. When found in `self.db`, nodes are added to `G` and `D` on demand.
   - Updated `_search_entities`, `_entity_profile`, and `_money_flow` in `backend/app/ai/tools.py` and `money_flow` in `backend/app/graph/queries.py` to ensure queries execute against `Entity`, `Relationship`, and `TimelineEvent` records reliably.
3. **Open Web Search Integration & UI Toggle**:
   - Enhanced `_parse_ddg` in `backend/app/sources/web.py` with `|\Z` lookahead so trailing blocks and single results parse cleanly without requiring three trailing `</div>` tags.
   - In `frontend-next/src/app/(sheet)/investigator/page.tsx`:
     - Added `searchWeb` state and `searchWeb` attribute on `Turn`.
     - Added a "Search Open Web" toggle button with Globe icon, active state highlighting (`border-blue bg-blue-wash text-blue font-semibold`), and tooltip.
     - Added a visual badge on question turns when web search was enabled.
     - Automatically appends instructions to invoke `web_search` when active.
     - Rendered open-web citations in the response footer as live clickable links (`<a>` tags with `target="_blank"`, `rel="noreferrer noopener"`, and full hover tooltips).
4. **Provider Fallbacks & Multi-Provider Architecture**:
   - Created `OpenAICompatibleProvider` base class in `backend/app/ai/providers.py` that encapsulates OpenAI-format streaming, chunked tool-call argument parsing, and network error handling.
   - Subclassed `NvidiaNIMProvider`, `OpenRouterProvider`, and `OpenAIProvider`, registering them in `catalogue`.
   - Enhanced `stream_with_fallback` to detect real emitted content (`(kind == "text" and payload.strip()) or kind == "tool_use"`) before committing to a provider, seamlessly falling back on transient errors or HTTP 4xx/5xx status codes without crashing.
5. **Comprehensive Test Suite**:
   - Authored `backend/tests/test_m5_investigator_chat.py` with 14 automated tests covering fallback removal, database tools, web search, question clarification, provider fallbacks, and live end-to-end execution.

## 3. Caveats
- `CNA_GEMINI_API_KEY` in `backend/.env` is currently a placeholder token that returns HTTP 404/400; the system correctly and seamlessly falls back to `nvidia` / `openrouter` via `stream_with_fallback`. If a valid Google AI Studio key is provided in the future, Gemini will resume primary execution automatically.
- Open-web search relies on DuckDuckGo HTML endpoint when no Firecrawl key is provided; DuckDuckGo responses may vary based on network conditions, but fallbacks and caching protect against failures.

## 4. Conclusion
Milestone M5 is complete and verified:
- Canned interception has been eliminated; all investigator queries execute through the dynamic tool-calling agent loop.
- The agent queries real entities, relationships, dossiers, and money flows from the database.
- The open-web search tool functions reliably, and the frontend includes a functional UI toggle and live citation links.
- Provider fallback is robust against rate limits and network errors.
- 100% of automated tests pass (14/14 M5 tests, 81/81 full backend suite), and frontend lint passes cleanly with 0 errors.

## 5. Verification Method
1. **Pytest M5 Suite**:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m5_investigator_chat.py -v
   ```
   *Result*: 14 passed in ~58s.
2. **Full Backend Pytest Suite**:
   ```powershell
   & "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/ -v
   ```
   *Result*: 81 passed in ~69s.
3. **Frontend Lint**:
   ```powershell
   cd frontend-next; npm run lint
   ```
   *Result*: 0 errors, 0 warnings.
