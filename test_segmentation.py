#!/usr/bin/env python3
"""
测试图像分割功能
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from backend.services.instanseg_service import instanseg_service
from backend.core.config import settings

async def test_segmentation():
    """测试分割功能"""
    
    # 测试文件
    image_path = "/Users/Donytu/Desktop/take_home_project/Branch-Aware_Multi-Tenant-Workflow-Scheduler/CMU-1-JP2K-33005.svs"
    output_dir = "/Users/Donytu/Desktop/take_home_project/Branch-Aware_Multi-Tenant-Workflow-Scheduler/test_results"
    
    print("="*80)
    print("🧪 测试图像分割功能")
    print("="*80)
    print(f"📂 输入文件: {image_path}")
    print(f"📁 输出目录: {output_dir}")
    print()
    
    # 检查文件是否存在
    if not Path(image_path).exists():
        print(f"❌ 错误：文件不存在: {image_path}")
        return
    
    print(f"✅ 文件存在，大小: {Path(image_path).stat().st_size / (1024*1024):.2f} MB")
    print()
    
    # 初始化服务
    print("🔧 初始化InstanSeg服务...")
    try:
        await instanseg_service.initialize()
        print("✅ InstanSeg服务初始化完成")
    except Exception as e:
        print(f"⚠️ InstanSeg初始化失败，将使用Mock模式: {e}")
    print()
    
    # 进度回调
    async def progress_callback(processed, total, message):
        percent = (processed / total * 100) if total > 0 else 0
        print(f"📊 进度: {processed}/{total} ({percent:.1f}%) - {message}")
    
    # 执行分割
    print("🚀 开始分割...")
    print()
    try:
        result = await instanseg_service.segment_large_image(
            image_path=image_path,
            output_dir=output_dir,
            tile_size=512,  # 使用较小的tile size以加快测试
            overlap=64,
            progress_callback=progress_callback
        )
        
        print()
        print("="*80)
        print("✅ 分割完成！")
        print("="*80)
        print(f"📊 结果统计:")
        print(f"   - 图像尺寸: {result['width']}x{result['height']}")
        print(f"   - 总瓦片数: {result['total_tiles']}")
        print(f"   - 检测到的细胞数: {result['total_cells']}")
        print(f"   - 结果文件: {result['result_path']}")
        print(f"   - 可视化文件: {result['visualization_path']}")
        print(f"   - 完成时间: {result['completed_at']}")
        print("="*80)
        
    except Exception as e:
        print()
        print("="*80)
        print(f"❌ 分割失败: {e}")
        print("="*80)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_segmentation())

