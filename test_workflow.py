#!/usr/bin/env python3
"""
测试工作流创建和执行
"""
import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "test-user-123"

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def create_workflow():
    """创建一个简单的工作流"""
    print_section("创建工作流")
    
    workflow_data = {
        "name": "Test Cell Segmentation Workflow",
        "description": "测试细胞分割工作流",
        "nodes": [
            {
                "node_id": "node_1",
                "job_type": "cell_segmentation",
                "branch": "main",
                "image_path": "/Users/Donytu/Desktop/take_home_project/Branch-Aware_Multi-Tenant-Workflow-Scheduler/CMU-1-JP2K-33005.svs",
                "depends_on": [],
                "parameters": {
                    "tile_size": 512,
                    "overlap": 64
                }
            }
        ]
    }
    
    headers = {"X-User-ID": USER_ID}
    
    print(f"📤 发送请求到 {BASE_URL}/workflows")
    print(f"👤 用户ID: {USER_ID}")
    print(f"📋 工作流配置:")
    print(json.dumps(workflow_data, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/workflows",
        json=workflow_data,
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        workflow_id = result["workflow_id"]
        print(f"\n✅ 工作流创建成功!")
        print(f"🆔 Workflow ID: {workflow_id}")
        return workflow_id
    else:
        print(f"\n❌ 工作流创建失败!")
        print(f"状态码: {response.status_code}")
        print(f"错误: {response.text}")
        return None

def monitor_workflow(workflow_id):
    """监控工作流进度"""
    print_section(f"监控工作流: {workflow_id}")
    
    headers = {"X-User-ID": USER_ID}
    
    last_progress = -1
    last_message = ""
    iteration = 0
    
    while True:
        response = requests.get(
            f"{BASE_URL}/workflows/{workflow_id}/progress",
            headers=headers
        )
        
        if response.status_code != 200:
            print(f"\n❌ 获取进度失败: {response.text}")
            break
        
        progress = response.json()
        status = progress["status"]
        percent = progress["progress_percent"]
        
        # 打印进度
        if percent != last_progress or iteration % 10 == 0:
            print(f"\n📊 工作流状态: {status}")
            print(f"📈 整体进度: {percent:.1f}%")
            
            if progress["jobs"]:
                print(f"\n任务详情:")
                for job in progress["jobs"]:
                    job_msg = job.get("current_message", "")
                    print(f"  - Job {job['job_id'][:8]}: {job['status']} ({job['progress_percent']:.1f}%)")
                    if job_msg and job_msg != last_message:
                        print(f"    💬 {job_msg}")
                        last_message = job_msg
                    if job["tiles_total"] > 0:
                        print(f"    🧩 瓦片: {job['tiles_processed']}/{job['tiles_total']}")
            
            last_progress = percent
        
        # 检查是否完成
        if status in ["completed", "failed", "cancelled"]:
            print(f"\n🏁 工作流最终状态: {status}")
            if status == "completed":
                print("✅ 工作流成功完成!")
            else:
                print(f"❌ 工作流状态: {status}")
            break
        
        time.sleep(2)
        iteration += 1
    
    return progress

def check_system_stats():
    """检查系统统计信息"""
    print_section("系统统计")
    
    response = requests.get(f"{BASE_URL}/stats/system")
    
    if response.status_code == 200:
        stats = response.json()
        print(f"📊 系统状态:")
        print(f"  - 活跃用户: {stats['active_users']}/{stats['max_active_users']}")
        print(f"  - 活跃Worker: {stats['active_workers']}/{stats['max_workers']}")
        print(f"  - 队列深度: {stats['queue_depth']}")
        print(f"  - 已处理任务: {stats['total_jobs_processed']}")
        print(f"  - 平均延迟: {stats['average_job_latency_seconds']:.2f}秒")
        if stats.get('per_branch_queue_depth'):
            print(f"  - 分支队列: {stats['per_branch_queue_depth']}")
    else:
        print(f"❌ 获取统计失败: {response.text}")

def main():
    print_section("工作流测试脚本")
    print("测试Branch-Aware Multi-Tenant Workflow Scheduler")
    print()
    
    # 检查系统健康
    print("🔍 检查系统健康...")
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code != 200:
        print(f"❌ 系统未就绪: {response.text}")
        sys.exit(1)
    print("✅ 系统就绪")
    
    # 检查系统统计
    check_system_stats()
    
    # 创建工作流
    workflow_id = create_workflow()
    if not workflow_id:
        sys.exit(1)
    
    # 监控工作流
    final_progress = monitor_workflow(workflow_id)
    
    # 再次检查系统统计
    check_system_stats()
    
    print_section("测试完成")

if __name__ == "__main__":
    main()

