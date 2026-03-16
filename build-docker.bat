@echo off
REM Simposter Docker Build Script (Windows)
REM Passes DOCKER_TAG into the image so the UI can warn when running an unsupported tag.
REM Usage:
REM   build-docker.bat              -> tags as simposter:latest and simposter:local, DOCKER_TAG=local
REM   build-docker.bat webui-overhaul-dev  -> tags as simposter:webui-overhaul-dev, DOCKER_TAG=webui-overhaul-dev

REM Allow an optional tag argument (default: local)
set DOCKER_TAG=%~1
if "%DOCKER_TAG%"=="" set DOCKER_TAG=local

echo Building Simposter Docker image...
echo Docker tag: %DOCKER_TAG%

REM Build Docker image — DOCKER_TAG is baked into build-info.json for runtime branch/tag detection
docker build ^
  --build-arg DOCKER_TAG=%DOCKER_TAG% ^
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
