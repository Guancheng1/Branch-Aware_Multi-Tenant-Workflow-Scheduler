#!/bin/bash
# 在运行中的Docker容器内应用results路由补丁

echo "🔧 正在Docker容器内应用结果文件访问补丁..."

# 创建临时Python脚本来修改main.py
docker-compose exec -T app python3 << 'PYTHON_SCRIPT'
import re

# 读取main.py
with open('/app/main.py', 'r') as f:
    content = f.read()

# 检查是否已经有results挂载
if 'mount("/results"' in content:
    print("✅ results路由已存在，无需修改")
    exit(0)

# 找到static挂载的位置，在其后添加results挂载
pattern = r'(# 挂载静态文件.*?logger\.warning\("Static directory not found.*?"\))'
replacement = r'''\1

# 挂载结果文件目录
try:
    app.mount("/results", StaticFiles(directory="results"), name="results")
    logger.info("Results files mounted at /results")
except RuntimeError:
    logger.warning("Results directory not found, skipping results files mounting")'''

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

# 如果替换成功，写回文件
if new_content != content:
    with open('/app/main.py', 'w') as f:
        f.write(new_content)
    print("✅ main.py已更新")
else:
    print("❌ 未能找到插入位置")
    exit(1)
PYTHON_SCRIPT

if [ $? -eq 0 ]; then
    echo ""
    echo "📝 验证修改..."
    docker-compose exec app grep -A2 'mount("/results"' /app/main.py
    
    echo ""
    echo "🔄 重启容器以应用更改..."
    docker-compose restart app
    
    echo ""
    echo "⏳ 等待服务启动..."
    sleep 5
    
    echo ""
    echo "✅ 完成! 现在测试结果文件访问..."
    sleep 2
    
    # 测试访问
    echo ""
    echo "🔍 测试结果文件访问:"
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/results/user-001/825269aa-a9d8-4038-b3e2-3b9344fb6562/segmentation_results.json)
    
    if [ "$STATUS" = "200" ]; then
        echo "  ✅ JSON文件访问成功! (状态码: $STATUS)"
    else
        echo "  ❌ JSON文件访问失败 (状态码: $STATUS)"
    fi
    
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/results/user-001/825269aa-a9d8-4038-b3e2-3b9344fb6562/visualization.jpg)
    
    if [ "$STATUS" = "200" ]; then
        echo "  ✅ 图像文件访问成功! (状态码: $STATUS)"
    else
        echo "  ❌ 图像文件访问失败 (状态码: $STATUS)"
    fi
    
    echo ""
    echo "🎉 补丁应用完成!"
    echo ""
    echo "💡 现在可以在浏览器中测试:"
    echo "   1. 打开: http://localhost:8000"
    echo "   2. 点击任务 825269aa-a9d8-4038-b3e2-3b9344fb6562"  
    echo "   3. 点击「查看结果」按钮"
else
    echo "❌ 补丁应用失败"
    exit 1
fi

