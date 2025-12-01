"""
InstanSeg integration service - for large image segmentation
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

# Set OpenSlide library path (macOS)
if 'DYLD_LIBRARY_PATH' not in os.environ:
    os.environ['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib'

INSTANSEG_IMPORT_ERROR = None

try:
    import torch
    from instanseg import InstanSeg
    INSTANSEG_AVAILABLE = True
    print("✅ InstanSeg imported successfully!")
except ImportError as e:
    INSTANSEG_AVAILABLE = False
    INSTANSEG_IMPORT_ERROR = str(e)
    print(f"⚠️ InstanSeg import failed: {e}")
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
    """InstanSeg service - handles large image segmentation (two-stage optimization)"""
    
    def __init__(self):
        self.model = None
        self.device = torch.device(settings.DEVICE if INSTANSEG_AVAILABLE and torch.cuda.is_available() else "cpu")
        self.pixel_size = 1.0  # Default pixel_size, will be updated when loading WSI
        self.current_level = 0  # Currently used level
        self.tissue_mask = None  # Stage 1: Low resolution tissue mask
        self.mask_level = 0  # Level corresponding to mask
        self.seg_level = 0   # Level used for segmentation
        logger.info(f"InstanSegService initialized with device: {self.device}")
    
    async def initialize(self):
        """Initialize model"""
        if not INSTANSEG_AVAILABLE:
            detail = f"import error: {INSTANSEG_IMPORT_ERROR}" if INSTANSEG_IMPORT_ERROR else "unknown import error"
            logger.warning(
                "InstanSeg not available (%s). "
                "Ensure instanseg-torch[full] and its native dependencies are installed before starting the worker.",
                detail
            )
            return
        
        try:
            # Load model in background thread
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model)
            logger.info("InstanSeg model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load InstanSeg model: {e}", exc_info=True)
            raise
    
    def _load_model(self):
        """Load InstanSeg model (synchronous)"""
        if not INSTANSEG_AVAILABLE:
            return
        
        try:
            # Load model using correct API
            device_name = 'mps' if self.device.type == 'mps' else str(self.device)
            self.model = InstanSeg(
                settings.INSTANSEG_MODEL, 
                image_reader='tiffslide',
                verbosity=1
            )
            print(f"✅ [MODEL] InstanSeg model '{settings.INSTANSEG_MODEL}' loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            # Use fallback model
            try:
                self.model = InstanSeg(
                    "brightfield_nuclei",
                    image_reader='tiffslide', 
                    verbosity=1
                )
                print(f"✅ [MODEL] InstanSeg fallback model 'brightfield_nuclei' loaded successfully")
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
        Two-stage large image segmentation:
        Stage 1: Generate tissue mask at low resolution (fast)
        Stage 2: Selective segmentation at high resolution based on mask (precise)
        
        Args:
            image_path: Input image path
            output_dir: Output directory
            tile_size: Tile size
            overlap: Overlap area size
            progress_callback: Progress callback function callback(processed, total, message)
            
        Returns:
            Result dictionary containing segmentation information
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
        
        # ====== Stage 1: Generate low resolution tissue mask ======
        print(f"\n🎯 [STAGE 1] Generating tissue mask at low resolution...")
        mask_start = time.time()
        
        # Load low resolution image for mask generation
        mask_image, slide = await self._load_image_at_level(
            image_path, 
            level=settings.TISSUE_MASK_LEVEL
        )
        self.mask_level = settings.TISSUE_MASK_LEVEL
        
        # Generate tissue mask
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
        
        # Save mask visualization
        mask_path = output_path / "tissue_mask.png"
        await loop.run_in_executor(None, cv2.imwrite, str(mask_path), self.tissue_mask)
        
        # ====== Stage 2: High-resolution cell segmentation (only in tissue regions) ======
        print(f"\n🎯 [STAGE 2] High-resolution cell segmentation...")
        seg_start = time.time()
        
        # Load high resolution image for segmentation
        image, _ = await self._load_image_at_level(
            image_path,
            level=settings.CELL_SEG_LEVEL
        )
        self.seg_level = settings.CELL_SEG_LEVEL
        height, width = image.shape[:2]
        
        print(f"📐 [STAGE 2] Image loaded, size: {width}x{height}")
        logger.info(f"Processing image {image_path}, size: {width}x{height}")
        
        # Calculate tiles
        tiles = self._calculate_tiles(width, height, tile_size, overlap)
        total_tiles = len(tiles)
        
        print(f"🔢 [STAGE 2] Image divided into {total_tiles} tiles (before filtering)")
        
        # Filter tiles based on tissue mask
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
        
        # Process tiles (batch processing optimization)
        all_masks = []
        all_labels = []
        processed = 0
        tiles_with_cells = 0
        tiles_skipped_density = 0
        
        # Prepare batches
        batch_size = settings.BATCH_SIZE
        print(f"📦 [BATCH] Using batch size: {batch_size}")
        
        # Process in batches
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
            
            # Prepare current batch tiles
            current_batch = []
            for i, (x, y, w, h) in enumerate(batch_tiles):
                tile_idx = batch_start + i
                
                # Extract tile
                tile_image = image[y:y+h, x:x+w]
                
                # Quick density check (second layer filtering)
                if not self._should_process_tile_by_density(tile_image):
                    print(f"  ⏭️ [FILTER] Skipped tile {tile_idx+1} (low density)")
                    tiles_skipped_density += 1
                    processed += 1
                    continue
                
                # Add to batch
                current_batch.append((tile_image, x, y, w, h))
            
            # If batch is not empty, perform batch segmentation
            if current_batch:
                print(f"  🔬 [BATCH] Segmenting {len(current_batch)} tiles...")
                
                # Batch segmentation
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
        
        # Merge results
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
        
        # Save results
        print(f"💾 [INSTANSEG] Saving results...")
        result_path = await self._save_results(
            merged_results, output_path, image_path
        )
        print(f"✅ [INSTANSEG] Results saved to: {result_path}")
        
        # Generate visualization
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
        
        # Save results
        print(f"💾 [INSTANSEG] Saving results...")
        result_path = await self._save_results(
            merged_results, output_path, image_path
        )
        print(f"✅ [INSTANSEG] Results saved to: {result_path}")
        
        # Generate visualization
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
        Load image (supports WSI format) - uses default level 1
        
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
        Load image at specified level (supports WSI format)
        
        Args:
            image_path: Image path
            level: WSI pyramid level (0=highest resolution)
            
        Returns:
            (image_array, slide_object)
        """
        print(f"📂 [LOAD_IMAGE] Loading image from: {image_path} at level {level}")
        path = Path(image_path)
        
        print(f"🔍 [LOAD_IMAGE] File exists: {path.exists()}, suffix: {path.suffix}")
        
        # For WSI files (.svs, .ndpi, etc.), use InstanSeg's built-in tiffslide reader
        if path.suffix.lower() in ['.svs', '.ndpi', '.tif', '.tiff']:
            try:
                print(f"🔬 [LOAD_IMAGE] Using tiffslide to load WSI...")
                import tiffslide
                
                slide = tiffslide.TiffSlide(str(path))
                
                # Use specified level
                level = min(level, len(slide.level_dimensions) - 1)
                self.current_level = level
                
                print(f"📊 [LOAD_IMAGE] TiffSlide loaded - level_count: {len(slide.level_dimensions)}")
                print(f"📏 [LOAD_IMAGE] All level dimensions: {slide.level_dimensions}")
                print(f"🎯 [LOAD_IMAGE] Using level: {level}, dimensions: {slide.level_dimensions[level]}")
                
                # Get real pixel_size from slide metadata (μm/pixel)
                try:
                    # Try to read MPP (Microns Per Pixel) from metadata
                    mpp_x = float(slide.properties.get('tiffslide.mpp-x', 0.25))  # Default 0.25 μm/pixel (40x)
                    downsample = slide.level_downsamples[level]
                    self.pixel_size = mpp_x * downsample
                    
                    print(f"🔬 [LOAD_IMAGE] Metadata: mpp_x={mpp_x:.4f} μm/pixel, downsample={downsample:.2f}")
                    print(f"✅ [LOAD_IMAGE] Computed pixel_size={self.pixel_size:.4f} μm/pixel for level {level}")
                except Exception as e:
                    print(f"⚠️ [LOAD_IMAGE] Could not read MPP from metadata: {e}")
                    print(f"⚠️ [LOAD_IMAGE] Using default pixel_size=1.0 μm/pixel")
                    self.pixel_size = 1.0
                
                # Read image at specified level
                image = np.array(slide.read_region((0, 0), level, slide.level_dimensions[level]))
                
                # Convert color space (if needed)
                if image.shape[2] == 4:  # RGBA
                    image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
                elif image.shape[2] == 3 and image.dtype == np.uint8:
                    # Already RGB, no conversion needed
                    pass
                
                print(f"✅ [LOAD_IMAGE] Image loaded via TiffSlide, shape: {image.shape}")
                return image, slide
                
            except Exception as e:
                print(f"⚠️ [LOAD_IMAGE] Failed to load with TiffSlide: {e}")
                logger.warning(f"Failed to load with TiffSlide: {e}")
                raise ValueError(f"Failed to load WSI file {image_path}: {e}")
        
        # For regular image files, use OpenCV
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
        Calculate tile coordinates
        
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
        Determine whether tile should be processed based on tissue mask (first layer filtering)
        
        Args:
            tile_coord: (x, y, w, h) coordinates at segmentation level
            image_width: Image width at segmentation level
            image_height: Image height at segmentation level
            
        Returns:
            Whether the tile should be processed
        """
        if self.tissue_mask is None:
            return True  # If no mask, process all tiles
        
        x, y, w, h = tile_coord
        
        # Calculate scale ratio from segmentation level to mask level
        # level 0 -> level 1: downsample ~2x
        # level 0 -> level 2: downsample ~4x
        # level 1 -> level 2: downsample ~2x
        downsample_factor = 2 ** (self.seg_level - self.mask_level)
        
        # Map tile coordinates to mask coordinate system
        mask_h, mask_w = self.tissue_mask.shape
        mask_x = int(x / downsample_factor)
        mask_y = int(y / downsample_factor)
        mask_w = int(w / downsample_factor)
        mask_h_tile = int(h / downsample_factor)
        
        # Ensure coordinates are within mask bounds
        mask_x = max(0, min(mask_x, mask_w - 1))
        mask_y = max(0, min(mask_y, mask_h - 1))
        mask_x_end = min(mask_x + mask_w, mask_w)
        mask_y_end = min(mask_y + mask_h_tile, mask_h)
        
        if mask_x_end <= mask_x or mask_y_end <= mask_y:
            return False
        
        # Extract corresponding mask region
        tile_mask_region = self.tissue_mask[mask_y:mask_y_end, mask_x:mask_x_end]
        
        # Calculate tissue coverage ratio
        tissue_ratio = np.mean(tile_mask_region > 0)
        
        should_process = tissue_ratio >= settings.TISSUE_RATIO_THRESH
        
        if not should_process:
            print(f"  ⏭️ [FILTER-MASK] Skipping tile at ({x},{y}) - "
                  f"tissue_ratio={tissue_ratio:.3f} < {settings.TISSUE_RATIO_THRESH}")
        
        return should_process
    
    def _should_process_tile_by_density(self, tile_image: np.ndarray) -> bool:
        """
        Determine whether tile should be processed based on foreground density (second layer filtering)
        Do cheap density check at tile level
        
        Args:
            tile_image: RGB tile image
            
        Returns:
            Whether the tile should be processed
        """
        # Convert to grayscale
        gray = cv2.cvtColor(tile_image, cv2.COLOR_RGB2GRAY)
        
        # Otsu threshold
        _, tile_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Calculate foreground ratio
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
        Segment a single tile
        
        Returns:
            (masks, labels)
        """
        if not INSTANSEG_AVAILABLE or self.model is None:
            error_msg = "InstanSeg not available or model not loaded"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        print(f"🔬 [SEGMENT] Segmenting tile with real InstanSeg ({offset_x}, {offset_y})")
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
            print(f"❌ [SEGMENT] Tile segmentation failed ({offset_x}, {offset_y}): {e}")
            raise
    
    def _segment_tile_sync(
        self,
        tile_image: np.ndarray,
        offset_x: int,
        offset_y: int
    ) -> Tuple[List, List]:
        """Synchronously segment tile - using real InstanSeg (optimized version)"""
        print(f"  🔬 [INSTANSEG_REAL] Starting tile segmentation, size: {tile_image.shape}")
        print(f"  📏 [INSTANSEG_REAL] Using pixel_size={self.pixel_size:.4f} μm/pixel")
        
        # Optimization: use inference_mode to reduce memory and computation overhead
        with torch.inference_mode():
            # Use real pixel_size computed from WSI metadata
            labeled_output, image_tensor = self.model.eval_small_image(
                tile_image, 
                pixel_size=self.pixel_size
            )
        
        print(f"  ✅ [INSTANSEG_REAL] InstanSeg segmentation complete")
        print(f"  📊 [INSTANSEG_REAL] labeled_output type: {type(labeled_output)}, shape: {labeled_output.shape}")
        
        # Convert Tensor to numpy array
        if torch.is_tensor(labeled_output):
            labeled_output = labeled_output.cpu().numpy()
        
        # If 4D tensor (batch, channel, height, width), take first batch and channel
        if len(labeled_output.shape) == 4:
            labeled_output = labeled_output[0, 0]  # Take first batch and channel
        elif len(labeled_output.shape) == 3:
            labeled_output = labeled_output[0]  # Take first channel
        
        print(f"  📊 [INSTANSEG_REAL] After conversion: shape: {labeled_output.shape}, unique labels: {len(np.unique(labeled_output))}")
        
        # Convert labeled_output to contours/polygons
        masks = []
        labels = []
        
        # Get all unique labels (skip background 0)
        unique_labels = np.unique(labeled_output)
        unique_labels = unique_labels[unique_labels > 0]
        
        filtered_count = 0
        for label_id in unique_labels:
            # Create binary mask for current label
            binary_mask = (labeled_output == label_id).astype(np.uint8)
            
            # Find contours
            contours, _ = cv2.findContours(
                binary_mask, 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                # Use the largest contour
                contour = max(contours, key=cv2.contourArea)
                
                # Optimization: minimum area filtering (remove noise)
                area = cv2.contourArea(contour)
                if area < settings.MIN_CELL_AREA:
                    filtered_count += 1
                    continue
                
                if len(contour) >= 3:  # Need at least 3 points to form a polygon
                    # Simplify contour
                    epsilon = 0.01 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # Adjust coordinate offset
                    polygon = approx.reshape(-1, 2).astype(float)
                    polygon[:, 0] += offset_x
                    polygon[:, 1] += offset_y
                    
                    masks.append(polygon)
                    labels.append(f"cell_{label_id}")
        
        if filtered_count > 0:
            print(f"  🧹 [OPTIMIZATION] Filtered {filtered_count} small objects "
                  f"(area < {settings.MIN_CELL_AREA})")
        
        print(f"  ✅ [INSTANSEG_REAL] Extracted {len(masks)} cells from labeled_output")
        return masks, labels
    
    async def _segment_tiles_batch(
        self,
        tile_batch: List[Tuple[np.ndarray, int, int, int, int]]
    ) -> Tuple[List, List]:
        """
        Batch segment multiple tiles (optimized - fully utilize GPU parallel capability)
        
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
        Synchronously batch segment tiles - using real InstanSeg batch processing
        """
        all_masks = []
        all_labels = []
        
        if not tile_batch:
            return all_masks, all_labels
        
        # Optimization: use inference_mode to reduce memory and computation overhead
        with torch.inference_mode():
            # Process each tile in batch
            print(f"  🔬 [BATCH] Processing {len(tile_batch)} tiles with InstanSeg")
            print(f"  📏 [BATCH] Using pixel_size={self.pixel_size:.4f} μm/pixel")
            
            for i, (tile_image, x, y, w, h) in enumerate(tile_batch):
                # Segment current tile using InstanSeg
                labeled_output, _ = self.model.eval_small_image(
                    tile_image, 
                    pixel_size=self.pixel_size
                )
                
                # Extract masks from output
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
        Extract masks and labels from InstanSeg output
        """
        # Convert Tensor to numpy array
        if torch.is_tensor(labeled_output):
            labeled_output = labeled_output.cpu().numpy()
        
        # Process dimensions
        if len(labeled_output.shape) == 4:
            labeled_output = labeled_output[0, 0]
        elif len(labeled_output.shape) == 3:
            labeled_output = labeled_output[0]
        
        masks = []
        labels = []
        
        # Get all unique labels (skip background 0)
        unique_labels = np.unique(labeled_output)
        unique_labels = unique_labels[unique_labels > 0]
        
        filtered_count = 0
        for label_id in unique_labels:
            # Create binary mask for current label
            binary_mask = (labeled_output == label_id).astype(np.uint8)
            
            # Find contours
            contours, _ = cv2.findContours(
                binary_mask, 
                cv2.RETR_EXTERNAL, 
                cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                # Use the largest contour
                contour = max(contours, key=cv2.contourArea)
                
                # Minimum area filtering
                area = cv2.contourArea(contour)
                if area < settings.MIN_CELL_AREA:
                    filtered_count += 1
                    continue
                
                if len(contour) >= 3:
                    # Simplify contour
                    epsilon = 0.01 * cv2.arcLength(contour, True)
                    approx = cv2.approxPolyDP(contour, epsilon, True)
                    
                    # Adjust coordinate offset
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
        Merge tile results, handle overlapping regions
        """
        # Simplified version: directly use all masks
        # In practice should handle duplicate detection in overlapping regions
        
        # Deduplication: based on center point distance
        unique_masks = []
        unique_labels = []
        
        for i, mask in enumerate(all_masks):
            # Calculate mask center
            center = np.mean(mask, axis=0)
            
            # Check if duplicate with existing masks
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
        """Save results in JSON format"""
        # Convert numpy arrays to list for JSON serialization
        serializable_results = {
            "image_path": image_path,
            "image_width": results["image_width"],
            "image_height": results["image_height"],
            "total_cells": len(results["masks"]),
            "cells": []
        }
        
        for i, (mask, label) in enumerate(zip(results["masks"], results["labels"])):
            # Calculate bounding box
            mask_array = np.array(mask)
            x_min, y_min = mask_array.min(axis=0)
            x_max, y_max = mask_array.max(axis=0)
            
            # Calculate area
            area = cv2.contourArea(mask_array.astype(np.float32))
            
            serializable_results["cells"].append({
                "id": i,
                "label": label,
                "polygon": mask_array.tolist(),
                "bbox": [float(x_min), float(y_min), float(x_max), float(y_max)],
                "area": float(area),
                "centroid": mask_array.mean(axis=0).tolist()
            })
        
        # Save JSON
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
        """Generate visualization image"""
        vis_image = image.copy()
        
        # Draw all masks
        for mask in results["masks"]:
            mask_array = np.array(mask, dtype=np.int32)
            
            # Random color
            color = tuple(np.random.randint(0, 255, 3).tolist())
            
            # Draw contours
            cv2.polylines(vis_image, [mask_array], True, color, 2)
        
        # Save
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
        Generate tissue mask (for skipping background tiles)
        
        Args:
            image_path: Input image path
            output_dir: Output directory
            progress_callback: Progress callback
            
        Returns:
            Result dictionary
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        if progress_callback:
            await progress_callback(0, 100, "Loading image...")
        
        # Load image
        image, slide = await self._load_image(image_path)
        
        if progress_callback:
            await progress_callback(50, 100, "Generating tissue mask...")
        
        # Generate tissue mask (simple threshold method)
        loop = asyncio.get_event_loop()
        mask = await loop.run_in_executor(
            None,
            self._generate_tissue_mask_sync,
            image
        )
        
        # Save mask
        mask_path = output_path / "tissue_mask.png"
        await loop.run_in_executor(
            None,
            cv2.imwrite,
            str(mask_path),
            mask
        )
        
        # Generate visualization
        vis_image = image.copy()
        vis_image[mask == 0] = vis_image[mask == 0] // 2  # Darken background
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
            "result_path": str(mask_path),  # Add result_path for frontend to display View Results button
            "tissue_area": int(np.sum(mask > 0)),
            "total_area": int(mask.size),
            "tissue_percentage": float(np.sum(mask > 0) / mask.size * 100),
            "completed_at": datetime.now().isoformat()
        }
    
    def _generate_tissue_mask_sync(self, image: np.ndarray) -> np.ndarray:
        """Synchronously generate tissue mask"""
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        
        # Otsu threshold
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Morphological operations cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        return mask


# Global service instance
instanseg_service = InstanSegService()

