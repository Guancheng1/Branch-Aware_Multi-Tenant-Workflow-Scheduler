"""
InstanSeg集成服务 - 用于大图像分割
"""
import os
import asyncio
import numpy as np
import cv2
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import logging
import json
from datetime import datetime

# 设置OpenSlide库路径（macOS）
if 'DYLD_LIBRARY_PATH' not in os.environ:
    os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib'

INSTANSEG_IMPORT_ERROR = None

try:
    import torch
    from instanseg import InstanSeg
    INSTANSEG_AVAILABLE = True
    print("✅ InstanSeg导入成功!")
except ImportError as e:
    INSTANSEG_AVAILABLE = False
    INSTANSEG_IMPORT_ERROR = str(e)
    print(f"⚠️ InstanSeg导入失败: {e}")
    logging.warning("InstanSeg not available, using mock implementation")

try:
    import openslide
    OPENSLIDE_AVAILABLE = True
except ImportError:
    OPENSLIDE_AVAILABLE = False
    logging.warning("OpenSlide not available, falling back to OpenCV")

from backend.core.config import settings

logger = logging.getLogger(__name__)


class InstanSegService:
    """InstanSeg服务 - 处理大图像分割（两阶段优化）"""
    
    def __init__(self):
        self.model = None
        self.device = torch.device(settings.DEVICE if INSTANSEG_AVAILABLE and torch.cuda.is_available() else "cpu")
        self.pixel_size = 1.0  # 默认pixel_size，会在加载WSI时更新
        self.current_level = 0  # 当前使用的level
        self.tissue_mask = None  # Stage 1: 低分辨率 tissue mask
        self.mask_level = 0  # mask 对应的 level
        self.seg_level = 0   # 分割使用的 level
        logger.info(f"InstanSegService initialized with device: {self.device}")
    
    async def initialize(self):
        """初始化模型"""
        if not INSTANSEG_AVAILABLE:
            detail = f"import error: {INSTANSEG_IMPORT_ERROR}" if INSTANSEG_IMPORT_ERROR else "unknown import error"
            logger.warning(
                "InstanSeg not available (%s). "
                "Ensure instanseg-torch[full] and its native dependencies are installed before starting the worker.",
                detail
            )
            return
        
        try:
            # 在后台线程加载模型
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model)
            logger.info("InstanSeg model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load InstanSeg model: {e}", exc_info=True)
            raise
    
    def _load_model(self):
        """加载InstanSeg模型（同步）"""
        if not INSTANSEG_AVAILABLE:
            return
        
        try:
            # 使用正确的API加载模型
            device_name = 'mps' if self.device.type == 'mps' else str(self.device)
            self.model = InstanSeg(
                settings.INSTANSEG_MODEL, 
                image_reader='tiffslide',
                verbosity=1
            )
            print(f"✅ [MODEL] InstanSeg模型 '{settings.INSTANSEG_MODEL}' 加载成功")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            # 使用备用模型
            try:
                self.model = InstanSeg(
                    "brightfield_nuclei",
                    image_reader='tiffslide', 
                    verbosity=1
                )
                print(f"✅ [MODEL] InstanSeg备用模型 'brightfield_nuclei' 加载成功")
            except Exception as e2:
                logger.error(f"Failed to load any model: {e2}")
                raise
    
    async def segment_large_image(
        self,
        image_path: str,
        output_dir: str,
        tile_size: int = None,
        overlap: int = None,
        progress_callback = None
    ) -> Dict:
        """
        两阶段分割大图像：
        Stage 1: 低分辨率生成 tissue mask（快速）
        Stage 2: 基于 mask 在高分辨率上选择性分割（精确）
        
        Args:
            image_path: 输入图像路径
            output_dir: 输出目录
            tile_size: 瓦片大小
            overlap: 重叠区域大小
            progress_callback: 进度回调函数 callback(processed, total, message)
            
        Returns:
            结果字典，包含分割信息
        """
        print(f"🖼️ [INSTANSEG] Starting TWO-STAGE segment_large_image for: {image_path}")
        
        tile_size = tile_size or settings.TILE_SIZE
        overlap = overlap or settings.TILE_OVERLAP
        print(f"⚙️ [INSTANSEG] tile_size={tile_size}, overlap={overlap}")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 [INSTANSEG] Output directory: {output_path}")
        
        import time
        start_time = time.time()
        
        # ====== Stage 1: 生成低分辨率 tissue mask ======
        print(f"\n🎯 [STAGE 1] Generating tissue mask at low resolution...")
        mask_start = time.time()
        
        # 加载低分辨率图像用于生成 mask
        mask_image, slide = await self._load_image_at_level(
            image_path, 
            level=settings.TISSUE_MASK_LEVEL
        )
        self.mask_level = settings.TISSUE_MASK_LEVEL
        
        # 生成 tissue mask
        loop = asyncio.get_event_loop()
        self.tissue_mask = await loop.run_in_executor(
            None,
            self._generate_tissue_mask_sync,
            mask_image
        )
        
        mask_time = time.time() - mask_start
        tissue_percentage = np.sum(self.tissue_mask > 0) / self.tissue_mask.size * 100
        print(f"✅ [STAGE 1] Tissue mask generated in {mask_time:.2f}s")
        print(f"📊 [STAGE 1] Tissue coverage: {tissue_percentage:.2f}%")
        
        # 保存 mask 可视化
        mask_path = output_path / "tissue_mask.png"
        await loop.run_in_executor(None, cv2.imwrite, str(mask_path), self.tissue_mask)
        
        # ====== Stage 2: 高分辨率细胞分割（仅在有组织的区域） ======
        print(f"\n🎯 [STAGE 2] High-resolution cell segmentation...")
        seg_start = time.time()
        
        # 加载高分辨率图像用于分割
        image, _ = await self._load_image_at_level(
            image_path,
            level=settings.CELL_SEG_LEVEL
        )
        self.seg_level = settings.CELL_SEG_LEVEL
        height, width = image.shape[:2]
        
        print(f"📐 [STAGE 2] Image loaded, size: {width}x{height}")
        logger.info(f"Processing image {image_path}, size: {width}x{height}")
        
        # 计算瓦片
        tiles = self._calculate_tiles(width, height, tile_size, overlap)
        total_tiles = len(tiles)
        
        print(f"🔢 [STAGE 2] Image divided into {total_tiles} tiles (before filtering)")
        
        # 基于 tissue mask 过滤 tiles
        filtered_tiles = []
        for tile_coord in tiles:
            if self._should_process_tile_by_mask(tile_coord, width, height):
                filtered_tiles.append(tile_coord)
        
        skipped_tiles = total_tiles - len(filtered_tiles)
        print(f"🚀 [OPTIMIZATION] Filtered out {skipped_tiles}/{total_tiles} tiles "
              f"({skipped_tiles/total_tiles*100:.1f}%) using tissue mask")
        print(f"🔢 [STAGE 2] Will process {len(filtered_tiles)} tiles with tissue")
        logger.info(f"Tile filtering: {total_tiles} → {len(filtered_tiles)} "
                   f"(speedup: {total_tiles/max(len(filtered_tiles), 1):.2f}x)")
        
        # 处理瓦片（批处理优化）
        all_masks = []
        all_labels = []
        processed = 0
        tiles_with_cells = 0
        tiles_skipped_density = 0
        
        # 准备批次
        batch_size = settings.BATCH_SIZE
        print(f"📦 [BATCH] Using batch size: {batch_size}")
        
        # 分批处理
        for batch_start in range(0, len(filtered_tiles), batch_size):
            batch_end = min(batch_start + batch_size, len(filtered_tiles))
            batch_tiles = filtered_tiles[batch_start:batch_end]
            
            if progress_callback:
                await progress_callback(
                    processed, 
                    len(filtered_tiles),
                    f"Processing batch {batch_start//batch_size + 1}/{(len(filtered_tiles) + batch_size - 1)//batch_size}"
                )
            
            print(f"\n📦 [BATCH] Processing batch {batch_start//batch_size + 1} "
                  f"(tiles {batch_start+1}-{batch_end}/{len(filtered_tiles)})")
            
            # 准备当前批次的瓦片
            current_batch = []
            for i, (x, y, w, h) in enumerate(batch_tiles):
                tile_idx = batch_start + i
                
                # 提取瓦片
                tile_image = image[y:y+h, x:x+w]
                
                # 快速密度检查（第二层过滤）
                if not self._should_process_tile_by_density(tile_image):
                    print(f"  ⏭️ [FILTER] Skipped tile {tile_idx+1} (low density)")
                    tiles_skipped_density += 1
                    processed += 1
                    continue
                
                # 添加到批次
                current_batch.append((tile_image, x, y, w, h))
            
            # 如果批次不为空，进行批量分割
            if current_batch:
                print(f"  🔬 [BATCH] Segmenting {len(current_batch)} tiles...")
                
                # 批量分割
                batch_masks, batch_labels = await self._segment_tiles_batch(current_batch)
                
                if batch_masks is not None and len(batch_masks) > 0:
                    all_masks.extend(batch_masks)
                    all_labels.extend(batch_labels)
                    tiles_with_cells += len(current_batch)
                    print(f"  ✅ [BATCH] Batch processed, found {len(batch_masks)} cells total")
                else:
                    print(f"  ✗ [BATCH] Batch returned no results")
                
                processed += len(current_batch)
            else:
                print(f"  ⏭️ [BATCH] Entire batch skipped due to low density")
        
        seg_time = time.time() - seg_start
        total_time = time.time() - start_time
        
        print(f"\n📊 [STATISTICS]")
        print(f"  Total tiles: {total_tiles}")
        print(f"  Filtered by mask: {skipped_tiles} ({skipped_tiles/total_tiles*100:.1f}%)")
        print(f"  Filtered by density: {tiles_skipped_density} ({tiles_skipped_density/max(len(filtered_tiles), 1)*100:.1f}%)")
        print(f"  Actually processed: {tiles_with_cells}")
        print(f"  Total cells found: {len(all_masks)}")
        print(f"  Stage 1 time: {mask_time:.2f}s")
        print(f"  Stage 2 time: {seg_time:.2f}s")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Theoretical speedup: {total_tiles/max(tiles_with_cells, 1):.2f}x")
        
        print(f"🧬 [INSTANSEG] All tiles processed. Total masks: {len(all_masks)}")
        
        # 合并结果
        if progress_callback:
            await progress_callback(
                len(filtered_tiles),
                len(filtered_tiles),
                "Merging results..."
            )
        
        print(f"🔄 [INSTANSEG] Merging results...")
        merged_results = await self._merge_results(
            all_masks, all_labels, width, height, overlap
        )
        print(f"✅ [INSTANSEG] Results merged. Total cells: {len(merged_results.get('masks', []))}")
        
        # 保存结果
        print(f"💾 [INSTANSEG] Saving results...")
        result_path = await self._save_results(
            merged_results, output_path, image_path
        )
        print(f"✅ [INSTANSEG] Results saved to: {result_path}")
        
        # 生成可视化
        print(f"🎨 [INSTANSEG] Generating visualization...")
        vis_path = await self._generate_visualization(
            image, merged_results, output_path
        )
        print(f"✅ [INSTANSEG] Visualization saved to: {vis_path}")
        
        if slide:
            slide.close()
        
        result = {
            "image_path": image_path,
            "width": width,
            "height": height,
            "total_cells": len(merged_results.get("masks", [])),
            "total_tiles": total_tiles,
            "filtered_tiles": skipped_tiles,
            "filtered_by_density": tiles_skipped_density,
            "processed_tiles": tiles_with_cells,
            "speedup": round(total_tiles/max(tiles_with_cells, 1), 2),
            "stage1_time": round(mask_time, 2),
            "stage2_time": round(seg_time, 2),
            "total_time": round(total_time, 2),
            "result_path": str(result_path),
            "visualization_path": str(vis_path),
            "mask_path": str(mask_path),
            "completed_at": datetime.now().isoformat()
        }
        
        print(f"🎉 [INSTANSEG] Two-stage segmentation complete! Result: {result}")
        return result
        
        # 保存结果
        print(f"💾 [INSTANSEG] Saving results...")
        result_path = await self._save_results(
            merged_results, output_path, image_path
        )
        print(f"✅ [INSTANSEG] Results saved to: {result_path}")
        
        # 生成可视化
        print(f"🎨 [INSTANSEG] Generating visualization...")
        vis_path = await self._generate_visualization(
            image, merged_results, output_path
        )
        print(f"✅ [INSTANSEG] Visualization saved to: {vis_path}")
        
        if slide:
            slide.close()
        
        result = {
            "image_path": image_path,
            "width": width,
            "height": height,
            "total_cells": len(merged_results.get("masks", [])),
            "total_tiles": total_tiles,
            "result_path": str(result_path),
            "visualization_path": str(vis_path),
            "completed_at": datetime.now().isoformat()
        }
        
        print(f"🎉 [INSTANSEG] Segmentation complete! Result: {result}")
        return result
    
    async def _load_image(self, image_path: str) -> Tuple[np.ndarray, Optional[any]]:
        """
        加载图像（支持WSI格式）- 使用默认 level 1
        
        Returns:
            (image_array, slide_object)
        """
        return await self._load_image_at_level(image_path, level=1)
    
    async def _load_image_at_level(
        self, 
        image_path: str, 
        level: int = 1
    ) -> Tuple[np.ndarray, Optional[any]]:
        """
        加载指定 level 的图像（支持WSI格式）
        
        Args:
            image_path: 图像路径
            level: WSI pyramid level (0=最高分辨率)
            
        Returns:
            (image_array, slide_object)
        """
        print(f"📂 [LOAD_IMAGE] Loading image from: {image_path} at level {level}")
        path = Path(image_path)
        
        print(f"🔍 [LOAD_IMAGE] File exists: {path.exists()}, suffix: {path.suffix}")
        
        # 对于WSI文件（.svs, .ndpi等），使用InstanSeg内置的tiffslide读取
        if path.suffix.lower() in ['.svs', '.ndpi', '.tif', '.tiff']:
            try:
                print(f"🔬 [LOAD_IMAGE] Using tiffslide to load WSI...")
                import tiffslide
                
                slide = tiffslide.TiffSlide(str(path))
                
                # 使用指定的 level
                level = min(level, len(slide.level_dimensions) - 1)
                self.current_level = level
                
                print(f"📊 [LOAD_IMAGE] TiffSlide loaded - level_count: {len(slide.level_dimensions)}")
                print(f"📏 [LOAD_IMAGE] All level dimensions: {slide.level_dimensions}")
                print(f"🎯 [LOAD_IMAGE] Using level: {level}, dimensions: {slide.level_dimensions[level]}")
                
                # 从slide metadata中获取真实的pixel_size（μm/pixel）
                try:
                    # 尝试从metadata中读取MPP (Microns Per Pixel)
                    mpp_x = float(slide.properties.get('tiffslide.mpp-x', 0.25))  # 默认0.25 μm/pixel (40x)
                    downsample = slide.level_downsamples[level]
                    self.pixel_size = mpp_x * downsample
                    
                    print(f"🔬 [LOAD_IMAGE] Metadata: mpp_x={mpp_x:.4f} μm/pixel, downsample={downsample:.2f}")
                    print(f"✅ [LOAD_IMAGE] Computed pixel_size={self.pixel_size:.4f} μm/pixel for level {level}")
                except Exception as e:
                    print(f"⚠️ [LOAD_IMAGE] Could not read MPP from metadata: {e}")
                    print(f"⚠️ [LOAD_IMAGE] Using default pixel_size=1.0 μm/pixel")
                    self.pixel_size = 1.0
                
                # 读取指定level的图像
                image = np.array(slide.read_region((0, 0), level, slide.level_dimensions[level]))
                
                # 转换颜色空间（如果需要）
                if image.shape[2] == 4:  # RGBA
                    image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
                elif image.shape[2] == 3 and image.dtype == np.uint8:
                    # 已经是RGB，不需要转换
                    pass
                
                print(f"✅ [LOAD_IMAGE] Image loaded via TiffSlide, shape: {image.shape}")
                return image, slide
                
            except Exception as e:
                print(f"⚠️ [LOAD_IMAGE] Failed to load with TiffSlide: {e}")
                logger.warning(f"Failed to load with TiffSlide: {e}")
                raise ValueError(f"Failed to load WSI file {image_path}: {e}")
        
        # 对于普通图像文件，使用OpenCV加载
        print(f"🖼️ [LOAD_IMAGE] Attempting to load with OpenCV...")
        loop = asyncio.get_event_loop()
        image = await loop.run_in_executor(None, cv2.imread, str(path))
        
        if image is None:
            print(f"❌ [LOAD_IMAGE] Failed to load image: {image_path}")
            raise ValueError(f"Failed to load image: {image_path}")
        
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        print(f"✅ [LOAD_IMAGE] Image loaded via OpenCV, shape: {image.shape}")
        return image, None
    
    def _calculate_tiles(
        self,
        width: int,
        height: int,
        tile_size: int,
        overlap: int
    ) -> List[Tuple[int, int, int, int]]:
        """
        计算瓦片坐标
        
        Returns:
            List of (x, y, w, h)
        """
        tiles = []
        stride = tile_size - overlap
        
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                w = min(tile_size, width - x)
                h = min(tile_size, height - y)
                tiles.append((x, y, w, h))
        
        return tiles
    
    def _should_process_tile_by_mask(
        self, 
        tile_coord: Tuple[int, int, int, int],
        image_width: int,
        image_height: int
    ) -> bool:
        """
        基于 tissue mask 判断是否应该处理该 tile（第一层过滤）
        
        Args:
            tile_coord: (x, y, w, h) 在分割 level 的坐标
            image_width: 分割 level 的图像宽度
            image_height: 分割 level 的图像高度
            
        Returns:
            是否应该处理该 tile
        """
        if self.tissue_mask is None:
            return True  # 如果没有 mask，处理所有 tile
        
        x, y, w, h = tile_coord
        
        # 计算从分割 level 到 mask level 的缩放比例
        # level 0 -> level 1: downsample ~2x
        # level 0 -> level 2: downsample ~4x
        # level 1 -> level 2: downsample ~2x
        downsample_factor = 2 ** (self.seg_level - self.mask_level)
        
        # 将 tile 坐标映射到 mask 坐标系
        mask_h, mask_w = self.tissue_mask.shape
        mask_x = int(x / downsample_factor)
        mask_y = int(y / downsample_factor)
        mask_w = int(w / downsample_factor)
        mask_h_tile = int(h / downsample_factor)
        
        # 确保坐标在 mask 范围内
        mask_x = max(0, min(mask_x, mask_w - 1))
        mask_y = max(0, min(mask_y, mask_h - 1))
        mask_x_end = min(mask_x + mask_w, mask_w)
        mask_y_end = min(mask_y + mask_h_tile, mask_h)
        
        if mask_x_end <= mask_x or mask_y_end <= mask_y:
            return False
        
        # 提取对应区域的 mask
        tile_mask_region = self.tissue_mask[mask_y:mask_y_end, mask_x:mask_x_end]
        
        # 计算组织覆盖率
        tissue_ratio = np.mean(tile_mask_region > 0)
        
        should_process = tissue_ratio >= settings.TISSUE_RATIO_THRESH
        
        if not should_process:
            print(f"  ⏭️ [FILTER-MASK] Skipping tile at ({x},{y}) - "
                  f"tissue_ratio={tissue_ratio:.3f} < {settings.TISSUE_RATIO_THRESH}")
        
        return should_process
    
    def _should_process_tile_by_density(self, tile_image: np.ndarray) -> bool:
        """
        基于前景密度判断是否应该处理该 tile（第二层过滤）
        在 tile 层面做 cheap 的密度检查
        
        Args:
            tile_image: RGB tile 图像
            
        Returns:
            是否应该处理该 tile
        """
        # 转灰度
        gray = cv2.cvtColor(tile_image, cv2.COLOR_RGB2GRAY)
        
        # Otsu 阈值
        _, tile_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # 计算前景比例
        fg_ratio = np.mean(tile_mask > 0)
        
        should_process = fg_ratio >= settings.FG_DENSITY_THRESH
        
        if not should_process:
            print(f"    ⏭️ [FILTER-DENSITY] Low density tile - "
                  f"fg_ratio={fg_ratio:.3f} < {settings.FG_DENSITY_THRESH}")
        
        return should_process
    
    async def _segment_tile(
        self,
        tile_image: np.ndarray,
        offset_x: int,
        offset_y: int
    ) -> Tuple[Optional[List], Optional[List]]:
        """
        分割单个瓦片
        
        Returns:
            (masks, labels)
        """
        if not INSTANSEG_AVAILABLE or self.model is None:
            error_msg = "InstanSeg not available or model not loaded"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        print(f"🔬 [SEGMENT] 使用真实InstanSeg分割瓦片 ({offset_x}, {offset_y})")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._segment_tile_sync,
                tile_image,
                offset_x,
                offset_y
            )
            return result
        except Exception as e:
            logger.error(f"Error segmenting tile at ({offset_x}, {offset_y}): {e}")
            print(f"❌ [SEGMENT] 瓦片分割失败 ({offset_x}, {offset_y}): {e}")
            raise
    
    def _segment_tile_sync(
        self,
        tile_image: np.ndarray,
        offset_x: int,
        offset_y: int
    ) -> Tuple[List, List]:
        """同步分割瓦片 - 使用真实的InstanSeg（优化版）"""
        print(f"  🔬 [INSTANSEG_REAL] 开始分割瓦片，尺寸: {tile_image.shape}")
        print(f"  📏 [INSTANSEG_REAL] 使用 pixel_size={self.pixel_size:.4f} μm/pixel")
        
        # 优化：使用 inference_mode 减少显存和计算开销
        with torch.inference_mode():
            # 使用从WSI metadata计算出的真实pixel_size
            labeled_output, image_tensor = self.model.eval_small_image(
                tile_image, 
                pixel_size=self.pixel_size
            )
        
        print(f"  ✅ [INSTANSEG_REAL] InstanSeg分割完成")
        print(f"  📊 [INSTANSEG_REAL] labeled_output type: {type(labeled_output)}, shape: {labeled_output.shape}")
        
        # 将Tensor转换为numpy数组
        if torch.is_tensor(labeled_output):
            labeled_output = labeled_output.cpu().numpy()
        
        # 如果是4D tensor (batch, channel, height, width)，取第一个batch和channel
        if len(labeled_output.shape) == 4:
            labeled_output = labeled_output[0, 0]  # 取第一个batch和channel
        elif len(labeled_output.shape) == 3:
            labeled_output = labeled_output[0]  # 取第一个channel
        
        print(f"  📊 [INSTANSEG_REAL] After conversion: shape: {labeled_output.shape}, unique labels: {len(np.unique(labeled_output))}")
        
        # 将labeled_output转换为轮廓/多边形
        masks = []
        labels = []
        
        # 获取所有唯一的标签（跳过背景0）
        unique_labels = np.unique(labeled_output)
        unique_labels = unique_labels[unique_labels > 0]
        
        filtered_count = 0
        for label_id in unique_labels:
            # 创建当前标签的二值mask
            binary_mask = (labeled_output == label_id).astype(np.uint8)
            
            # 查找轮廓
            contours, _ = cv2.findContours(
                binary_mask, 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                # 使用最大的轮廓
                contour = max(contours, key=cv2.contourArea)
                
                # 优化：最小面积过滤（去除噪声）
                area = cv2.contourArea(contour)
                if area < settings.MIN_CELL_AREA:
                    filtered_count += 1
                    continue
                
                if len(contour) >= 3:  # 至少需要3个点形成多边形
                    # 简化轮廓
                    epsilon = 0.01 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # 调整坐标偏移
                    polygon = approx.reshape(-1, 2).astype(float)
                    polygon[:, 0] += offset_x
                    polygon[:, 1] += offset_y
                    
                    masks.append(polygon)
                    labels.append(f"cell_{label_id}")
        
        if filtered_count > 0:
            print(f"  🧹 [OPTIMIZATION] Filtered {filtered_count} small objects "
                  f"(area < {settings.MIN_CELL_AREA})")
        
        print(f"  ✅ [INSTANSEG_REAL] 从labeled_output提取了 {len(masks)} 个细胞")
        return masks, labels
    
    async def _segment_tiles_batch(
        self,
        tile_batch: List[Tuple[np.ndarray, int, int, int, int]]
    ) -> Tuple[List, List]:
        """
        批量分割多个瓦片（优化版 - 充分利用GPU并行能力）
        
        Args:
            tile_batch: List of (tile_image, x, y, w, h)
            
        Returns:
            (all_masks, all_labels)
        """
        if not INSTANSEG_AVAILABLE or self.model is None:
            error_msg = "InstanSeg not available or model not loaded"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        if not tile_batch:
            return [], []
        
        print(f"🚀 [BATCH] Processing batch of {len(tile_batch)} tiles")
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._segment_tiles_batch_sync,
            tile_batch
        )
        return result
    
    def _segment_tiles_batch_sync(
        self,
        tile_batch: List[Tuple[np.ndarray, int, int, int, int]]
    ) -> Tuple[List, List]:
        """
        同步批量分割瓦片 - 使用真实的InstanSeg批处理
        """
        all_masks = []
        all_labels = []
        
        if not tile_batch:
            return all_masks, all_labels
        
        # 优化：使用 inference_mode 减少显存和计算开销
        with torch.inference_mode():
            # 批量处理每个瓦片
            print(f"  🔬 [BATCH] Processing {len(tile_batch)} tiles with InstanSeg")
            print(f"  📏 [BATCH] Using pixel_size={self.pixel_size:.4f} μm/pixel")
            
            for i, (tile_image, x, y, w, h) in enumerate(tile_batch):
                # 使用InstanSeg分割当前瓦片
                labeled_output, _ = self.model.eval_small_image(
                    tile_image, 
                    pixel_size=self.pixel_size
                )
                
                # 从输出中提取masks
                masks, labels = self._extract_masks_from_output(labeled_output, x, y)
                all_masks.extend(masks)
                all_labels.extend(labels)
            
            print(f"  ✅ [BATCH] Batch processing complete, found {len(all_masks)} cells")
        
        return all_masks, all_labels
    
    def _extract_masks_from_output(
        self,
        labeled_output,
        offset_x: int,
        offset_y: int
    ) -> Tuple[List, List]:
        """
        从InstanSeg输出中提取masks和labels
        """
        # 将Tensor转换为numpy数组
        if torch.is_tensor(labeled_output):
            labeled_output = labeled_output.cpu().numpy()
        
        # 处理维度
        if len(labeled_output.shape) == 4:
            labeled_output = labeled_output[0, 0]
        elif len(labeled_output.shape) == 3:
            labeled_output = labeled_output[0]
        
        masks = []
        labels = []
        
        # 获取所有唯一的标签（跳过背景0）
        unique_labels = np.unique(labeled_output)
        unique_labels = unique_labels[unique_labels > 0]
        
        filtered_count = 0
        for label_id in unique_labels:
            # 创建当前标签的二值mask
            binary_mask = (labeled_output == label_id).astype(np.uint8)
            
            # 查找轮廓
            contours, _ = cv2.findContours(
                binary_mask, 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                # 使用最大的轮廓
                contour = max(contours, key=cv2.contourArea)
                
                # 最小面积过滤
                area = cv2.contourArea(contour)
                if area < settings.MIN_CELL_AREA:
                    filtered_count += 1
                    continue
                
                if len(contour) >= 3:
                    # 简化轮廓
                    epsilon = 0.01 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # 调整坐标偏移
                    polygon = approx.reshape(-1, 2).astype(float)
                    polygon[:, 0] += offset_x
                    polygon[:, 1] += offset_y
                    
                    masks.append(polygon)
                    labels.append(f"cell_{label_id}")
        
        return masks, labels
    
    async def _merge_results(
        self,
        all_masks: List,
        all_labels: List,
        width: int,
        height: int,
        overlap: int
    ) -> Dict:
        """
        合并瓦片结果，处理重叠区域
        """
        # 简化版本：直接使用所有mask
        # 实际应用中应该处理重叠区域的重复检测
        
        # 去重：基于中心点距离
        unique_masks = []
        unique_labels = []
        
        for i, mask in enumerate(all_masks):
            # 计算mask中心
            center = np.mean(mask, axis=0)
            
            # 检查是否与已有mask重复
            is_duplicate = False
            for existing_mask in unique_masks:
                existing_center = np.mean(existing_mask, axis=0)
                distance = np.linalg.norm(center - existing_center)
                
                if distance < overlap / 2:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_masks.append(mask)
                unique_labels.append(all_labels[i] if i < len(all_labels) else f"cell_{i}")
        
        return {
            "masks": unique_masks,
            "labels": unique_labels,
            "image_width": width,
            "image_height": height
        }
    
    async def _save_results(
        self,
        results: Dict,
        output_dir: Path,
        image_path: str
    ) -> Path:
        """保存结果为JSON格式"""
        # 转换numpy数组为list以便JSON序列化
        serializable_results = {
            "image_path": image_path,
            "image_width": results["image_width"],
            "image_height": results["image_height"],
            "total_cells": len(results["masks"]),
            "cells": []
        }
        
        for i, (mask, label) in enumerate(zip(results["masks"], results["labels"])):
            # 计算边界框
            mask_array = np.array(mask)
            x_min, y_min = mask_array.min(axis=0)
            x_max, y_max = mask_array.max(axis=0)
            
            # 计算面积
            area = cv2.contourArea(mask_array.astype(np.float32))
            
            serializable_results["cells"].append({
                "id": i,
                "label": label,
                "polygon": mask_array.tolist(),
                "bbox": [float(x_min), float(y_min), float(x_max), float(y_max)],
                "area": float(area),
                "centroid": mask_array.mean(axis=0).tolist()
            })
        
        # 保存JSON
        output_file = output_dir / "segmentation_results.json"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: output_file.write_text(json.dumps(serializable_results, indent=2))
        )
        
        return output_file
    
    async def _generate_visualization(
        self,
        image: np.ndarray,
        results: Dict,
        output_dir: Path
    ) -> Path:
        """生成可视化图像"""
        vis_image = image.copy()
        
        # 绘制所有mask
        for mask in results["masks"]:
            mask_array = np.array(mask, dtype=np.int32)
            
            # 随机颜色
            color = tuple(np.random.randint(0, 255, 3).tolist())
            
            # 绘制轮廓
            cv2.polylines(vis_image, [mask_array], True, color, 2)
        
        # 保存
        output_file = output_dir / "visualization.jpg"
        loop = asyncio.get_event_loop()
        vis_bgr = cv2.cvtColor(vis_image, cv2.COLOR_RGB2BGR)
        await loop.run_in_executor(
            None,
            cv2.imwrite,
            str(output_file),
            vis_bgr
        )
        
        return output_file
    
    async def generate_tissue_mask(
        self,
        image_path: str,
        output_dir: str,
        progress_callback = None
    ) -> Dict:
        """
        生成组织掩码（用于跳过背景瓦片）
        
        Args:
            image_path: 输入图像路径
            output_dir: 输出目录
            progress_callback: 进度回调
            
        Returns:
            结果字典
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        if progress_callback:
            await progress_callback(0, 100, "Loading image...")
        
        # 加载图像
        image, slide = await self._load_image(image_path)
        
        if progress_callback:
            await progress_callback(50, 100, "Generating tissue mask...")
        
        # 生成组织掩码（简单的阈值方法）
        loop = asyncio.get_event_loop()
        mask = await loop.run_in_executor(
            None,
            self._generate_tissue_mask_sync,
            image
        )
        
        # 保存掩码
        mask_path = output_path / "tissue_mask.png"
        await loop.run_in_executor(
            None,
            cv2.imwrite,
            str(mask_path),
            mask
        )
        
        # 生成可视化
        vis_image = image.copy()
        vis_image[mask == 0] = vis_image[mask == 0] // 2  # 背景变暗
        vis_path = output_path / "tissue_mask_overlay.jpg"
        vis_bgr = cv2.cvtColor(vis_image, cv2.COLOR_RGB2BGR)
        await loop.run_in_executor(
            None,
            cv2.imwrite,
            str(vis_path),
            vis_bgr
        )
        
        if slide:
            slide.close()
        
        if progress_callback:
            await progress_callback(100, 100, "Completed")
        
        return {
            "image_path": image_path,
            "mask_path": str(mask_path),
            "visualization_path": str(vis_path),
            "result_path": str(mask_path),  # 添加 result_path 以便前端显示 View Results 按钮
            "tissue_area": int(np.sum(mask > 0)),
            "total_area": int(mask.size),
            "tissue_percentage": float(np.sum(mask > 0) / mask.size * 100),
            "completed_at": datetime.now().isoformat()
        }
    
    def _generate_tissue_mask_sync(self, image: np.ndarray) -> np.ndarray:
        """同步生成组织掩码"""
        # 转换为灰度
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        
        # Otsu阈值
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 形态学操作清理
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        return mask


# 全局服务实例
instanseg_service = InstanSegService()

