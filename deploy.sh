#!/bin/bash
set -euo pipefail # Exit immediately on error, undefined vars, or failed pipes.

# --- Configuration ---
# Override with CHRONOS_PROJECT_DIR if the project lives elsewhere.
PROJECT_DIR="${CHRONOS_PROJECT_DIR:-/home/deploy/chronos}"
CONTAINER_NAME="chronos"
BRANCH="prod"

echo "--- Starting deployment ---"

# --- Navigation & Git Update ---
cd "$PROJECT_DIR"
echo "--- In project directory: $(pwd) ---"
if [ ! -f .env ]; then
    echo "ERROR: $PROJECT_DIR/.env not found. Aborting before touching anything." >&2
    exit 1
fi
echo "--- Fetching latest code from origin ---"
git fetch origin
echo "--- Resetting $BRANCH to match remote ---"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

# --- Docker Operations ---
echo "--- Building new image (old container keeps running) ---"
docker build -t "$CONTAINER_NAME" .

echo "--- Stopping and removing old container ---"
docker stop "$CONTAINER_NAME" || true
docker rm "$CONTAINER_NAME" || true

# Create a data directory for persistent storage if it doesn't exist
mkdir -p data

# Sanitize .env file for Docker by removing quotes and comments.
# This creates a temporary, clean .env file for Docker to use.
sed -e "s/'//g" -e 's/"//g' -e 's/[[:space:]]*#.*$//' .env > .env.docker

echo "--- Starting new container ---"
docker run -d \
    --restart always \
    --name "$CONTAINER_NAME" \
    --env-file .env.docker \
    -v "$(pwd)/data:/app/data" \
    "$CONTAINER_NAME"

# --- Cleanup ---
rm .env.docker
echo "--- Pruning old Docker images ---"
docker image prune -f

echo "--- Deployment finished successfully! ---"
