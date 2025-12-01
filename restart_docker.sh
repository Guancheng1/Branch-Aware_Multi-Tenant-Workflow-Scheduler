#!/bin/bash

# Quick Docker container restart script (development mode)
echo "🔄 Restarting Docker containers..."

# Restart app container
docker-compose restart app

echo "✅ Containers restarted!"
echo "📊 View logs: docker-compose logs -f app"

