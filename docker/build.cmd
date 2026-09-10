@echo off
REM ==============================================================================
REM build.cmd
REM
REM Builds the softwaretree/orm_skyway image locally. Most people don't need
REM this -- "docker pull softwaretree/orm_skyway" gets you the published image
REM directly. Build it yourself only if you're modifying orm_skyway.py, the
REM Dockerfile, or docker-entrypoint.sh and want to test your changes, or if
REM your network can't reach Docker Hub but you already have this repo. See
REM docs/docker_mode.md for details.
REM
REM This script lives in docker/, but the build context is the REPO ROOT
REM (one level up) since orm_skyway.py lives there, not in docker/ --
REM see the comment at the top of Dockerfile for why. cd /d "%~dp0\.." makes
REM this work correctly whether you double-click this file or run it from
REM anywhere else.
REM
REM CHANGED 2026-09-09: added --pull to the docker build below. This image is
REM built FROM softwaretree/gilhari (see Dockerfile), so its actual content
REM depends on that base image too, not just this repo's own files -- without
REM --pull, a Docker build reuses whatever softwaretree/gilhari image is
REM already sitting in your local image cache, even if a newer one has since
REM been published to Docker Hub. That silently produces a build that looks
REM successful but doesn't actually contain a base-image update (e.g. a new
REM JDX version baked into softwaretree/gilhari) until you separately notice
REM and pull it yourself. --pull makes every build check Docker Hub for a
REM newer base image first, so this can never go stale unnoticed again.
REM ==============================================================================
cd /d "%~dp0\.."
docker buildx version >nul 2>&1
if errorlevel 1 echo Note: a 'legacy builder is deprecated' warning below (if shown) is harmless.
docker build --pull -f docker/Dockerfile -t softwaretree/orm_skyway:latest .
docker images softwaretree/orm_skyway
echo.
pause
