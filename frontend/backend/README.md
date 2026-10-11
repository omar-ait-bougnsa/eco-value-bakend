# Eco Value Simulator · backend

FastAPI + PostgreSQL service that serves the data and calculations the frontend currently mocks in `src/data`, `src/engine` and `src/store`.
It also holds the knowledge base the agent cites from: documents cut into passages and searched by meaning, with pgvector (see [Knowledge base](#knowledge-base)).

## Run with Docker

```bash
cd backend
docker compose up --build        # API + PostgreSQL
```

- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json
- PostgreSQL: `localhost:5434`, database / user / password `eco` (local development only)
- Database browser (Adminer): http://localhost:8081, log in with System `PostgreSQL`, Server `db`, Username / Password / Database `eco`

Change the host ports with `API_PORT` and `DB_PORT`, e.g. `API_PORT=8001 docker compose up`.
`docker compose down` stops the stack and keeps the data; `docker compose down -v` also deletes it.

## Run without Docker

```bash
uv venv && uv pip install -r requirements.txt     # or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
docker compose up -d db                            # just the database (it must have pgvector: the image in docker-compose.yml does)
DATABASE_URL=postgresql+psycopg://eco:eco@localhost:5434/eco .venv/bin/uvicorn app.main:app --reload
```

## Tests

```bash
.venv/bin/pytest                 # in-memory SQLite, no database needed
TEST_DATABASE_URL=postgresql+psycopg://eco:eco@localhost:5434/eco .venv/bin/pytest   # against PostgreSQL; wipes that database
```

SQLite has no vector type: there the embeddings are kept as JSON and ranked in Python. Run the suite against PostgreSQL to
exercise the pgvector column, its HNSW index and the `<=>` search. The tests never call an embedding API (`EMBEDDINGS=hash`).

## Knowledge base

Exact numbers stay in the relational tables and go through the engine. The knowledge base holds what explains them:
reports, trial papers, methodology. Specification: `RAG.md`.

```
file → parser.py (text, tables) → chunker.py (500–800 tokens, 100 overlap) → embeddings.py → documents / document_chunks (pgvector)
question → embeddings.py → cosine search → passages with their source → the agent cites them ([1], [2]…)
```

| Method | Endpoint | |
| :--- | :--- | :--- |
| `POST` | `/api/knowledge/search` | Passages closest in meaning to a question. `{query, docType?, limit?}` |
| `GET` | `/api/knowledge/documents` | Indexed documents with their page and chunk counts, and their status |
| `POST` | `/api/knowledge/documents` | Index a file (multipart `file`; optional `uploadId`, `docType`, `title`, `docDate`). `.pdf .xlsx .csv .docx .txt .md`, 20 MB |
| `POST` | `/api/knowledge/reindex` | Compute every embedding again with the current model |
| `DELETE` | `/api/knowledge/documents/{id}` | Remove a document and its embeddings |

- **What is indexed on first start:** the data files in `sample-uploads/` (each sheet as a Markdown table) and `engine.md` as the
  methodology. Drop the narrative documents the specification lists (market commentary, freight reports, trial papers,
  internal guidelines) in through `POST /api/knowledge/documents`: none of them is in this repository.
- **Embedding model** (`EMBEDDINGS`, default `auto`): `text-embedding-3-small` through OpenAI (`OPENAI_API_KEY`) or OpenRouter
  (the agent's key) when there is a key and `LLM_ENABLED` is not false; else `all-MiniLM-L6-v2` on this machine when the optional
  `fastembed` package is installed (it downloads the model once, about 90 MB); else word hashing, which needs nothing but
  matches on shared words rather than on meaning.
- **Changing the model:** vectors of two models cannot be compared, so each chunk records the model of its vector and a search
  reads only its own. A restart computes the missing ones; `POST /api/knowledge/reindex` does it without a restart.
- **The agent** searches with its `search_knowledge` tool and cites passages as `[K1]`. Before an answer is streamed, the checker
  verifies that every citation, document name, date, quotation and figure is in what was retrieved; the answer then goes out
  with one `citation` event per passage used. Without a model, a question about the documents is answered with the passages
  themselves.

## Layout

```
Dockerfile, docker-compose.yml
app/
  main.py        FastAPI app, CORS for the Vite dev server, routers under /api
  schemas.py     Pydantic models, field names identical to src/engine/types.ts
  db.py          SQLAlchemy engine and tables (products, snapshots, uploads, parameters, simulations, runs, documents, document_chunks)
  store.py       Reads and writes: the only code that talks to the database
  data/seed.py   Demo data loaded into an empty database
  engine/        Pricing engine (period.py, run.py), a port of src/engine
  rag/           Knowledge base: parser.py, chunker.py, embeddings.py, index.py (store and search)
  routers/       products, market, parameters, uploads, engine, simulations, agent, rag (knowledge)
tests/           Golden values from src/engine/engine.test.ts + endpoint tests
```

## Notes

- Tables are created on start, and an empty database is loaded with the demo data. `POST /api/reset` deletes everything and reloads it.
- There are no migrations yet: after changing a table in `db.py`, recreate the database (`docker compose down -v`).
- "Today" is fixed to 2 Oct 2026 (`TODAY` in `app/data/seed.py`), the date the seeded 2026 snapshot runs to.
- `POST /api/uploads/detect` reads the filename and size only; file contents are not parsed yet. `POST /api/uploads` takes no
  file either: to make a data file citable, send it to `POST /api/knowledge/documents` with the upload's id (the frontend does).
- Agent and chat streaming are implemented under `/api/agent` and `/api/simulations/{id}/messages` (see `agent.md`).

## Validation limits

The server is the authority on what an input may be. The rules are in `app/limits.py`; the API returns what it refuses as
`400 {"detail": "...", "errors": [{"field": "recipe.sulphur", "message": "must be between 0 and 3 t/t"}]}`.
The forms read the same limits from `GET /api/limits` and check a draft with `POST /api/products/validate` and
`POST /api/engine/validate`, so there is one set of rules, not two.

**The defaults below are working assumptions, not confirmed business rules.** Change them without touching the code:

```bash
EVS_LIMITS='{"recipeQtyMax": 2.5, "pcfMax": 5}'
```

| Limit | Default | Applies to |
|---|---|---|
| `productNameMin` / `productNameMax` | 3 / 80 characters | Product name: trimmed, with letters, not one character repeated, unique whatever the case |
| `recipeQtyMax` | 3 t/t | One ingredient of a recipe (the largest in the demo data is 2.18) |
| `recipeTotalMax` | 4 t/t | All ingredients of a recipe together (the largest in the demo data is 2.76). A recipe needs at least one quantity |
| `nutrientTotalMax` | 1 (100 %) | N + P2O5 + K2O + S; each is 0–100 % |
| `pcfMax` | 10 t CO₂/t | Carbon footprint, 0 or more |
| `appRateMax` | 5 t/ha | Application rates, above 0 |
| `yieldGainMaxTHa` / `yieldGainMaxPct` | 20 t/ha / 100 % | Yield gain, in its unit |
| `baselineYieldMax` | 100 t/ha | Baseline yield, required when the yield gain is in % |
| `priceMax` | 10 000 USD/t | Crop price, benchmark, carbon price, reference cost override, D&A |
| `marginMax` / `marketingMax` | 2 (200 %) / 1 (100 %) | Cost-plus margin, marketing cost |
| `addressableMax` | 1e9 t | Addressable market |
| `rampYearSpan` | 30 years | Ramp-up target year, from the current year |
| `uploadMaxBytes` | 20 MB | An uploaded file |

A yield gain is a quantity with a unit (`yieldGainUnit`: `t/ha` or `%`). In % it is a share of `baselineYield`, which is then required:
`t/ha = % / 100 × baselineYield`. Products stored before the unit existed have none: runs use their value as t/ha and carry
flag U1 until the unit is set on the product or confirmed for the run.

## Uploads

`POST /api/uploads` takes the file itself. The record (name, type, dates, SHA-256) is made from it; a file that is empty,
too large, not `.xlsx`, `.csv`, `.pdf`, `.docx`, `.txt` or `.md`, or not readable as what its extension says is refused.
A file with rows of prices, freight, trials or crop prices gets that type; anything else is `other`: a document, used in
no calculation. In the same step the file is put in the knowledge base (`documentId` in the response), so the assistant
can answer from it. It does not create a product: the product library is only changed through `/api/products`. The same bytes sent again return the
upload they already are (200, `duplicate: true`) instead of a second row.

## Reviewing stored records

Rules added later do not reach the rows already stored. Review them, then set aside the ones that fail:

```bash
python -m app.maintenance            # report only: nothing is changed
python -m app.maintenance --apply    # quarantine what the report lists
```

Nothing is deleted. A quarantined product stays in the list as "Needs review" and cannot be priced until it is saved in a
valid form, which restores it. A quarantined upload is read by nothing and is still served by
`GET /api/uploads?includeQuarantined=true`. Every quarantine, restore and refused duplicate is in `GET /api/audit`.
The columns this needs are added on start by `app/migrations.py` (additive, safe to run again).

## Agent

`GET /api/agent/status` says what answers the chat: `mode`, `provider`, `model`, `configured`, `enabled`, `fallbackReason`
(`disabled`, `no_api_key`, `recent_failure`, `budget_exhausted`) and a `label` for the UI, never the key. Without a model
the chat is a rule-based assistant: a fixed set of requests matched on keywords. With one, the model can only call the
declared tools, with arguments checked against their declared schema; it prices as a preview and the user confirms the save.
`LLM_TIMEOUT_SECONDS` (35) and `LLM_RETRIES` (1) bound each model call; calls and refused tool calls are logged by `evs.agent`.

## Agent jobs

Every turn of the agent (a chat message, a run of the Configure run form, an answer to its question) is a job with a stored state:

```
queued → running → completed | failed | cancelled | timed_out
```

- `POST /api/simulations/{id}/messages` starts the job and streams its events. The first and last event are `job`; its id is also in the `X-Job-Id` header.
- The job belongs to the server, not to that response: a closed tab does not stop it. `GET /api/jobs/{id}` gives its state, `GET /api/simulations/{id}` its latest job (`job`), `GET /api/simulations/{id}/jobs` its history, `POST /api/jobs/{id}/cancel` stops it.
- A job stores its transitions with their times, a `failureCode` (`invalid_input`, `request_refused`, `internal_error`, `timed_out`, `cancelled`, `lost`) and an `error` that is safe to show. The cause of an `internal_error` is in the server log under the job id, never in the response.
- Nothing stays `running`: a job is ended as `timed_out` after `AGENT_JOB_TIMEOUT_SECONDS` (120), and one the server lost in a restart is ended (`lost`) the first time it is read after that time.
- To retry, send `request` of the job again.

| Setting | Default | |
|---|---|---|
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | none, `anthropic/claude-sonnet-5.5` | The model. In `.env` at the repository root (or `backend/.env`), read by the server only |
| `LLM_ENABLED` | `true` | `false` forces the rule-based assistant |
| `LLM_TIMEOUT_SECONDS`, `LLM_RETRIES` | 35, 1 | One model call |
| `LLM_MAX_TURNS_PER_MINUTE` | 30 | Above it, turns go to the rule-based assistant |
| `AGENT_JOB_TIMEOUT_SECONDS` | 120 | One whole job |
| `LOG_LEVEL` | `INFO` | Loggers `evs.jobs` (transitions) and `evs.agent` (model calls, refused tool calls), each line with the job id |
