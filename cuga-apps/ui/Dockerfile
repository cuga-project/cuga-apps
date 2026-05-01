# ============================================================
# UI Dockerfile — builds the Vite/React umbrella UI and
# serves the static output with nginx.
#
# Build args (optional):
#   VITE_DEPLOYMENT_TARGET   "huggingface" | "local"
#       When "huggingface", baked-in flag flips "Try it" / "Launch App"
#       links from http://localhost:28xxx to the corresponding Code
#       Engine deployment URLs. Unset → runtime hostname detection
#       handles it (auto-flips when served from *.hf.space).
#
# Example:
#   docker build -t myuser/cuga-apps-ui:hf \
#     --build-arg VITE_DEPLOYMENT_TARGET=huggingface ui/
# ============================================================

# Stage 1: build
FROM node:20-alpine AS build
WORKDIR /app

# Vite reads VITE_*  env vars at build time and burns them into the
# bundle. NOT a secret — see ui/src/data/deployment.ts for what we use.
ARG VITE_DEPLOYMENT_TARGET=""
ENV VITE_DEPLOYMENT_TARGET=$VITE_DEPLOYMENT_TARGET

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# Stage 2: serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# 7860 (non-privileged) instead of the nginx default 80 so the same image
# runs unchanged on Hugging Face Spaces (HF rejects app_port < 1025).
EXPOSE 7860
