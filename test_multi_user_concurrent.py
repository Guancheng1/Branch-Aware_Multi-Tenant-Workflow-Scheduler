"""
测试多用户并发调度
验证最多3个用户可以同时运行任务
"""
import asyncio
import httpx
import time
from typing import List

BASE_URL = "http://localhost:8000"


async def create_workflow_for_user(user_id: str, workflow_name: str) -> str:
    """为用户创建一个workflow"""
    async with httpx.AsyncClient(timeout=300.0) as client:
        workflow_data = {
            "nodes": [
                {
                    "node_id": f"{workflow_name}_node1",
                    "job_type": "tissue_mask",
                    "branch": f"{workflow_name}_branch1",
                    "depends_on": [],
                    "image_path": "CMU-1-JP2K-33005.svs",
                    "parameters": {}
                }
            ]
        }
        
        headers = {"X-User-ID": user_id}
        
        print(f"[{user_id}] 正在创建 workflow: {workflow_name}")
        response = await client.post(
            f"{BASE_URL}/api/workflows",
            json=workflow_data,
            headers=headers
        )
        
        if response.status_code == 200:
            workflow_id = response.json()["workflow_id"]
            print(f"[{user_id}] ✅ Workflow 创建成功: {workflow_id}")
            return workflow_id
        else:
            print(f"[{user_id}] ❌ Workflow 创建失败: {response.text}")
            return None


async def check_workflow_status(user_id: str, workflow_id: str) -> dict:
    """检查workflow状态"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {"X-User-ID": user_id}
        response = await client.get(
            f"{BASE_URL}/api/workflows/{workflow_id}/progress",
            headers=headers
        )
        if response.status_code == 200:
            return response.json()
        return None


async def get_system_stats() -> dict:
    """获取系统统计信息"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{BASE_URL}/api/system/stats")
        if response.status_code == 200:
            return response.json()
        return None


async def monitor_system(duration: int = 60):
    """监控系统状态"""
    start_time = time.time()
    while time.time() - start_time < duration:
        stats = await get_system_stats()
        if stats:
            print(f"\n📊 系统状态:")
            print(f"   活跃用户: {stats['active_users']}/{stats['max_active_users']}")
            print(f"   活跃Worker: {stats['active_workers']}/{stats['max_workers']}")
            print(f"   队列深度: {stats['queue_depth']}")
            print(f"   等待用户: {stats['waiting_users']}")
            print(f"   已处理任务: {stats['total_jobs_processed']}")
        await asyncio.sleep(5)


async def test_concurrent_users():
    """测试多用户并发"""
    print("=" * 80)
    print("开始测试：多用户并发调度")
    print("=" * 80)
    
    # 创建4个用户的workflow
    users = [
        ("user-001", "workflow-1"),
        ("user-002", "workflow-2"),
        ("user-003", "workflow-3"),
        ("user-004", "workflow-4"),  # 这个用户应该会等待
    ]
    
    print("\n第1步：同时提交4个用户的workflow")
    print("-" * 80)
    
    # 并发创建所有workflow
    tasks = []
    for user_id, workflow_name in users:
        task = create_workflow_for_user(user_id, workflow_name)
        tasks.append(task)
    
    workflow_ids = await asyncio.gather(*tasks)
    
    print("\n第2步：检查初始系统状态")
    print("-" * 80)
    await asyncio.sleep(2)  # 等待调度器处理
    
    stats = await get_system_stats()
    if stats:
        print(f"\n📊 系统状态:")
        print(f"   活跃用户: {stats['active_users']}/{stats['max_active_users']}")
        print(f"   活跃Worker: {stats['active_workers']}/{stats['max_workers']}")
        print(f"   等待用户: {stats['waiting_users']}")
        
        # 验证
        if stats['active_users'] <= 3:
            print(f"   ✅ 活跃用户数正确 (≤3)")
        else:
            print(f"   ❌ 活跃用户数错误 (>3)")
        
        if stats['waiting_users'] >= 1:
            print(f"   ✅ 有用户在等待 (第4个用户)")
        else:
            print(f"   ⚠️ 没有用户在等待 (可能任务执行太快)")
    
    print("\n第3步：监控30秒，观察用户切换")
    print("-" * 80)
    
    # 监控系统状态
    await monitor_system(duration=30)
    
    print("\n" + "=" * 80)
    print("测试完成！")
    print("=" * 80)
    
    # 最终状态检查
    print("\n检查各个workflow的最终状态:")
    for i, (user_id, _) in enumerate(users):
        if workflow_ids[i]:
            status = await check_workflow_status(user_id, workflow_ids[i])
            if status:
                print(f"[{user_id}] Status: {status['status']}, Progress: {status['progress_percent']:.1f}%")


async def test_sequential_users():
    """测试顺序提交用户"""
    print("=" * 80)
    print("开始测试：顺序提交用户")
    print("=" * 80)
    
    users = ["user-seq-1", "user-seq-2", "user-seq-3"]
    
    for i, user_id in enumerate(users):
        print(f"\n提交用户 {i+1}/3: {user_id}")
        workflow_id = await create_workflow_for_user(user_id, f"sequential-{i}")
        
        await asyncio.sleep(2)
        
        stats = await get_system_stats()
        if stats:
            print(f"   活跃用户: {stats['active_users']}/{stats['max_active_users']}")
            print(f"   活跃Worker: {stats['active_workers']}/{stats['max_workers']}")
    
    print("\n监控20秒...")
    await monitor_system(duration=20)


async def main():
    """主函数"""
    print("🚀 多用户并发测试工具")
    print("请确保服务器正在运行: python main.py\n")
    
    # 先检查服务器是否运行
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{BASE_URL}/api/system/stats")
            if response.status_code != 200:
                print("❌ 服务器未正常响应，请先启动服务器")
                return
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        print("请先运行: python main.py")
        return
    
    print("✅ 服务器连接成功\n")
    
    # 运行测试
    print("选择测试模式:")
    print("1. 并发提交4个用户（测试用户等待）")
    print("2. 顺序提交3个用户")
    
    # 默认运行测试1
    await test_concurrent_users()
    
    # 可选：运行测试2
    # await test_sequential_users()


if __name__ == "__main__":
    asyncio.run(main())

