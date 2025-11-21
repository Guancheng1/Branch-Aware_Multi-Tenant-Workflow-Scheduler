#!/bin/bash

# 快速启动脚本

echo "======================================"
echo "Branch-Aware Multi-Tenant Workflow Scheduler"
echo "======================================"
echo ""

# 检查Docker是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

echo "✅ Docker正在运行"
echo ""

# 检查docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose未安装"
    exit 1
fi

echo "✅ docker-compose已安装"
echo ""

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p uploads results logs
echo "✅ 目录创建完成"
echo ""

# 启动服务
echo "启动服务..."
docker-compose up -d

echo ""
echo "等待服务启动..."
sleep 10

# 检查服务状态
echo ""
echo "检查服务状态..."
docker-compose ps

echo ""
echo "======================================"
echo "服务已启动！"
echo "======================================"
echo ""
echo "访问地址："
echo "  - Web界面:    http://localhost:8000"
echo "  - API文档:    http://localhost:8000/docs"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana:    http://localhost:3000 (admin/admin)"
echo ""
echo "查看日志："
echo "  docker-compose logs -f app"
echo ""
echo "停止服务："
echo "  docker-compose down"
echo ""


