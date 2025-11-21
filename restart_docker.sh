#!/bin/bash

# 快速重启Docker容器脚本（开发模式）
echo "🔄 重启Docker容器..."

# 重启app容器
docker-compose restart app

echo "✅ 容器已重启！"
echo "📊 查看日志: docker-compose logs -f app"

