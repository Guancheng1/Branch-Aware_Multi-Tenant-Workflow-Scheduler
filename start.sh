#!/bin/bash

# Quick start script

echo "======================================"
echo "Branch-Aware Multi-Tenant Workflow Scheduler"
echo "======================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running, please start Docker first"
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Check docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed"
    exit 1
fi

echo "✅ docker-compose is installed"
echo ""

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p uploads results logs
echo "✅ Directories created"
echo ""

# Start services
echo "Starting services..."
docker-compose up -d

echo ""
echo "Waiting for services to start..."
sleep 10

# Check service status
echo ""
echo "Checking service status..."
docker-compose ps

echo ""
echo "======================================"
echo "Services started!"
echo "======================================"
echo ""
echo "Access URLs:"
echo "  - Web UI:     http://localhost:8000"
echo "  - API Docs:   http://localhost:8000/docs"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana:    http://localhost:3000 (admin/admin)"
echo ""
echo "View logs:"
echo "  docker-compose logs -f app"
echo ""
echo "Stop services:"
echo "  docker-compose down"
echo ""


