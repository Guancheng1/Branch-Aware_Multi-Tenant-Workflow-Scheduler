#!/bin/bash

# 应用开发模式配置（首次运行或修改docker-compose.yml后使用）
echo "🔧 应用开发模式配置..."
echo ""

echo "1️⃣ 停止现有容器..."
docker-compose down

echo ""
echo "2️⃣ 用新配置启动（源代码挂载 + 自动重载）..."
docker-compose up -d

echo ""
echo "3️⃣ 等待容器启动..."
sleep 3

echo ""
echo "✅ 开发模式已启用！"
echo ""
echo "📋 特性："
echo "  • 源代码已挂载（backend/, main.py）"
echo "  • 自动重载已启用（修改代码会自动重启）"
echo "  • 无需重新build镜像"
echo ""
echo "📊 查看日志: docker-compose logs -f app"
echo "🔄 手动重启: ./restart_docker.sh"
echo "⏹️  停止服务: docker-compose down"
echo ""

