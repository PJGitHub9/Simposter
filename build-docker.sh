#!/bin/bash

# Simposter Docker Build Script
# Automatically captures current git branch and passes it to the Docker build

# Detect current git branch
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")

echo "Building Simposter Docker image..."
echo "Git branch: $GIT_BRANCH"

# Build Docker image with git branch info
docker build \
  --build-arg GIT_BRANCH="$GIT_BRANCH" \
  --pull \
  --rm \
  -f Dockerfile \
  -t simposter:latest \
  -t simposter:local \
  .

echo "Build complete!"
echo "Image tagged as: simposter:latest, simposter:local"
