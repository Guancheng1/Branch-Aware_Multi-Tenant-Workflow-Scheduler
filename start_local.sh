#!/bin/bash

# 本地启动脚本（不使用Docker）

echo "======================================"
echo "Branch-Aware Multi-Tenant Workflow Scheduler"
echo "本地启动模式"
echo "======================================"
echo ""

# 设置OpenSlide库路径（macOS）
export DYLD_LIBRARY_PATH=/opt/homebrew/lib:$DYLD_LIBRARY_PATH

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p uploads results logs
echo "✅ 目录创建完成"
echo ""

# 检查Python依赖
echo "检查依赖..."
python -c "import fastapi" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️ 缺少依赖，正在安装..."
    python -m pip install --user -q fastapi uvicorn pydantic pydantic-settings opencv-python numpy pillow openslide-python
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已安装"
fi
echo ""

# 启动服务
echo "启动服务..."
echo ""
echo "======================================"
echo "服务启动中..."
echo "======================================"
echo ""
echo "访问地址："
echo "  - Web界面:    http://localhost:8000"
echo "  - API文档:    http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 运行应用
python main.py

