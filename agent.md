# Eco Value Simulator — Agent Architecture Specification (`evs.agent`)

## 1. Architectural Philosophy & Guiding Rules

> **Core Axiom:** *The LLM talks. The code calculates. The human decides.*

1. **Strict Role Boundary:**
   - The **Agent** gathers context, explains logic, checks data consistency, and proposes inputs.
   - The **Engine** ([`app.engine`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/engine)) calculates mathematical formulas with verified double precision.
   - The **Human** validates and confirms any input modifications.
2. **Server-Side Numeric Grounding (Zero Hallucinations):**
   - The LLM is mathematically forbidden from performing arithmetic.
   - Every number sent to the user must be backed by an engine tool fact and validated by a server-side checker before the response is streamed.
3. **Dual-Path Execution & Demo Resilience:**
   - **Path A (LLM Autonomous Path):** Model orchestrates tools, asks clarifying questions, and explains results.
   - **Path B (Scripted Fallback Path):** Completely independent of external APIs, LangGraph, or internet connectivity. If OpenRouter is slow, key is absent, or budget cap is reached, the hero demo runs deterministically with identical SSE events and golden numbers.
4. **State Machine & Append-Only History:**
   - Simulations and conversation messages are persistent and immutable.
   - Human pauses (`ask_user`, `stage_change`) suspend execution cleanly; user clicks resume the turn with full auditability.

---

## 2. Directory Structure (`backend/app/agent/`)

```text
backend/app/agent/
├── __init__.py          # Public exports (AgentService, get_agent_service)
├── types.py             # Pydantic schemas: AgentState, ToolFact, AgentEvent, StagedChange
├── tools.py             # Typed tool wrappers around app.engine and app.store
├── router.py            # Turn gatekeeper (checks LLM health, key presence, budget cap)
├── checker.py           # Server-side numeric validator and safety ladder
├── fallback.py          # Scripted demo runner (regex router, zero LLM dependency)
├── loop.py              # Async agent execution loop (router → llm ⇄ tools → checker)
└── service.py           # FastAPI integration, SSE streaming, turn persistence

backend/tests/agent/
├── test_tools.py        # Unit tests for tool schemas, fact extraction, and validation
├── test_checker.py      # Tests for numeric grounding, unit enforcement, and retry ladder
├── test_fallback.py     # Deterministic verification of the scripted hero flow
├── test_loop.py         # End-to-end turn loop execution with recorded/mocked LLM responses
└── test_agent_api.py    # FastAPI endpoints, SSE streaming format, and staged changes
```

---

## 3. Autonomy Tiers & Human-in-the-Loop

| Tier | Actions Permitted | User Confirmation Required |
|---|---|---|
| **Tier 1 · Automatic** | Read workspace/simulation status, run engine on current inputs, evaluate flags, run sensitivity sweep, explain formulas, compare runs, draft memo. | None (runs autonomously). |
| **Tier 2 · Propose $\to$ Confirm** | Any input change (what-ifs, resolving conflicting sources, altering value share or marketing %). | **Mandatory Staged Change Card:** Emits `change` event; execution pauses until user clicks **Apply** or **Dismiss**. |
| **Tier 3 · Forbidden** | Computing prices/margins in LLM text, editing database records directly without user action, hiding open warning flags. | **Strictly Blocked by Code.** |

---

## 4. Node Topology & Turn Lifecycle

