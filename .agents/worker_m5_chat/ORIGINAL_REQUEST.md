## 2026-09-17T20:54:01Z
You are worker_m5_chat, a specialized implementation worker.

Working directory: `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m5_chat`
Project root: `c:\Users\NIRJHAR BARMA\Desktop\batcave`
Python environment: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\python.exe`
Pytest: `c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your assigned task: Milestone M5 — Investigator AI Chat & Web Search (R2)
"Replace canned answers with a functional chat using a real LLM API (e.g. Gemini or OpenAI). Check environment variables/configuration. The chat must ask for case-specific details to answer accurately, fetch data from the database, and provide a functional option to search the internet (articles, news, etc.).
Acceptance: Queries for case facts retrieve actual database content using real LLM; web search fallback/option successfully retrieves live data from internet."

Requirements & Steps:
1. Remove Hardcoded Canned Interception:
   - In `backend/app/ai/agent.py`:
     Locate and remove lines 184-190:
     ```python
     if os.getenv("CNA_DEFAULT_CORPUS", "none").lower() == "none" and self.ctx.db.query(Case).count() > 0:
         # We are running with the demo case data, so intercept with the hardcoded fallback
         from .demo_fallback import match
         if match(question):
             yield from fallback_stream(question)
             return
     ```
     All questions MUST execute through the dynamic tool-calling agent loop!
   - In `SYSTEM` prompt in `agent.py`:
     Update instructions:
     "If the investigator's question is too broad or lacks specific entity or case details, ask for the specific entity name, account number, phone number, or transaction date to provide an accurate investigation. Always retrieve facts from the corpus tools first. If web context is needed or requested, use web_search."

2. Database Tool Execution:
   - Ensure tools in `backend/app/ai/tools.py` (`search_entities`, `entity_profile`, `find_path`, `money_flow`, `read_document`, etc.) execute real queries against the database session and graph.
   - When answering questions about entities (e.g. "Tell me about Prabhakar Kumar" or "Follow money from A002"), the LLM calls `search_entities` / `entity_profile` / `money_flow` to retrieve real data from `Entity`, `Relationship`, and `TimelineEvent` records.

3. Functional Web Search Option:
   - Ensure `_web_search` in `backend/app/ai/tools.py` and `WebConnector` in `backend/app/sources/web.py` are fully functional (using DuckDuckGo / web search).
   - In `frontend-next/src/app/(sheet)/investigator/page.tsx`:
     Add a clear UI toggle/switch/button for "Search Open Web" (e.g., a globe icon button or toggle next to the input area). When active, it informs the agent to search the open web for the query (or appends web search instruction).
     Ensure open-web search citations with live links are rendered in the response footer.

4. LLM API Configuration & Fallbacks:
   - Check `backend/.env` for configured keys (`CNA_GEMINI_API_KEY`, `CNA_NVIDIA_API_KEY`, `CNA_OPENROUTER_API_KEY`, etc.).
   - Ensure `stream_with_fallback` in `backend/app/ai/providers.py` handles provider responses robustly, parses tool calls correctly, and handles any transient API rate limits or network issues cleanly without crashing.

5. Verification:
   - Write comprehensive automated tests in `backend/tests/test_m5_investigator_chat.py`:
     - Test that canned demo fallback no longer intercepts questions.
     - Test that the agent loop calls database retrieval tools (`search_entities`, `entity_profile`) and receives actual database rows.
     - Test that web_search tool executes and retrieves results.
     - Test that clarification is prompted for ambiguous/underspecified questions.
   - Run tests:
     `& "c:\Users\NIRJHAR BARMA\Desktop\batcave\backend\venv\Scripts\pytest.exe" backend/tests/test_m5_investigator_chat.py -v`
   - Ensure all tests pass 100%.

6. Handoff:
   - Write `handoff.md` and `progress.md` in `c:\Users\NIRJHAR BARMA\Desktop\batcave\.agents\worker_m5_chat\`.
   - Send completion message to orchestrator.
