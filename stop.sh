#!/bin/bash

# Stop service script

echo "======================================"
echo "Stopping Workflow Scheduler Service"
echo "======================================"
echo ""

docker-compose down

echo ""
echo "✅ Services stopped"
echo ""


