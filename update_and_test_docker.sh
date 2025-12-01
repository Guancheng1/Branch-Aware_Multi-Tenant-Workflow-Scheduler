#!/bin/bash
# Update Docker and test results file access

echo "🐳 Updating Docker container and testing results file access"
echo "=========================================="

# Navigate to project directory
cd "$(dirname "$0")"

echo ""
echo "Step 1/3: Rebuilding Docker image (applying latest code)..."
echo "--------------------------------------------"
docker-compose build app

if [ $? -ne 0 ]; then
    echo "❌ Docker build failed!"
    exit 1
fi

echo ""
echo "Step 2/3: Restarting application container..."
echo "--------------------------------------------"
docker-compose restart app

# Wait for service to start
echo "⏳ Waiting for service to start..."
sleep 5

# Check service status
echo ""
echo "📊 Container status:"
docker-compose ps

echo ""
echo "Step 3/3: Running test script..."
echo "--------------------------------------------"
python3 test_docker_results.py

echo ""
echo "=========================================="
echo "✅ Complete!"
echo ""
echo "💡 If tests passed, you can now test in browser:"
echo "   1. Open: http://localhost:8000"
echo "   2. Click on a completed task"
echo "   3. Click the 'View Results' button"