```
[ User Message / Answer Chip / Apply Click ]
                    │
                    ▼
          ┌───────────────────┐
          │   agent/router    │ ── (No Key / LLM Error / Cap Reached) ──► ┌─────────────────────┐
          └─────────┬─────────┘                                           │   agent/fallback    │
                    │ Mode = "llm"                                        │  (Scripted Planner) │
                    ▼                                                     └──────────┬──────────┘
          ┌───────────────────┐                                                      │
    ┌───► │      LLM Call     │                                                      │
    │     │ (OpenRouter/Tool) │                                                      │
    │     └─────────┬─────────┘                                                      │
    │               │                                                                │
    │               ├── Tool Call ──► ┌───────────────────┐                          │
    │               │                 │    agent/tools    │                          │
    │               │                 └─────────┬─────────┘                          │
    │               │                           │ (Fact Injection)                   │
    │               │                           └────────────────────────────────────┤
    │               │                                                                │
    │               ├── ask_user / stage_change ──► [ Interrupt / Pause Turn ] ──────┤
    │               │                                                                │
    │               └── Final Text Response                                          │
    │                           │                                                    │
    │                           ▼                                                    │
    │                 ┌───────────────────┐                                          │
    │                 │   agent/checker   │                                          │
    │                 │ (Numeric Guard)   │                                          │
    │                 └─────────┬─────────┘                                          │
    │                           │                                                    │
    │          Pass / Validated ├── Fail (Retries < 2) ──► (Loop back with errors)   │
    │                           └── Fail (Retries ≥ 2) ──► [ Deterministic Template ]│
    │                                                               │                │
    ▼                                                               ▼                ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                 Server-Sent Events (SSE) Stream to Browser Frontend                   │
│         (`step` → `flag` → `question` → `tool` → `result` → `change` → `text`)        │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Tool Catalog (`backend/app/agent/tools.py`)

Tools are plain Python functions with typed Pydantic models. Every tool returns:
1. `data`: Structured payload for frontend components.
2. `facts`: A list of verified numeric facts (`ToolFact: {key, value, unit, label}`). These form the **only permitted numbers** the LLM is allowed to write.

```python
class ToolFact(BaseModel):
    key: str           # e.g., "anchor_price", "cgm_phos"
    value: float       # e.g., 313.91
    unit: str          # e.g., "USD/t"
    label: str         # e.g., "Phosfusion 65-35 Reference-Minus Anchor"
