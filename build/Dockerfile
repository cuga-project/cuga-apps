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
# Self-contained: the 5 MCP servers the ship-ready apps use (web, knowledge,
# geo, finance, local) are bundled and run on loopback inside this container
# (CUGA_TARGET=local). No external MCP deployment is required — the whole
# environment (UI + 21 apps + MCP servers) comes up from one image / one
# `docker compose up`. Service keys (Tavily/OpenTripMap/AlphaVantage) come in
# via env (see build/.env.example).
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

# CPU-only PyTorch FIRST. `cuga` pulls torch transitively (via docling /
# transformers / accelerate), and torch's default PyPI wheel bundles the full
# NVIDIA CUDA stack (nvidia-* + triton ≈ 4.4 GB) that is dead weight in this
# CPU-only container. Installing the +cpu build up front satisfies the version
# constraint, so the requirements.apps.txt resolve below never drags in the
# CUDA wheels. Keeps all functionality; ~4.4 GB smaller image.
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch==2.12.0 torchvision

# App deps (cuga + sqlite-vec + feedparser + playwright + the LangChain stack).
# The ship-ready set does NOT include video_qa/deck_forge, so the heavy file
# (chromadb + sentence-transformers) is intentionally skipped — leaner image.
COPY cuga-apps/requirements.apps.txt ./
RUN pip install --no-cache-dir -r requirements.apps.txt

# MCP server deps (lean subset — see build/requirements.mcp.txt). The 5 servers
# the ship-ready apps use are bundled into this image and run on loopback, so
# the apps need NO external MCP deployment.
COPY build/requirements.mcp.txt ./requirements.mcp.txt
RUN pip install --no-cache-dir -r requirements.mcp.txt

# Chromium for the one browser-driven ship-ready app (meetup_finder).
RUN python -m playwright install --with-deps chromium

# CUGA_TARGET=local + the explicit MCP_<NAME>_URL exports in run_all.sh point
# every app at the in-container MCP servers. PYTHONPATH includes /app so the
# `mcp_servers` package and `apps._ports` import resolve.
ENV CUGA_IN_DOCKER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/apps \
    CUGA_TARGET=local

# App code, the MCP servers, and the built UI.
COPY cuga-apps/apps/ ./apps/
COPY cuga-apps/mcp_servers/ ./mcp_servers/
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

# ── Build provenance ─────────────────────────────────────────────────────────
# Git commit + build time, baked in so the internal stats dashboard can show
# exactly which image is live (GET /api/build → footer on /a/usage-collector/).
# Declared LAST, on purpose: these values change every build, so keeping them
# after the heavy pip/npm/playwright layers means a new stamp only rebuilds
# these trivial layers — the expensive ones stay cached. `.git` isn't in the
# build context, so the values are computed on the host and passed as build-args
# (see build/ce/build_and_push.sh and build/docker-compose.yml).
ARG CUGA_BUILD_TIME=""
ARG CUGA_GIT_COMMIT=""
ARG CUGA_GIT_SHA=""
ARG CUGA_GIT_BRANCH=""
ARG CUGA_GIT_SUBJECT=""
ARG CUGA_GIT_COMMIT_TIME=""
ENV CUGA_BUILD_TIME=$CUGA_BUILD_TIME \
    CUGA_GIT_COMMIT=$CUGA_GIT_COMMIT \
    CUGA_GIT_SHA=$CUGA_GIT_SHA \
    CUGA_GIT_BRANCH=$CUGA_GIT_BRANCH \
    CUGA_GIT_SUBJECT=$CUGA_GIT_SUBJECT \
    CUGA_GIT_COMMIT_TIME=$CUGA_GIT_COMMIT_TIME

EXPOSE 8080
CMD ["/app/run_all.sh"]
