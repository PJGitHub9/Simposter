@echo off
REM Simposter Docker Build Script (Windows)
REM Automatically captures current git branch and passes it to the Docker build

REM Detect current git branch
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set GIT_BRANCH=%%i
if "%GIT_BRANCH%"=="" set GIT_BRANCH=unknown

echo Building Simposter Docker image...
echo Git branch: %GIT_BRANCH%

REM Build Docker image with git branch info
docker build ^
  --build-arg GIT_BRANCH=%GIT_BRANCH% ^
  --pull ^
  --rm ^
  -f Dockerfile ^
  -t simposter:latest ^
  -t simposter:local ^
  .

echo Build complete!
echo Image tagged as: simposter:latest, simposter:local
pause