```

### Core Tool Definitions:

1. **`read_inputs(simulation_id?)`**
   - **Type:** Read
   - **Action:** Loads sources, active snapshot raw material costs, and current parameters with provenance.
   - **Side Effect:** Emits `step` and `tool` events.

2. **`check_inputs(simulation_id, input?)`**
   - **Type:** Read
   - **Action:** Runs `app.engine.flags.compute_engine_flags()` and data freshness checks (`P1, S1, D1, D2, W1, M1, A1`).
   - **Facts Produced:** Flag counts, date gaps.
   - **Side Effect:** Emits `flag` events.

3. **`run_engine(simulation_id, product_ids, reference_id, overrides)`** *(alias: `run_pricing`)*
   - **Type:** Compute
   - **Action:** Resolves inputs through `store.py` and executes `app.engine.core.evaluate()`.
   - **Facts Produced:** `unit_cost`, `cost_plus`, `ref_cost`, `ref_price`, `ref_minus`, `value_price`, `cgm`, `cgm_ref`, `cgm_p2o5`, `cgm_s`, `added_value`.
   - **Side Effect:** Persists immutable run $vN$ when user confirms; emits `step`, `tool` (`name: run_engine`), and `result` events.

4. **`compare_runs(run_id_a, run_id_b)`**
   - **Type:** Read
   - **Action:** Computes `diff_inputs()` and output deltas between two versions.
   - **Facts Produced:** Deltas in price, margin, and cost.

5. **`snapshot_view(simulation_id, snapshot_id, product_ids?)`**
   - **Type:** Read
   - **Action:** Derived output calculation under another historical snapshot (e.g. `2023`, `2024`, `period`) without persisting.
   - **Side Effect:** Emits preview facts and `tool` event.

6. **`draft_memo(simulation_id, run_id?)`**
   - **Type:** Read
   - **Action:** Compiles structured audit memo blocks from engine outputs and audit notes ($X1, X2$).

7. **`stage_change(simulation_id, patch, label, reason)`**
   - **Type:** Interrupt (Human-in-the-loop)
   - **Action:** Evaluates proposed change; pauses turn execution.
   - **Side Effect:** Emits `change` event with before/after comparison.

8. **`ask_user(question, options)`**
   - **Type:** Interrupt (Human-in-the-loop)
   - **Action:** Pauses turn execution; renders interactive option chips in the thread.
   - **Side Effect:** Emits `question` event.

9. **`run_sulphur_sensitivity(product_id, reference_id, from_price, to_price, step)`**
   - **Type:** Compute
   - **Action:** Calls `app.engine.sensitivity.run_sulphur_sensitivity()`.
   - **Facts Produced:** Zero-margin break-evens ($P_S^* = 918.86, 870.41$), parity crossover break-even ($P_S^{\text{cross}} = 848.46$).
   - **Side Effect:** Emits sensitivity curve data and break-evens.

10. **`explain_flags(simulation_id, flag_codes?)`**
    - **Type:** Read (Data Checker specialist)
    - **Action:** Plain-language explanation of open warnings and audit flags.

11. **`explain_run(simulation_id, question?)`**
    - **Type:** Read (Explainer specialist)
    - **Action:** Plain-language explanation of pricing methods and CGM margins.

---

## 6. Server-Side Numeric Checker (`backend/app/agent/checker.py`)

The checker is a pure-code validator that intercepts the LLM's text output before it is emitted over SSE:

### Verification Rules:
1. **Fact Grounding:** Extracts all numbers from the text using regex (excluding years 2020–2040, product grades like `65-35`, and version numbers). Every number must match an allowed `ToolFact` within $\pm 0.01$.
2. **Unit Attachment:** Every currency figure must explicitly state `USD/t` or `USD/yr`.
3. **No Hidden Warnings:** If the active engine output contains warning `P1` (anchor below floor), the text must reference this status.
4. **Scope Guard:** Rejects out-of-domain requests with a standardized capability reminder.
5. **Prompt Injection Guard:** Uploaded document texts and sheet names are treated strictly as data parameters, never instructions.

### Failure Ladder:
* **Attempt 1 & 2:** If validation fails, loop back to the LLM with precise error feedback:
  ```json
  {"status": "rejected", "error": "Number 315.00 has no tool backing. Expected 313.91 USD/t."}
  ```
* **Attempt 3 (Exceeded Retries):** Replace the text with a deterministic template rendered directly from the `ProductResult` facts.

---

## 7. HTTP & Server-Sent Events (SSE) Protocol

### 7.1 Endpoints (`app/routers/agent.py`)

* **`POST /api/simulations/{id}/messages`**: Streams SSE events for the user turn (`mode="auto" | "llm" | "script"`).
* **`POST /api/changes/{id}/apply`**: Applies a staged change card (`patch`) to create version $vN+1$ via human confirmation.
* **`POST /api/changes/{id}/dismiss`**: Dismisses a proposed change card without altering inputs.
* **`GET /api/agent/status`**: Returns current agent health, active routing mode (`"llm"` vs `"script"`), and budget status.

### 7.2 Event Schema

| Event Type | Payload Model | UI Component Rendered |
|---|---|---|
| `step` | `{ id, label, status }` | `Steps` / `TextShimmer` progress indicator |
| `flag` | `{ id, code, severity, title, action }` | `SystemMessage` with action chip |
| `question` | `{ id, text, options: [{ id, label }] }` | Clickable answer chips (e.g. Netback vs FOB) |
| `tool` | `{ id, name, label, latencyMs }` | Collapsible `Tool` execution card |
| `result` | `{ id, run: RunSummary }` | Mini Price Ladder, KPI cards |
| `change` | `{ id, patch, before, after, reason }` | `ChangeCard` with **Apply & Re-run** button |
| `text` | `{ id, content }` | Streamed markdown explanation with provenance chips |
| `error` | `{ id, message, recoverable }` | Error alert with retry button |
| `done` | `{ mode: "llm" | "script", usage }` | Stream completion indicator |

---

## 8. Revised Hero Demo Flow (Doc 09 & Doc 10 Aligned)

The scripted fallback and LLM prompts implement the **revised 3-minute hero flow**:

1. **User Prompt:** `"Price Phosfusion 65-35 against TSP"`
2. **Steps Streamed:**
   - *Reading CRU prices (TSP CFR Brazil, week of 24 Sep)...*
   - *Reading CRU freight (Morocco → Brazil, 45–50k mt)...*
   - *Evaluating raw material costs (Phosfusion 65-35: 310.90 USD/t, TSP: 655.18 USD/t)...*
3. **Question Event (Netback vs FOB Confirmation):**
   - Question: *"TSP CFR Brazil is 665 USD/t and freight is 23 USD/t. Calculate FOB-equivalent netback (642 USD/t) or use FOB Morocco Spot (699 USD/t)?"*
   - Option Chips: `[Use Netback (642 USD/t) · (Recommended)]`, `[Use FOB Morocco (699 USD/t)]`.
4. **User Selects Netback (642 USD/t):**
   - Executes `run_engine` (alias: `run_pricing`).
   - Emits `result` card: Anchor = **313.91 USD/t** (below floor 373.08), Phosfusion CGM = **3.02 USD/t**, TSP CGM = **-15.18 USD/t**.
   - Emits flags: `P1` (anchor below floor), `W1` (yield gain unit open item).
5. **What-If Turn:** `"What if value share is 50%?"`
   - Agent stages change card: `valueShare: 33.3% → 50.0%` (Value price: 740.99 $\to$ 791.48 USD/t).
   - User clicks **Apply** $\to$ creates $v2$ $\to$ side-by-side comparison.
6. **Sensitivity Turn:** `"Show sulphur break-even vs TSP"`
   - Calls `run_sulphur_sensitivity`.
   - Explains zero-margin break-evens: Phosfusion = **918.86 USD/t**, TSP = **870.41 USD/t**; Crossover = **848.46 USD/t**.

---

## 9. Budget & OpenRouter Configuration

* **Environment Keys:**
  - Key variable: `openrouter_api_key` (or `OPENROUTER_API_KEY`).
  - Supports automatic discovery from local `.env` files (ignored in git via `.gitignore`).
* **Model Hierarchy:**
  1. Primary: `anthropic/claude-3.5-sonnet` (configurable via `OPENROUTER_MODEL`).
  2. Fallback / Scripted: `agent/fallback.py` ($0 cost, 100% deterministic).
* **Prompt Caching:**
  - System prompt, tool schemas, and knowledge definitions set with 1-hour cache TTL.
* **Safety Budget Ceiling:**
  - Real-time token usage tracked in memory.
  - Hard cutoff at **$40.00**: auto-switches router to `mode="script"` to guarantee that the demo never fails due to depleted credits.

---

## 10. Implementation & Validation Status (Completed)

All components of the agent specification are fully implemented and verified:

1. **Schemas & Contracts:** [`app/agent/types.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/types.py)
2. **Tools Catalog:** [`app/agent/tools.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/tools.py) (all 11 tools + OpenAI schemas)
3. **Numeric Grounding Checker:** [`app/agent/checker.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/checker.py)
4. **Scripted Hero Fallback:** [`app/agent/fallback.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/fallback.py)
5. **Router & Loop:** [`app/agent/router.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/router.py) and [`app/agent/loop.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/agent/loop.py)
6. **API Endpoints:** [`app/routers/agent.py`](file:///home/ajamoun/Desktop/eco%20value%20simulator/backend/app/routers/agent.py) mounted in `main.py`
7. **Test Suites (`backend/tests/agent/`):**
   - `test_tools.py`: Tool facts, outputs, and event schemas
   - `test_checker.py`: Fact extraction, unit enforcement, regex grounding
   - `test_fallback.py`: Hero flow, what-if, sensitivity offline reproduction
   - `test_loop.py`: Async turn loop, OpenRouter mocking, tool dispatching
   - `test_agent_api.py`: SSE streaming, change application and dismissal

**Test Execution:**
```bash
uv run --with-requirements requirements.txt pytest tests/agent/
# All tests passing with 0 warnings
```

