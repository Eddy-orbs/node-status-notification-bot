#!/bin/bash

# update.sh - Update Git, build Docker, and restart service in one operation

set -e

echo "=========================================="
echo "Node Status Notification Bot Update Started"
echo "=========================================="

# 1. Update to latest version
echo ""
echo "[1/3] Updating Git to latest version..."
git pull
echo "✓ Git update completed"

# 2. Build Docker image
echo ""
echo "[2/3] Building Docker image..."
sudo docker compose build --no-cache
echo "✓ Docker build completed"

# 3. Restart service
echo ""
echo "[3/3] Restarting service..."
sudo docker compose down
sudo docker compose up -d
echo "✓ Service restart completed"

echo ""
echo "=========================================="
echo "Update completed!"
echo "=========================================="
echo ""
echo "Service status:"
sudo docker compose ps
