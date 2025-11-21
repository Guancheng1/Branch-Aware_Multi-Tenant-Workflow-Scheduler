# 快速调优指南

## 🚨 如果优化效果不明显怎么办？

### 问题诊断

如果你看到：
- ❌ `Filtered out 0/130 tiles (0.0%)` - 第一层过滤没有效果
- ❌ 处理速度仍然很慢
- ❌ tile 数量没有明显减少

### 原因分析

**1. 图像组织覆盖率很高**
   - 如果组织覆盖率 > 80%（如 `Tissue coverage: 84.79%`）
   - 说明你的图像几乎全是组织，很少有纯背景
   - 第一层 mask 过滤效果有限（它主要过滤纯背景）

**2. 使用了错误的 tile 大小**
   - 如果看到 `1024x1024` 的 tile，说明配置没生效
   - 应该使用 `512x512`

**3. 阈值设置不合理**
   - 默认阈值可能不适合你的图像类型

---

## ⚡ 立即优化方案

### 方案 1: 调整过滤阈值（针对组织密集图像）

编辑 `backend/core/config.py`:

```python
# 对于组织密集的图像（如肿瘤切片）
TISSUE_RATIO_THRESH: float = 0.05   # 降低（从 0.1 → 0.05）
FG_DENSITY_THRESH: float = 0.15     # 提高（从 0.05 → 0.15）
MIN_CELL_AREA: float = 30.0         # 提高（从 20 → 30）
```

**效果**: 第二层密度过滤会更激进，过滤掉更多稀疏区域

### 方案 2: 强制使用正确的 tile 大小

#### 前端调用
确保前端传入正确参数：

```javascript
// 在 static/app.js 中
const jobData = {
    job_type: "cell_segmentation",
    parameters: {
        tile_size: 512,   // ← 使用 512 而不是 1024
        overlap: 64       // ← 使用 64 而不是 128
    },
    image_path: imagePath
};
```

#### API 调用
```bash
curl -X POST "http://localhost:8000/api/v1/jobs" \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "cell_segmentation",
    "parameters": {
      "tile_size": 512,
      "overlap": 64
    },
    "image_path": "/path/to/image.svs"
  }'
```

### 方案 3: 使用更低的分辨率（牺牲一点精度换速度）

```python
# 在 backend/core/config.py
CELL_SEG_LEVEL: int = 2  # 从 1 降到 2（分辨率降低 1 级）
```

**效果**: tile 数量可能减少 4 倍（2^2）

---

## 🔍 验证优化是否生效

### 1. 查看日志

重新运行后，应该看到：

```bash
# 好的迹象 ✅
🚀 [OPTIMIZATION] Filtered out 45/130 tiles (34.6%) using tissue mask
⏭️ [FILTER-DENSITY] Low density tile - fg_ratio=0.085 < 0.15
⏭️ [OPTIMIZATION] Skipped tile X (low density)

📊 [STATISTICS]
  Total tiles: 130
  Filtered by mask: 45 (34.6%)        # ← 应该 > 20%
  Filtered by density: 30 (35.3%)     # ← 应该 > 20%
  Actually processed: 55              # ← 大幅减少
  Speedup: 2.36x                      # ← 应该 > 2x
```

### 2. 检查 tile 大小

日志中应该看到：
```
⚙️ [INSTANSEG] tile_size=512, overlap=64
```

而不是：
```
⚙️ [INSTANSEG] tile_size=1024, overlap=128
```

---

## 📊 不同图像类型的推荐配置

### 1. 组织密集图像（如肿瘤切片）

```python
TISSUE_RATIO_THRESH = 0.05   # 低阈值
FG_DENSITY_THRESH = 0.15     # 高阈值（过滤稀疏区域）
MIN_CELL_AREA = 30.0
TILE_SIZE = 512
```

**特点**: 
- 组织覆盖率 > 70%
- 第一层过滤效果有限
- 依赖第二层密度过滤

### 2. 稀疏组织图像（如活检样本）

```python
TISSUE_RATIO_THRESH = 0.03   # 非常低
FG_DENSITY_THRESH = 0.05     # 低阈值（避免漏检）
MIN_CELL_AREA = 15.0
TILE_SIZE = 512
```

**特点**:
- 组织覆盖率 < 30%
- 第一层过滤效果显著
- 需要降低阈值避免漏检

### 3. 背景很多的图像（如全视野扫描）

```python
TISSUE_RATIO_THRESH = 0.08   # 中等
FG_DENSITY_THRESH = 0.08     # 中等
MIN_CELL_AREA = 20.0
TILE_SIZE = 512
```

**特点**:
- 组织覆盖率 30-70%
- 两层过滤都有效
- 最佳优化场景

---

## 🔧 调试技巧

### 1. 可视化 tissue mask

查看生成的 mask：
```bash
# 在输出目录找到
results/user-001/{job_id}/tissue_mask.png
results/user-001/{job_id}/tissue_mask_overlay.jpg
```

如果 mask 不准确，调整阈值。

### 2. 监控实时日志

```bash
docker-compose logs -f app | grep -E "STAGE|OPTIMIZATION|FILTER"
```

### 3. 临时调整配置（无需重启）

直接编辑容器内的配置：
```bash
docker exec -it workflow-app vi /app/backend/core/config.py
# 修改后，需要重启容器
docker-compose restart app
```

---

## 🚀 快速重启 Docker

```bash
# 停止
docker-compose down

# 重新构建（如果改了代码）
docker-compose build --no-cache app

# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f app
```

---

## 💡 最终建议

### 如果你的图像组织覆盖率很高（> 80%）

两阶段优化的**主要收益来自第二层密度过滤**，而不是第一层 mask 过滤。

**调整策略**:
1. ✅ 提高 `FG_DENSITY_THRESH` 到 0.15-0.20
2. ✅ 使用 512×512 tile（而不是 1024×1024）
3. ✅ 提高 `MIN_CELL_AREA` 减少噪声
4. ✅ 考虑使用 Level 2（如果精度要求不是很高）

**预期效果**:
- 过滤率：40-60%
- 加速比：1.5-2.5x（不是 5x，因为背景少）

### 如果你的图像背景很多（< 50% 组织）

**你很幸运**！两层过滤都会非常有效：
- 过滤率：70-90%
- 加速比：3-10x

---

**最后更新**: 2025-11-21  
**快速问题排查**: 如果还有问题，查看 `OPTIMIZATION_GUIDE_CN.md` 的"故障排查"部分

