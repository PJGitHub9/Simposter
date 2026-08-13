#!/bin/bash

# Simposter Docker Build Script (Linux/Mac)
# Passes DOCKER_TAG into the image so the UI can warn when running an unsupported tag.
# Usage:
#   ./build-docker.sh              -> tags as simposter:latest and simposter:local, DOCKER_TAG=local
#   ./build-docker.sh dev          -> tags as simposter:dev, DOCKER_TAG=dev

# Allow an optional tag argument (default: local)
DOCKER_TAG="${1:-local}"

# Detect current git branch (falls back to "unknown" if not in a git repo)
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

echo "Building Simposter Docker image..."
echo "Docker tag: $DOCKER_TAG"
echo "Git branch: $GIT_BRANCH"

# Build Docker image — DOCKER_TAG/GIT_BRANCH are baked into build-info.json for runtime branch/tag detection
docker build \
  --build-arg DOCKER_TAG="$DOCKER_TAG" \
  --build-arg GIT_BRANCH="$GIT_BRANCH" \
  --pull \
  --rm \
  -f Dockerfile \
  -t simposter:"$DOCKER_TAG" \
  -t simposter:latest \
  .

echo ""
echo "Build complete!"
echo "Image tagged as: simposter:$DOCKER_TAG, simposter:latest"
