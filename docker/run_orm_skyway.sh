#!/bin/bash
# ==============================================================================
# run_orm_skyway.sh
#
# Wrapper around `docker run` for the softwaretree/orm_skyway image. Run this
# from your project root directory (the directory containing
# orm_skyway_config.json) — same place you would normally run orm_skyway.py.
#
# Usage:
#   ./run_orm_skyway.sh -f orm_skyway_config.json --phase 1+3
#   ./run_orm_skyway.sh -f orm_skyway_config.json --yes
#   ./run_orm_skyway.sh --version
#
# All arguments are passed straight through to orm_skyway.py inside the
# container. Paths in your config file's "-f" target stay relative to the
# project directory, which is mounted at /project inside the container.
#
# Mounts:
#   -v "$(pwd):/project"                 your project directory
#   -v /var/run/docker.sock:/var/run/docker.sock
#                                         lets `docker build` (Phase 3) run
#                                         from inside this container, building
#                                         images on the host's Docker daemon
#
# --add-host=host.docker.internal:host-gateway is required on Linux and on
# Colima — without it, host.docker.internal does not resolve and Phase 1
# cannot reach a database running on localhost on the host machine.
#
# SQLite (or other file-based) database NOT under your project directory:
#   The "$(pwd):/project" mount above covers any path inside (or below) the
#   directory you run this script from -- e.g. a DB at ./config/mydb.sqlite
#   needs nothing extra; orm_skyway_config.json should reference it with a
#   relative path, e.g. "jdbc:sqlite:config/mydb.sqlite".
#
#   If your DB file lives somewhere else entirely (e.g. /data/mydb.sqlite),
#   set ORM_SKYWAY_EXTRA_MOUNT to a "host_path:container_path" pair before
#   running this script, and point jdbc_url at the container_path side:
#
#     ORM_SKYWAY_EXTRA_MOUNT=/data:/extra_data ./run_orm_skyway.sh -f orm_skyway_config.json
#
#   with "jdbc_url": "jdbc:sqlite:/extra_data/mydb.sqlite" in your config.
# ==============================================================================
set -e

DOCKER_SOCK="/var/run/docker.sock"
SOCK_MOUNT=()
if [ -S "$DOCKER_SOCK" ]; then
    SOCK_MOUNT=(-v "$DOCKER_SOCK:$DOCKER_SOCK")
else
    echo "Warning: $DOCKER_SOCK not found — 'docker build' (Phase 3) will not" >&2
    echo "         work from inside the container. Is the Docker daemon running?" >&2
fi

EXTRA_MOUNT=()
if [ -n "$ORM_SKYWAY_EXTRA_MOUNT" ]; then
    EXTRA_MOUNT=(-v "$ORM_SKYWAY_EXTRA_MOUNT")
fi

exec docker run --rm -it \
    --add-host=host.docker.internal:host-gateway \
    -v "$(pwd):/project" \
    -e "ORM_SKYWAY_HOST_PROJECT_DIR=$(pwd)" \
    "${SOCK_MOUNT[@]}" \
    "${EXTRA_MOUNT[@]}" \
    softwaretree/orm_skyway "$@"
