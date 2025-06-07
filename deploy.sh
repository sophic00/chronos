#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
# IMPORTANT: Change this to the absolute path of your project directory on the server.
PROJECT_DIR="/home/vaibhav/my-debauch-devotion"
CONTAINER_NAME="submission-notifier"

echo "--- Starting deployment ---"

# --- Navigation ---
cd "$PROJECT_DIR"
echo "--- In project directory: $(pwd) ---"

# --- Git Update ---
echo "--- Pulling latest code from prod branch ---"
git checkout prod
git pull origin prod

# --- Docker Operations ---
echo "--- Stopping and removing old container ---"
docker stop "$CONTAINER_NAME" || true
docker rm "$CONTAINER_NAME" || true

echo "--- Building new Docker image ---"
docker build -t "$CONTAINER_NAME" .

# Create a data directory for persistent storage if it doesn't exist
mkdir -p data

echo "--- Starting new container ---"
docker run -d \
    --restart always \
    --name "$CONTAINER_NAME" \
    --env-file .env \
    -v "$(pwd)/data:/app/data" \
    "$CONTAINER_NAME"

# --- Cleanup ---
echo "--- Pruning old Docker images ---"
docker image prune -f

echo "--- Deployment finished successfully! ---" 
