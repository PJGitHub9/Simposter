@echo off
REM Simposter Docker Build Script (Windows)
REM Passes DOCKER_TAG into the image so the UI can warn when running an unsupported tag.
REM Usage:
REM   build-docker.bat              -> tags as simposter:latest and simposter:local, DOCKER_TAG=local
REM   build-docker.bat webui-overhaul-dev  -> tags as simposter:webui-overhaul-dev, DOCKER_TAG=webui-overhaul-dev

REM Allow an optional tag argument (default: local)
set DOCKER_TAG=%~1
if "%DOCKER_TAG%"=="" set DOCKER_TAG=local

REM Detect current git branch (falls back to "unknown" if not in a git repo)
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set GIT_BRANCH=%%b
if "%GIT_BRANCH%"=="" set GIT_BRANCH=unknown

echo Building Simposter Docker image...
echo Docker tag: %DOCKER_TAG%
echo Git branch: %GIT_BRANCH%

REM Build Docker image — DOCKER_TAG/GIT_BRANCH are baked into build-info.json for runtime branch/tag detection
docker build ^
  --build-arg DOCKER_TAG=%DOCKER_TAG% ^
  --build-arg GIT_BRANCH=%GIT_BRANCH% ^
  --pull ^
  --rm ^
  -f Dockerfile ^
  -t simposter:%DOCKER_TAG% ^
  -t simposter:latest ^
  .

echo.
echo Build complete!
echo Image tagged as: simposter:%DOCKER_TAG%, simposter:latest
pause
