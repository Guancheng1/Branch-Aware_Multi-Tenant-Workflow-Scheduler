FROM python:3.10-slim

# Install system dependencies
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

# Set working directory
WORKDIR /app

# Copy dependency file
COPY requirements.txt .

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install core dependencies first (in order to avoid conflicts)
RUN pip install --no-cache-dir \
    torch>=2.0.0 \
    torchvision>=0.15.0 \
    numpy>=1.24.0

# Install image processing libraries
RUN pip install --no-cache-dir \
    opencv-python>=4.8.0 \
    scikit-image>=0.22.0 \
    Pillow>=10.0.0 \
    tiffslide>=2.4.0 \
    openslide-python==1.3.1

# Install InstanSeg (skip optional dependencies like slideio)
RUN pip install --no-cache-dir --no-deps instanseg-torch

# Install InstanSeg required dependencies (manually specified, skip slideio)
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

# Install other application dependencies
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

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads results logs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Startup command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

