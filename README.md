# Eco Value Simulator · backend

FastAPI + PostgreSQL service that serves the data and calculations the frontend currently mocks in `src/data`, `src/engine` and `src/store`.

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
docker compose up -d db                            # just the database
DATABASE_URL=postgresql+psycopg://eco:eco@localhost:5434/eco .venv/bin/uvicorn app.main:app --reload
```

## Tests

```bash
.venv/bin/pytest                 # in-memory SQLite, no database needed
TEST_DATABASE_URL=postgresql+psycopg://eco:eco@localhost:5434/eco .venv/bin/pytest   # against PostgreSQL; wipes that database
```

## Layout

```
Dockerfile, docker-compose.yml
app/
  main.py        FastAPI app, CORS for the Vite dev server, routers under /api
  schemas.py     Pydantic models, field names identical to src/engine/types.ts
  db.py          SQLAlchemy engine and tables (products, snapshots, uploads, parameters, simulations, runs)
  store.py       Reads and writes: the only code that talks to the database
  data/seed.py   Demo data loaded into an empty database
  engine/        Pricing engine (period.py, run.py), a port of src/engine
  routers/       products, market, parameters, uploads, engine, simulations
tests/           Golden values from src/engine/engine.test.ts + endpoint tests
```

## Notes

- Tables are created on start, and an empty database is loaded with the demo data. `POST /api/reset` deletes everything and reloads it.
- There are no migrations yet: after changing a table in `db.py`, recreate the database (`docker compose down -v`).
- "Today" is fixed to 2 Oct 2026 (`TODAY` in `app/data/seed.py`), the date the seeded 2026 snapshot runs to.
- `POST /api/uploads/detect` reads the filename and size only; file contents are not parsed yet.
- No agent / chat endpoints yet.
