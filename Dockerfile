FROM python:3.10-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgl1 \
    libopencv-dev \
    libopenslide0 \
    libopenslide-dev \
    libgdal-dev \
    gdal-bin \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 升级pip
RUN pip install --no-cache-dir --upgrade pip

# 先安装核心依赖(按顺序避免冲突)
RUN pip install --no-cache-dir \
    torch>=2.0.0 \
    torchvision>=0.15.0 \
    numpy>=1.24.0

# 安装图像处理库
RUN pip install --no-cache-dir \
    opencv-python>=4.8.0 \
    scikit-image>=0.22.0 \
    Pillow>=10.0.0 \
    tiffslide>=2.4.0 \
    openslide-python==1.3.1

# 安装InstanSeg(跳过slideio等可选依赖)
RUN pip install --no-cache-dir --no-deps instanseg-torch

# 安装InstanSeg的必需依赖(手动指定,跳过slideio)
RUN pip install --no-cache-dir \
    einops \
    tqdm \
    matplotlib \
    geojson \
    tifffile \
    fastremap \
    connected-components-3d \
    rasterio \
    colorcet \
    palettable

# 安装其他应用依赖
RUN pip install --no-cache-dir \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    python-multipart==0.0.6 \
    websockets==12.0 \
    aiofiles==23.2.1 \
    aioredis==2.0.1 \
    redis==5.0.1 \
    pydantic==2.5.0 \
    pydantic-settings==2.1.0 \
    prometheus-client==0.19.0 \
    prometheus-fastapi-instrumentator==6.1.0 \
    sqlalchemy==2.0.23 \
    aiosqlite==0.19.0 \
    python-dotenv==1.0.0 \
    httpx==0.25.2 \
    requests

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p uploads results logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

