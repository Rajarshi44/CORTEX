# Hosted demo: one container serves the API and the console from the same origin, preloaded with
# the Operation CyberHawk 2.0 case from demo-case-data/. Used by render.yaml.

# ---- console: static export of the Next.js app
FROM node:22-slim AS console
WORKDIR /src/frontend-next
COPY frontend-next/package.json frontend-next/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend-next/ ./
# An empty API URL makes every request relative, i.e. to the API that serves these files.
ENV NEXT_OUTPUT=export NEXT_PUBLIC_API_URL= NEXT_TELEMETRY_DISABLED=1
RUN npx next build

# ---- API + demo sheet
FROM python:3.12-slim
# MALLOC_ARENA_MAX: glibc otherwise gives each thread its own arena, which on a 512 MB plan is the
# difference between fitting and being killed.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 MALLOC_ARENA_MAX=2
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock ./
RUN pip install uv \
 && uv export --frozen --no-dev --no-emit-project --no-hashes -o /tmp/requirements.txt \
 && uv pip install --system -r /tmp/requirements.txt \
 && pip uninstall -y uv

COPY backend/ ./
COPY demo-case-data/ /app/demo-case-data/
COPY --from=console /src/frontend-next/out /app/console

ENV CNA_DATABASE_URL=sqlite:////app/backend/data/demo.db \
    CNA_DEFAULT_CORPUS=none \
    CNA_STATIC_DIR=/app/console \
    CNA_ENVIRONMENT=demo

# Bake the embedding model and the seeded sheet into the image: a cold start then only opens a
# file, and every restart comes back to the same clean case.
RUN python download_model.py && python -m app.ingestion.load_demo_case

EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
