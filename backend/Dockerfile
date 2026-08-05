# backend/Dockerfile
#
# Builds the FastAPI backend. Includes simulator/ and data/ (copied from
# the repo root via the build context set in docker-compose.yml) so the
# app's /simulate/* routes can import simulator/*.py directly, and so
# seed.py has CSVs to load on startup.

FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2 (Postgres driver) -- psycopg2-binary avoids
# needing these at runtime, but build tools are still needed for some
# platforms (notably ARM). Kept minimal on purpose.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY backend/app ./app

# Simulator code -- needed at runtime because app/routers/simulator.py
# imports directly from simulator/*.py (see that file's sys.path setup).
COPY simulator ./simulator

# Seed data -- loaded by app/seed.py on startup. See docker-compose.yml
# for the volume mount alternative; this COPY is the fallback baked into
# the image itself, so seeding works even without the volume mount.
COPY data ./data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]