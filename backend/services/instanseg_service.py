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
    """InstanSeg服务 - 处理大图像分割"""
    
    def __init__(self):
        self.model = None
        self.device = torch.device(settings.DEVICE if INSTANSEG_AVAILABLE and torch.cuda.is_available() else "cpu")
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
        分割大图像
        
        Args:
            image_path: 输入图像路径
            output_dir: 输出目录
            tile_size: 瓦片大小
            overlap: 重叠区域大小
            progress_callback: 进度回调函数 callback(processed, total, message)
            
        Returns:
            结果字典，包含分割信息
        """
        print(f"🖼️ [INSTANSEG] Starting segment_large_image for: {image_path}")
        
        tile_size = tile_size or settings.TILE_SIZE
        overlap = overlap or settings.TILE_OVERLAP
        print(f"⚙️ [INSTANSEG] tile_size={tile_size}, overlap={overlap}")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 [INSTANSEG] Output directory: {output_path}")
        
        # 读取图像
        if progress_callback:
            await progress_callback(0, 100, "Loading image...")
        
        print(f"📖 [INSTANSEG] Loading image from {image_path}")
        image, slide = await self._load_image(image_path)
        height, width = image.shape[:2]
        
        print(f"📐 [INSTANSEG] Image loaded, size: {width}x{height}")
        logger.info(f"Processing image {image_path}, size: {width}x{height}")
        
        # 计算瓦片
        tiles = self._calculate_tiles(width, height, tile_size, overlap)
        total_tiles = len(tiles)
        
        print(f"🔢 [INSTANSEG] Image divided into {total_tiles} tiles")
        logger.info(f"Image divided into {total_tiles} tiles")
        
        # 处理瓦片
        all_masks = []
        all_labels = []
        processed = 0
        
        for i, (x, y, w, h) in enumerate(tiles):
            if progress_callback:
                await progress_callback(
                    processed, total_tiles,
                    f"Processing tile {i+1}/{total_tiles}"
                )
            
            print(f"🧩 [INSTANSEG] Processing tile {i+1}/{total_tiles} at ({x},{y},{w},{h})")
            
            # 提取瓦片
            tile_image = image[y:y+h, x:x+w]
            
            # 分割瓦片
            masks, labels = await self._segment_tile(tile_image, x, y)
            
            if masks is not None:
                all_masks.extend(masks)
                all_labels.extend(labels)
                print(f"✓ [INSTANSEG] Tile {i+1} processed, found {len(masks)} cells")
            else:
                print(f"✗ [INSTANSEG] Tile {i+1} returned no results")
            
            processed += 1
        
        print(f"🧬 [INSTANSEG] All tiles processed. Total masks: {len(all_masks)}")
        
        # 合并结果
        if progress_callback:
            await progress_callback(
                total_tiles, total_tiles,
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
            "result_path": str(result_path),
            "visualization_path": str(vis_path),
            "completed_at": datetime.now().isoformat()
        }
        
        print(f"🎉 [INSTANSEG] Segmentation complete! Result: {result}")
        return result
    
    async def _load_image(self, image_path: str) -> Tuple[np.ndarray, Optional[any]]:
        """
        加载图像（支持WSI格式）
        
        Returns:
            (image_array, slide_object)
        """
        print(f"📂 [LOAD_IMAGE] Loading image from: {image_path}")
        path = Path(image_path)
        
        print(f"🔍 [LOAD_IMAGE] File exists: {path.exists()}, suffix: {path.suffix}")
        
        # 对于WSI文件（.svs, .ndpi等），使用InstanSeg内置的tiffslide读取
        if path.suffix.lower() in ['.svs', '.ndpi', '.tif', '.tiff']:
            try:
                print(f"🔬 [LOAD_IMAGE] Using tiffslide to load WSI...")
                import tiffslide
                
                slide = tiffslide.TiffSlide(str(path))
                # 获取缩略图或指定级别
                level = min(2, len(slide.level_dimensions) - 1)  # 使用中等分辨率
                print(f"📊 [LOAD_IMAGE] TiffSlide loaded - level_count: {len(slide.level_dimensions)}, using level: {level}")
                print(f"📏 [LOAD_IMAGE] Level dimensions: {slide.level_dimensions[level]}")
                
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
            # Mock implementation
            print(f"⚠️ [SEGMENT] 使用Mock方法分割瓦片 ({offset_x}, {offset_y})")
            await asyncio.sleep(0.1)  # 模拟处理时间
            return self._mock_segment(tile_image, offset_x, offset_y)
        
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
            return None, None
    
    def _segment_tile_sync(
        self,
        tile_image: np.ndarray,
        offset_x: int,
        offset_y: int
    ) -> Tuple[List, List]:
        """同步分割瓦片 - 使用真实的InstanSeg"""
        print(f"  🔬 [INSTANSEG_REAL] 开始分割瓦片，尺寸: {tile_image.shape}")
        
        # 使用InstanSeg的eval_small_image方法
        # pixel_size参数对于HE染色图像可以设为1.0
        labeled_output, image_tensor = self.model.eval_small_image(
            tile_image, 
            pixel_size=1.0
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
        
        print(f"  ✅ [INSTANSEG_REAL] 从labeled_output提取了 {len(masks)} 个细胞")
        return masks, labels
    
    def _mock_segment(
        self,
        tile_image: np.ndarray,
        offset_x: int,
        offset_y: int
    ) -> Tuple[List, List]:
        """Mock分割（用于测试）"""
        # 生成一些假的细胞mask
        h, w = tile_image.shape[:2]
        num_cells = np.random.randint(5, 20)
        
        masks = []
        labels = []
        
        for i in range(num_cells):
            # 随机生成圆形mask
            cx = np.random.randint(50, w - 50) + offset_x
            cy = np.random.randint(50, h - 50) + offset_y
            radius = np.random.randint(10, 30)
            
            # 生成多边形近似
            num_points = 20
            angles = np.linspace(0, 2*np.pi, num_points)
            polygon = np.array([
                [cx + radius * np.cos(a), cy + radius * np.sin(a)]
                for a in angles
            ])
            
            masks.append(polygon)
            labels.append(f"cell_{i}")
        
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

