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
