#!/bin/bash
# ==============================================================================
# docker-entrypoint.sh — softwaretree/orm_skyway
#
# Docker Hub has no mechanism to gate a `docker pull` behind a license
# agreement, so the agreement is shown here instead, the first time the image
# is actually *run* against a given project directory. orm_skyway.py inherits
# the Gilhari product license (the same one the user already accepts when
# pulling/running softwaretree/gilhari).
#
# Acceptance is recorded as a marker file inside the bind-mounted /project
# directory, so it survives across --rm container runs and is only asked once
# per project. For CI / non-interactive use, set ORM_SKYWAY_ACCEPT_LICENSE=yes.
# ==============================================================================
set -e

LICENSE_FILE="/opt/orm_skyway/LICENSE_AGREEMENT.txt"
MARKER_FILE="/project/.orm_skyway_license_accepted"

show_license_and_prompt() {
    echo "=============================================================================="
    echo " softwaretree/orm_skyway — License Agreement"
    echo "=============================================================================="
    if [ -f "$LICENSE_FILE" ]; then
        cat "$LICENSE_FILE"
    else
        echo "orm_skyway.py is distributed under the Software Tree, LLC Gilhari product"
        echo "license. See https://github.com/SoftwareTree/orm_skyway for details."
    fi
    echo "=============================================================================="
    echo

    if [ "$ORM_SKYWAY_ACCEPT_LICENSE" = "yes" ] || [ "$ORM_SKYWAY_ACCEPT_LICENSE" = "true" ]; then
        echo "ORM_SKYWAY_ACCEPT_LICENSE is set — license accepted non-interactively."
        return 0
    fi

    if [ ! -t 0 ]; then
        echo "No interactive terminal attached and ORM_SKYWAY_ACCEPT_LICENSE is not set."
        echo "Re-run with -it, or set -e ORM_SKYWAY_ACCEPT_LICENSE=yes to accept and continue."
        exit 1
    fi

    read -r -p "Do you accept this license agreement? [y/N] " REPLY
    case "$REPLY" in
        [yY][eE][sS]|[yY])
            return 0
            ;;
        *)
            echo "License not accepted. Exiting."
            exit 1
            ;;
    esac
}

if [ -d "/project" ]; then
    if [ ! -f "$MARKER_FILE" ]; then
        show_license_and_prompt
        # Best-effort: /project may be a read-only mount in some CI setups.
        date -u +"%Y-%m-%dT%H:%M:%SZ — accepted via softwaretree/orm_skyway" \
            > "$MARKER_FILE" 2>/dev/null || true
    fi
else
    # No project volume mounted at all (e.g. `docker run softwaretree/orm_skyway --version`).
    show_license_and_prompt
fi

exec python3 /opt/orm_skyway/orm_skyway.py "$@"
