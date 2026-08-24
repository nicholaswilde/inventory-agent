#!/bin/bash

# Exit on any error
set -e

# Configuration
IMAGE="ghcr.io/sysadminsmedia/homebox:latest"
PORT="7745"
CONTAINER_NAME="homebox-test-$(date +%s)"

echo "Starting HomeBox container ($CONTAINER_NAME)..."
sudo docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:7745" \
  -e HBOX_LOG_LEVEL=info \
  -e HBOX_AUTH_API_KEY_PEPPER="$(openssl rand -base64 48)" \
  "$IMAGE" > /dev/null

# Ensure container is stopped and removed when script exits
cleanup() {
  echo "Cleaning up..."
  sudo docker rm -f "$CONTAINER_NAME" > /dev/null
}
trap cleanup EXIT

echo "Waiting for HomeBox to be ready..."
# Wait up to 30 seconds
for i in {1..30}; do
  if [ "$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/)" -eq 200 ]; then
    echo "HomeBox is up and running!"
    break
  fi
  if [ "$i" -eq 30 ]; then
    echo "Timeout waiting for HomeBox to start."
    sudo docker logs "$CONTAINER_NAME"
    exit 1
  fi
  sleep 1
done

echo "Running tests..."

# Test 1: Check if the application is serving HTML on the root endpoint
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/)
if [ "$HTTP_STATUS" -eq 200 ]; then
  echo "✅ Test 1 Passed: Root endpoint returned HTTP 200"
else
  echo "❌ Test 1 Failed: Root endpoint returned HTTP $HTTP_STATUS"
  exit 1
fi

echo "All tests passed successfully!"
