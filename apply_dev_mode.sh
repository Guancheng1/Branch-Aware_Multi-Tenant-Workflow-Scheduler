#!/bin/bash

# Apply development mode configuration (use after first run or modifying docker-compose.yml)
echo "🔧 Applying development mode configuration..."
echo ""

echo "1️⃣ Stopping existing containers..."
docker-compose down

echo ""
echo "2️⃣ Starting with new configuration (source code mount + auto-reload)..."
docker-compose up -d

echo ""
echo "3️⃣ Waiting for containers to start..."
sleep 3

echo ""
echo "✅ Development mode enabled!"
echo ""
echo "📋 Features:"
echo "  • Source code mounted (backend/, main.py)"
echo "  • Auto-reload enabled (code changes trigger automatic restart)"
echo "  • No need to rebuild image"
echo ""
echo "📊 View logs: docker-compose logs -f app"
echo "🔄 Manual restart: ./restart_docker.sh"
echo "⏹️  Stop service: docker-compose down"
echo ""

