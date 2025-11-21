#!/bin/bash
# 更新Docker并测试结果文件访问

echo "🐳 更新Docker容器并测试结果文件访问"
echo "=========================================="

# 进入项目目录
cd "$(dirname "$0")"

echo ""
echo "步骤 1/3: 重新构建Docker镜像（应用最新代码）..."
echo "--------------------------------------------"
docker-compose build app

if [ $? -ne 0 ]; then
    echo "❌ Docker构建失败!"
    exit 1
fi

echo ""
echo "步骤 2/3: 重启应用容器..."
echo "--------------------------------------------"
docker-compose restart app

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 5

# 检查服务状态
echo ""
echo "📊 容器状态:"
docker-compose ps

echo ""
echo "步骤 3/3: 运行测试脚本..."
echo "--------------------------------------------"
python3 test_docker_results.py

echo ""
echo "=========================================="
echo "✅ 完成!"
echo ""
echo "💡 如果测试成功，现在可以在浏览器中测试:"
echo "   1. 打开: http://localhost:8000"
echo "   2. 点击已完成的任务"
echo "   3. 点击「查看结果」按钮"

