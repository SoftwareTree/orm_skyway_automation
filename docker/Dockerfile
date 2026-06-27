# ==============================================================================
# softwaretree/orm_skyway
#
# Packages orm_skyway.py + Python on top of the softwaretree/gilhari base image
# (which already includes a JDK and the JDX ORM libraries). This reduces the
# end-user's prerequisites to "Docker only" — no local JDK, JDX SDK, or Python
# install required to run Phase 1 + Phase 3 of the ORM Skyway workflow.
#
# Repo layout: this Dockerfile lives in docker/, but orm_skyway.py lives at
# the repo root (so non-Docker users can grab just that one file without the
# rest of this directory) — so the build context is the REPO ROOT, not this
# docker/ directory, with -f pointing at this file:
#
#   cd orm_skyway_automation/        (repo root)
#   docker build -f docker/Dockerfile -t softwaretree/orm_skyway:latest .
#
# Prefer build.cmd / build.sh in this same directory, which set this up
# automatically (including the correct working directory regardless of where
# they're invoked from).
#
# Run (from the project root directory on the host):
#   docker run --rm -it \
#     --add-host=host.docker.internal:host-gateway \
#     -v "$(pwd):/project" \
#     -v /var/run/docker.sock:/var/run/docker.sock \
#     softwaretree/orm_skyway -f /project/orm_skyway_config.json
#
# (Prefer the generated run_orm_skyway.sh / run_orm_skyway.cmd wrapper, which
# includes all required flags automatically — see those scripts for details.)
# ==============================================================================

ARG BASE_PLATFORM=linux/amd64
FROM --platform=${BASE_PLATFORM} softwaretree/gilhari

LABEL org.opencontainers.image.title="softwaretree/orm_skyway"
LABEL org.opencontainers.image.description="Automates turning a relational database into an AI-ready REST microservice (Gilhari) via JDX ORM."
LABEL org.opencontainers.image.vendor="Software Tree, LLC"
LABEL org.opencontainers.image.licenses="See LICENSE / LICENSE_AGREEMENT.txt — inherits the Gilhari product license."

# ── Python 3 + pip ────────────────────────────────────────────────────────────
# Base image confirmed: Ubuntu 20.04 + openjdk-8-jdk + Node v20.10.0 (binary
# tarball install, not apt) — so apt-get is correct here and python3-pip is
# available directly from the Ubuntu 20.04 archive (no deadsnakes PPA needed).
# Ubuntu 20.04 ships Python 3.8, which matches orm_skyway.py's stated 3.8+
# minimum exactly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

# pip on Ubuntu 20.04's python3-pip is old enough that --break-system-packages
# is unrecognized (PEP 668 enforcement was added in much later pip/Debian
# releases) — safe to call pip3 directly without that flag on this base image.
RUN pip3 install --no-cache-dir rich

# ── Docker CLI ────────────────────────────────────────────────────────────────
# Needed so Phase 3's `docker build` (invoked by orm_skyway.py via subprocess)
# can talk to the host's Docker daemon through the socket mounted at
# /var/run/docker.sock by run_orm_skyway.sh/.cmd. docker.io's client package
# pulls in some daemon-only bits too, but that's fine — we never run dockerd
# in this container, only the client binary against the mounted host socket.
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/orm_skyway
COPY orm_skyway.py                ./orm_skyway.py
COPY docker/LICENSE_AGREEMENT.txt ./LICENSE_AGREEMENT.txt
COPY docker/docker-entrypoint.sh  ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# Project files are bind-mounted at /project by the caller (run_orm_skyway.sh/.cmd
# or an equivalent `docker run -v "$(pwd):/project" ...`). All artifacts
# orm_skyway.py writes (config/, src/, bin/, generated scripts, Dockerfile, ...)
# land on the host via that mount.
WORKDIR /project

ENV PYTHONUNBUFFERED=1

# The entrypoint shows the one-time license agreement (inherited from the
# Gilhari product license) before the very first run against a given project
# directory, then execs orm_skyway.py with whatever args the user passed.
ENTRYPOINT ["/opt/orm_skyway/docker-entrypoint.sh"]
CMD ["--help"]
