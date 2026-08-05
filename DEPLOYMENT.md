# Deployment

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Docker | ≥ 24.0 | `docker --version` |
| Docker Compose | ≥ 2.20 (bundled with Docker Desktop) | `docker compose version` |
| Git | ≥ 2.30 | `git --version` |

No other runtime, language, or package manager is needed — everything
runs inside containers.

## Quick start (local)

```bash
git clone https://github.com/aadity-dev/fault-localization-system.git
cd fault-localization-system
docker compose up --build
```

Wait for the backend to print `Application startup complete` (typically
~15 seconds). Then open:

- **Operator console**: http://localhost:8501
- **API docs (Swagger)**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/health

The system seeds itself on first startup with a synthetic ~700-pole grid
— no manual data loading required.

## How to verify it worked

1. Open http://localhost:8501 — you should see the operator console with
   a "Simulator" panel in the sidebar.
2. Click "Inject span fault" — within ~30-40 seconds, a new ticket
   should appear in the ticket list.
3. Open http://localhost:8000/docs — you should see the Swagger UI with
   all API endpoints listed.

## Environment variables

All environment variables and their defaults. Copy `.env.example` to
`.env` to override any of these:

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `POSTGRES_DB` | Yes | `gridfault` | PostgreSQL database name |
| `POSTGRES_USER` | Yes | `admin` | PostgreSQL username |
| `POSTGRES_PASSWORD` | Yes | `admin` | PostgreSQL password |
| `DATABASE_URL` | Yes | `postgresql://admin:admin@db:5432/gridfault` | SQLAlchemy connection string (set by docker-compose) |
| `REDIS_URL` | Yes | `redis://redis:6379` | Redis connection string (set by docker-compose) |
| `GEMINI_API_KEY` | No | _(unset)_ | Google Gemini API key for AI ticket summaries. Without it, the system falls back to deterministic template summaries — no feature breaks. |
| `API_BASE` | No | `http://backend:8000` | Backend URL for the frontend container (set by docker-compose) |

### Enabling the AI feature

```bash
export GEMINI_API_KEY=your-key-here
docker compose up --build
```

Without the key, every ticket still gets a readable summary — it's just
a deterministic template instead of an LLM-generated one.

## Running tests

```bash
cd backend
pip install -r requirements.txt   # one-time
DATABASE_URL="sqlite:///test.db" python -m pytest tests/ -v
```

Expected: 32 tests passing, covering span/DT/feeder faults,
missing-topology fallback, dead-sensor suppression, scheduled-outage
handling, ticket lifecycle enforcement, worker dedup/debounce, and the
AI feature's fallback guarantee.

## Cloud deployment (Render / Railway / Fly.io)

*(Note: If deploying on Render's Free Tier, be aware that services spin down after 15 minutes of inactivity. The next request will experience a "cold start" delay of ~45-60 seconds. This is normal and expected for free-tier hosting. The `API_BASE` should also point to the external Render URL for the backend, not the internal Docker network hostname).*

1. Push the repo to a public GitHub URL.
2. Create a new project on your platform with Docker Compose support, or
   deploy each service individually:
   - **PostgreSQL**: use the platform's managed Postgres add-on.
   - **Redis**: use the platform's managed Redis add-on.
   - **Backend**: build from `backend/Dockerfile`, set `DATABASE_URL` and
     `REDIS_URL` from the managed add-ons.
   - **Frontend**: build from `frontend/Dockerfile`, set
     `API_BASE=https://your-backend-url`.
3. Set `GEMINI_API_KEY` as an environment variable if you want AI
   summaries (optional).
4. Verify: open the public URL in an incognito window — should see the
   operator console with no login required.

## How to reset to clean state

```bash
docker compose down -v    # removes containers AND volumes (database data)
docker compose up --build # rebuilds everything fresh, re-seeds the grid
```

The `-v` flag is critical — it removes the PostgreSQL volume, so the
database is recreated from scratch and the grid is re-seeded on startup.

## Troubleshooting

### `docker compose up` fails with "port already in use"

Another process is using port 5432, 6379, 8000, or 8501. Either stop
that process or change the port mapping in `docker-compose.yml`:

```yaml
ports: ["8001:8000"]  # maps container port 8000 to host port 8001
```

### Backend starts but frontend shows "Connection refused"

The frontend container can't reach the backend. Check that:
1. Both containers are on the same Docker network (they are by default
   with `docker compose`).
2. The `API_BASE` environment variable in the frontend service is set to
   `http://backend:8000` (not `localhost`).

### "No tickets appearing after injecting a fault"

This was the most common issue during development. Check:
1. **Redis is reachable**: `docker compose exec redis redis-cli ping`
   should return `PONG`.
2. **Worker is running**: look for `[worker]` log lines in
   `docker compose logs backend`. If absent, the worker thread may have
   crashed — check for `TimeoutError` in the logs (see AI-WORKFLOW.md
   for the full story on this bug).
3. **Wait 30+ seconds**: the debounce window is 30 seconds. A fault
   injected at t=0 won't produce a ticket until at least t=30.

### "Gemini API returns 403 / 429"

The AI summary will silently fall back to a template — no visible error
in the UI. Check `docker compose logs backend` for the actual API error.
Common causes: invalid API key, quota exceeded, or the key is
restricted to specific IPs.

### Database migration errors after schema changes

This project doesn't use Alembic — the schema is created from ORM
models on startup. If the schema changes:

```bash
docker compose down -v    # wipe the old schema
docker compose up --build # recreates tables from current models
```
