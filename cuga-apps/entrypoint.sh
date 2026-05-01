#!/bin/sh
# Universal container entrypoint for cuga-apps images.
#
# Loads secrets from a runtime-mounted env file (read-only volume) into the
# process environment, then exec's whatever command was passed. Doing it here
# instead of via docker-compose's env_file: keeps the values out of `docker
# inspect` and out of the image itself.
#
# Mount via docker-compose:
#     volumes:
#       - ./apps/.env:/run/secrets/app.env:ro

set -e

SECRETS_FILE="${CUGA_SECRETS_FILE:-/run/secrets/app.env}"

if [ -f "$SECRETS_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$SECRETS_FILE"
    set +a
fi

exec "$@"
