@echo off
REM ==============================================================================
REM run_orm_skyway.cmd
REM
REM Wrapper around "docker run" for the softwaretree/orm_skyway image. Run this
REM from your project root directory (the directory containing
REM orm_skyway_config.json) -- same place you would normally run orm_skyway.py.
REM
REM Usage:
REM   run_orm_skyway.cmd -f orm_skyway_config.json --phase 1+3
REM   run_orm_skyway.cmd -f orm_skyway_config.json --yes
REM   run_orm_skyway.cmd --version
REM
REM All arguments are passed straight through to orm_skyway.py inside the
REM container. Docker Desktop for Windows resolves host.docker.internal
REM natively, so no --add-host flag is needed here (unlike Linux/Colima --
REM see run_orm_skyway.sh).
REM
REM Mounts:
REM   -v "%cd%:/project"                          your project directory
REM   -v /var/run/docker.sock:/var/run/docker.sock
REM                                                lets "docker build" (Phase 3)
REM                                                run from inside this Linux
REM                                                container, on the host's
REM                                                Docker daemon. Even on
REM                                                Windows, this is the correct
REM                                                mount for a LINUX container --
REM                                                Docker Desktop's WSL2 backend
REM                                                exposes the daemon at this
REM                                                Unix socket path; the Windows
REM                                                named pipe (//./pipe/docker_engine)
REM                                                is only for native Windows
REM                                                containers, not applicable here.
REM
REM --platform linux/amd64:
REM   softwaretree/orm_skyway (built on softwaretree/gilhari) is currently
REM   single-architecture (amd64-only). This is a no-op on standard x86_64
REM   Windows, included here only for consistency with run_orm_skyway.sh,
REM   where it matters on Apple Silicon Macs (avoids a platform-mismatch pull
REM   error) -- see the comment in that script for details.
REM
REM SQLite (or other file-based) database NOT under your project directory:
REM   The %cd%:/project mount above covers any path inside (or below) the
REM   directory you run this script from -- e.g. a DB at .\config\mydb.sqlite
REM   needs nothing extra; orm_skyway_config.json should reference it with a
REM   relative path, e.g. "jdbc:sqlite:config/mydb.sqlite".
REM
REM   If your DB file lives somewhere else entirely (e.g. C:\data\mydb.sqlite),
REM   set ORM_SKYWAY_EXTRA_MOUNT to a "host_path:container_path" pair before
REM   running this script, and point jdbc_url at the container_path side:
REM
REM     set ORM_SKYWAY_EXTRA_MOUNT=C:\data:/extra_data
REM     run_orm_skyway.cmd -f orm_skyway_config.json
REM
REM   with "jdbc_url": "jdbc:sqlite:/extra_data/mydb.sqlite" in your config.
REM
REM -e ORM_SKYWAY_HOST_PROJECT_DIR=%cd%:
REM   Lets orm_skyway.py translate its in-container /project path back to
REM   your real Windows path when generating scripts that run later, directly
REM   on this host (run_docker_app.cmd, build.cmd, ...) -- e.g. so a SQLite
REM   file's volume mount points at a real host path instead of "/project/...".
REM ==============================================================================
set "EXTRA_MOUNT_FLAG="
if defined ORM_SKYWAY_EXTRA_MOUNT set "EXTRA_MOUNT_FLAG=-v "%ORM_SKYWAY_EXTRA_MOUNT%""

docker run --rm -it ^
    --platform linux/amd64 ^
    -v "%cd%:/project" ^
    -v "/var/run/docker.sock:/var/run/docker.sock" ^
    -e "ORM_SKYWAY_HOST_PROJECT_DIR=%cd%" ^
    %EXTRA_MOUNT_FLAG% ^
    softwaretree/orm_skyway %*
