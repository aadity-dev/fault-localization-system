# frontend/Dockerfile
#
# Builds the Streamlit operator console. Build context is the repo root
# (see docker-compose.yml), matching the backend Dockerfile's convention.

FROM python:3.12-slim

WORKDIR /app

COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/app.py .

EXPOSE 8501

# --server.address=0.0.0.0 is required -- Streamlit defaults to
# localhost-only binding, which is unreachable from outside the
# container. This is a common deployment gotcha, documented in
# DEPLOYMENT.md's troubleshooting section.
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]