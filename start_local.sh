#!/bin/bash

# Local startup script (without Docker)

echo "======================================"
echo "Branch-Aware Multi-Tenant Workflow Scheduler"
echo "Local Startup Mode"
echo "======================================"
echo ""

# Set OpenSlide library path (macOS)
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p uploads results logs
echo "✅ Directories created"
echo ""

# Check Python dependencies
echo "Checking dependencies..."
python -c "import fastapi" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️ Missing dependencies, installing..."
    python -m pip install --user -q fastapi uvicorn pydantic pydantic-settings opencv-python numpy pillow openslide-python
    echo "✅ Dependencies installed"
else
    echo "✅ Dependencies already installed"
fi
echo ""

# Start services
echo "Starting services..."
echo ""
echo "======================================"
echo "Services starting..."
echo "======================================"
echo ""
echo "Access URLs:"
echo "  - Web UI:     http://localhost:8000"
echo "  - API Docs:   http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop service"
echo ""

# Run application
python main.py

