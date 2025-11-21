"""
测试批处理功能 - 验证InstanSeg批量处理瓦片的性能改进
"""
import asyncio
import time
from pathlib import Path
from backend.services.instanseg_service import instanseg_service
from backend.core.config import settings

async def test_batch_processing():
    """测试批处理功能"""
    
    print("=" * 80)
    print("🧪 测试InstanSeg批处理功能")
    print("=" * 80)
    
    # 测试图像路径
    test_image = Path("uploads/user-001/CMU-1-JP2K-33005.svs")
    
    if not test_image.exists():
        print(f"❌ 测试图像不存在: {test_image}")
        # 尝试其他路径
        test_image = Path("CMU-1-JP2K-33005.svs")
        if not test_image.exists():
            print(f"❌ 测试图像也不存在: {test_image}")
            print("⚠️ 请确保有可用的测试图像")
            return
    
    print(f"✅ 找到测试图像: {test_image}")
    print(f"📦 批处理大小: {settings.BATCH_SIZE}")
    print(f"🔢 瓦片大小: {settings.TILE_SIZE}")
    print(f"📏 重叠区域: {settings.TILE_OVERLAP}")
    print()
    
    # 初始化服务
    print("🔄 初始化InstanSeg服务...")
    try:
        await instanseg_service.initialize()
        print("✅ InstanSeg服务初始化成功")
    except Exception as e:
        print(f"❌ InstanSeg服务初始化失败: {e}")
        print("⚠️ 这可能是因为InstanSeg未安装或依赖缺失")
        return
    
    # 创建输出目录
    output_dir = Path("results/batch-test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 进度回调
    async def progress_callback(current, total, message):
        percentage = (current / total * 100) if total > 0 else 0
        print(f"📊 进度: {current}/{total} ({percentage:.1f}%) - {message}")
    
    # 运行分割
    print("\n🚀 开始批处理分割...")
    print("-" * 80)
    start_time = time.time()
    
    try:
        result = await instanseg_service.segment_large_image(
            image_path=str(test_image),
            output_dir=str(output_dir),
            progress_callback=progress_callback
        )
        
        elapsed_time = time.time() - start_time
        
        print("-" * 80)
        print("\n✅ 批处理分割完成!")
        print("\n📊 结果统计:")
        print(f"  • 图像尺寸: {result['width']}x{result['height']}")
        print(f"  • 总瓦片数: {result['total_tiles']}")
        print(f"  • 过滤瓦片数: {result['filtered_tiles']} ({result['filtered_tiles']/result['total_tiles']*100:.1f}%)")
        print(f"  • 密度过滤: {result['filtered_by_density']}")
        print(f"  • 实际处理: {result['processed_tiles']}")
        print(f"  • 检测细胞数: {result['total_cells']}")
        print(f"  • Stage 1 时间: {result['stage1_time']}s")
        print(f"  • Stage 2 时间: {result['stage2_time']}s")
        print(f"  • 总耗时: {elapsed_time:.2f}s")
        print(f"  • 理论加速比: {result['speedup']}x")
        print(f"  • 结果文件: {result['result_path']}")
        print(f"  • 可视化: {result['visualization_path']}")
        print(f"  • Tissue mask: {result['mask_path']}")
        
        # 计算平均处理速度
        if result['processed_tiles'] > 0:
            avg_time_per_tile = result['stage2_time'] / result['processed_tiles']
            print(f"  • 平均每瓦片: {avg_time_per_tile:.3f}s")
            
            # 估算批处理带来的提升
            batch_size = settings.BATCH_SIZE
            print(f"\n🚀 批处理优化:")
            print(f"  • 批处理大小: {batch_size}")
            print(f"  • 批次数量: {(result['processed_tiles'] + batch_size - 1) // batch_size}")
        
    except Exception as e:
        print(f"\n❌ 分割失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print("\n" + "=" * 80)
    print("✅ 测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_batch_processing())

