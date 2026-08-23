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
REM ==============================================================================
cd /d "%~dp0\.."
docker buildx version >nul 2>&1
if errorlevel 1 echo Note: a 'legacy builder is deprecated' warning below (if shown) is harmless.
docker build -f docker/Dockerfile -t softwaretree/orm_skyway:latest .
docker images softwaretree/orm_skyway
echo.
pause
