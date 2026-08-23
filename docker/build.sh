#!/bin/bash
# ==============================================================================
# build.sh
#
# Builds the softwaretree/orm_skyway image locally. Most people don't need
# this -- `docker pull softwaretree/orm_skyway` gets you the published image
# directly. Build it yourself only if you're modifying orm_skyway.py, the
# Dockerfile, or docker-entrypoint.sh and want to test your changes, or if
# your network can't reach Docker Hub but you already have this repo. See
# docs/docker_mode.md for details.
#
# This script lives in docker/, but the build context is the REPO ROOT (one
# level up) since orm_skyway.py lives there, not in docker/ -- see the
# comment at the top of Dockerfile for why. cd "$(dirname "$0")/.." makes
# this work correctly regardless of where it's invoked from.
# ==============================================================================
set -e
cd "$(dirname "$0")/.."
docker buildx version >/dev/null 2>&1 || \
    echo "Note: a 'legacy builder is deprecated' warning below (if shown) is harmless."
docker build -f docker/Dockerfile -t softwaretree/orm_skyway:latest .
docker images softwaretree/orm_skyway
