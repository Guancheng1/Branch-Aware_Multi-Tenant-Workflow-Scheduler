"""
测试批处理逻辑 - 不实际运行InstanSeg，只验证批处理逻辑
"""
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from backend.core.config import settings

def test_batch_logic():
    """测试批处理逻辑"""
    
    print("=" * 80)
    print("🧪 测试批处理逻辑（不运行实际模型）")
    print("=" * 80)
    
    # 模拟瓦片
    total_tiles = 100
    filtered_tiles = [(i*10, i*10, 512, 512) for i in range(total_tiles)]
    
    batch_size = settings.BATCH_SIZE
    
    print(f"\n📊 测试配置:")
    print(f"  • 总瓦片数: {total_tiles}")
    print(f"  • 批处理大小: {batch_size}")
    
    # 测试批次划分
    print(f"\n📦 批次划分测试:")
    batch_count = 0
    tiles_in_batches = 0
    
    for batch_start in range(0, len(filtered_tiles), batch_size):
        batch_end = min(batch_start + batch_size, len(filtered_tiles))
        batch_tiles = filtered_tiles[batch_start:batch_end]
        batch_count += 1
        tiles_in_batches += len(batch_tiles)
        
        print(f"  批次 {batch_count}: 瓦片 {batch_start+1}-{batch_end} ({len(batch_tiles)} 个)")
    
    print(f"\n✅ 验证结果:")
    print(f"  • 总批次数: {batch_count}")
    print(f"  • 批次中瓦片总数: {tiles_in_batches}")
    print(f"  • 验证: {'通过' if tiles_in_batches == total_tiles else '失败'}")
    
    # 测试空批次处理
    print(f"\n📦 边界条件测试:")
    
    # 测试1: 空列表
    empty_tiles = []
    empty_batches = 0
    for batch_start in range(0, len(empty_tiles), batch_size):
        empty_batches += 1
    print(f"  • 空列表批次数: {empty_batches} (期望: 0)")
    
    # 测试2: 少于batch_size的瓦片
    few_tiles = filtered_tiles[:3]
    few_batches = 0
    for batch_start in range(0, len(few_tiles), batch_size):
        batch_end = min(batch_start + batch_size, len(few_tiles))
        batch_tiles = few_tiles[batch_start:batch_end]
        few_batches += 1
    print(f"  • {len(few_tiles)}个瓦片批次数: {few_batches} (期望: 1)")
    
    # 测试3: 正好是batch_size的倍数
    exact_tiles = filtered_tiles[:batch_size * 3]
    exact_batches = 0
    for batch_start in range(0, len(exact_tiles), batch_size):
        exact_batches += 1
    print(f"  • {len(exact_tiles)}个瓦片批次数: {exact_batches} (期望: {len(exact_tiles)//batch_size})")
    
    print("\n" + "=" * 80)
    print("✅ 批处理逻辑测试完成!")
    print("=" * 80)
    
    # 验证配置
    print(f"\n⚙️ 当前配置:")
    print(f"  • BATCH_SIZE: {settings.BATCH_SIZE}")
    print(f"  • TILE_SIZE: {settings.TILE_SIZE}")
    print(f"  • TILE_OVERLAP: {settings.TILE_OVERLAP}")
    print(f"  • TISSUE_MASK_LEVEL: {settings.TISSUE_MASK_LEVEL}")
    print(f"  • CELL_SEG_LEVEL: {settings.CELL_SEG_LEVEL}")
    print(f"  • TISSUE_RATIO_THRESH: {settings.TISSUE_RATIO_THRESH}")
    print(f"  • FG_DENSITY_THRESH: {settings.FG_DENSITY_THRESH}")
    print(f"  • MIN_CELL_AREA: {settings.MIN_CELL_AREA}")


if __name__ == "__main__":
    test_batch_logic()

