#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# IMPORTANT: Change this to the absolute path of your project directory on the server.
PROJECT_DIR="/home/vaibhav/chronos"
CONTAINER_NAME="chronos"

echo "--- Starting deployment ---"

# --- Setup ---
if [ -d "$PROJECT_DIR" ]; then
    echo "--- Project directory found. Fetching latest code... ---"
    cd "$PROJECT_DIR"
    git fetch origin
    echo "--- Resetting prod branch to match remote ---"
    git checkout prod
    git reset --hard origin/prod
else
    echo "--- Project directory not found. Cloning repository... ---"
    git clone "$GIT_REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    git checkout prod
fi

echo "--- In project directory: $(pwd) ---"

# --- Docker Operations ---
echo "--- Stopping and removing old container ---"
docker stop "$CONTAINER_NAME" || true
docker rm "$CONTAINER_NAME" || true

echo "--- Building new Docker image ---"
docker build -t "$CONTAINER_NAME" .

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
