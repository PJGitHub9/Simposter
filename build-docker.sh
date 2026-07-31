#!/bin/bash

# Simposter Docker Build Script (Linux/Mac)
# Passes DOCKER_TAG into the image so the UI can warn when running an unsupported tag.
# Usage:
#   ./build-docker.sh              -> tags as simposter:latest and simposter:local, DOCKER_TAG=local
#   ./build-docker.sh dev          -> tags as simposter:dev, DOCKER_TAG=dev

# Allow an optional tag argument (default: local)
DOCKER_TAG="${1:-local}"

echo "Building Simposter Docker image..."
echo "Docker tag: $DOCKER_TAG"

# Build Docker image — DOCKER_TAG is baked into build-info.json for runtime branch/tag detection
docker build \
  --build-arg DOCKER_TAG="$DOCKER_TAG" \
  --pull \
  --rm \
  -f Dockerfile \
  -t simposter:"$DOCKER_TAG" \
  -t simposter:latest \
  .

echo ""
echo "Build complete!"
echo "Image tagged as: simposter:$DOCKER_TAG, simposter:latest"
