#!/bin/bash

# 停止服务脚本

echo "======================================"
echo "停止 Workflow Scheduler 服务"
echo "======================================"
echo ""

docker-compose down

echo ""
echo "✅ 服务已停止"
echo ""


