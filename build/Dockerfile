# syntax=docker/dockerfile:1
# =====================================================================
# build/Dockerfile — ALL-IN-ONE image: every ship-ready cuga-app + the
# umbrella UI behind a single nginx port (8080). One image, one port —
# runs identically under local `docker compose` and as a single Code
# Engine microservice.
#
# Build context is the REPO ROOT (see build/docker-compose.yml). This file
# and its helpers live entirely under build/ — no existing files are modified.
#
#   /            → umbrella UI (static SPA)
#   /a/<app>/    → reverse-proxied to that app (path-prefixed; nginx injects a
#                  fetch() shim so the apps' absolute URLs work under the prefix)
#   /healthz     → 200 (Code Engine readiness)
#
# MCP-backed apps use the hosted Code Engine MCP servers (CUGA_TARGET=ce), so
# no MCP servers are bundled here.
# =====================================================================

# ---- Stage 1: build the umbrella UI in "single-container" URL mode ----------
FROM node:20-slim AS ui
WORKDIR /ui
COPY cuga-apps/ui/package*.json ./
RUN npm ci
COPY cuga-apps/ui/ ./
# Inject the 'single' path-routing mode into THIS COPY of deployment.ts
# (repo source untouched), then build with the matching build-time flag.
COPY build/patch-deployment.cjs /tmp/patch-deployment.cjs
RUN node /tmp/patch-deployment.cjs src/data/deployment.ts
RUN VITE_DEPLOYMENT_TARGET=single npm run build      # → /ui/dist

# ---- Stage 2: runtime — apps + nginx ---------------------------------------
FROM python:3.13-slim AS runtime

# build-essential for any C extensions; nginx-extras as the single front door
# (nginx-extras guarantees ngx_http_sub_module / sub_filter, which the per-app
# path-prefix rewriting relies on — the base `nginx` package may omit it).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential nginx-extras \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# App deps (cuga + sqlite-vec + feedparser + playwright + the LangChain stack).
# The ship-ready set does NOT include video_qa/deck_forge, so the heavy file
# (chromadb + sentence-transformers) is intentionally skipped — leaner image.
COPY cuga-apps/requirements.apps.txt ./
RUN pip install --no-cache-dir -r requirements.apps.txt

# Chromium for the one browser-driven ship-ready app (meetup_finder).
RUN python -m playwright install --with-deps chromium

ENV CUGA_IN_DOCKER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps \
    CUGA_TARGET=ce

# App code + the built UI.
COPY cuga-apps/apps/ ./apps/
COPY --from=ui /ui/dist/ ./ui-dist/

# Generate the nginx config + startup script from _ports.py (single source of
# truth) so they always match the rest of the repo.
COPY build/generate.py ./build/generate.py
RUN rm -f /etc/nginx/sites-enabled/default \
    && python build/generate.py \
        --apps-dir /app/apps \
        --nginx /etc/nginx/conf.d/default.conf \
        --start /app/run_all.sh \
    && chmod +x /app/run_all.sh

EXPOSE 8080
CMD ["/app/run_all.sh"]
