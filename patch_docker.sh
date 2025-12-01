#!/bin/bash
# Apply results route patch inside running Docker container

echo "🔧 Applying results file access patch inside Docker container..."

# Create temporary Python script to modify main.py
docker-compose exec -T app python3 << 'PYTHON_SCRIPT'
import re

# Read main.py
with open('/app/main.py', 'r') as f:
    content = f.read()

# Check if results mount already exists
if 'mount("/results"' in content:
    print("✅ Results route already exists, no modification needed")
    exit(0)

# Find static mount location and add results mount after it
pattern = r'(# Mount static files.*?logger\.warning\("Static directory not found.*?"\))'
replacement = r'''\1

# Mount results file directory
try:
    app.mount("/results", StaticFiles(directory="results"), name="results")
    logger.info("Results files mounted at /results")
except RuntimeError:
    logger.warning("Results directory not found, skipping results files mounting")'''

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# If replacement successful, write back to file
if new_content != content:
    with open('/app/main.py', 'w') as f:
        f.write(new_content)
    print("✅ main.py updated")
else:
    print("❌ Could not find insertion point")
    exit(1)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    echo ""
    echo "📝 Verifying changes..."
    docker-compose exec app grep -A2 'mount("/results"' /app/main.py
    
    echo ""
    echo "🔄 Restarting container to apply changes..."
    docker-compose restart app
    
    echo ""
    echo "⏳ Waiting for service to start..."
    sleep 5
    
    echo ""
    echo "✅ Complete! Now testing results file access..."
    sleep 2
    
    # Test access
    echo ""
    echo "🔍 Testing results file access:"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/results/user-001/825269aa-a9d8-4038-b3e2-3b9344fb6562/segmentation_results.json)
    
    if [ "$STATUS" = "200" ]; then
        echo "  ✅ JSON file access successful! (Status code: $STATUS)"
    else
        echo "  ❌ JSON file access failed (Status code: $STATUS)"
    fi
    
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/results/user-001/825269aa-a9d8-4038-b3e2-3b9344fb6562/visualization.jpg)
    
    if [ "$STATUS" = "200" ]; then
        echo "  ✅ Image file access successful! (Status code: $STATUS)"
    else
        echo "  ❌ Image file access failed (Status code: $STATUS)"
    fi
    
    echo ""
    echo "🎉 Patch application complete!"
    echo ""
    echo "💡 You can now test in browser:"
    echo "   1. Open: http://localhost:8000"
    echo "   2. Click on task 825269aa-a9d8-4038-b3e2-3b9344fb6562"  
    echo "   3. Click the 'View Results' button"
else
    echo "❌ Patch application failed"
    exit 1
fi

