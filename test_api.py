"""
API测试脚本
使用此脚本快速测试系统功能
"""
import requests
import time
import json
from pathlib import Path

# 配置
API_BASE = "http://localhost:8000/api/v1"
USER_ID = "user-001"

def test_health():
    """测试健康检查"""
    print("\n=== 测试健康检查 ===")
    response = requests.get("http://localhost:8000/health")
    print(f"状态: {response.status_code}")
    print(f"响应: {response.json()}")
    return response.status_code == 200

def test_system_stats():
    """测试系统统计"""
    print("\n=== 测试系统统计 ===")
    response = requests.get(f"{API_BASE}/stats/system")
    print(f"状态: {response.status_code}")
    print(f"响应: {json.dumps(response.json(), indent=2)}")
    return response.status_code == 200

def test_create_job(image_path: str = "./test_image.jpg"):
    """测试创建任务"""
    print("\n=== 测试创建任务 ===")
    
    data = {
        "job_type": "cell_segmentation",
        "branch": "main",
        "image_path": image_path,
        "parameters": {
            "tile_size": 512,
            "overlap": 64
        }
    }
    
    response = requests.post(
        f"{API_BASE}/jobs",
        headers={"X-User-ID": USER_ID},
        json=data
    )
    
    print(f"状态: {response.status_code}")
    if response.status_code == 200:
        job = response.json()
        print(f"任务已创建: {job['job_id']}")
        print(f"状态: {job['status']}")
        return job['job_id']
    else:
        print(f"错误: {response.text}")
        return None

def test_get_job(job_id: str):
    """测试获取任务详情"""
    print(f"\n=== 测试获取任务详情 (ID: {job_id[:8]}...) ===")
    
    response = requests.get(
        f"{API_BASE}/jobs/{job_id}",
        headers={"X-User-ID": USER_ID}
    )
    
    print(f"状态: {response.status_code}")
    if response.status_code == 200:
        job = response.json()
        print(f"任务状态: {job['status']}")
        print(f"进度: {job['progress_percent']:.1f}%")
        print(f"消息: {job['current_message']}")
        return job
    else:
        print(f"错误: {response.text}")
        return None

def test_list_jobs():
    """测试列出任务"""
    print("\n=== 测试列出任务 ===")
    
    response = requests.get(
        f"{API_BASE}/jobs",
        headers={"X-User-ID": USER_ID}
    )
    
    print(f"状态: {response.status_code}")
    if response.status_code == 200:
        jobs = response.json()
        print(f"任务总数: {len(jobs)}")
        for job in jobs[:5]:  # 只显示前5个
            print(f"  - {job['job_id'][:8]}... | {job['status']} | {job['branch']}")
        return jobs
    else:
        print(f"错误: {response.text}")
        return []

def test_create_workflow(image_path: str = "./test_image.jpg"):
    """测试创建工作流"""
    print("\n=== 测试创建工作流 ===")
    
    data = {
        "name": "测试工作流",
        "description": "先生成组织掩码，再进行细胞分割",
        "nodes": [
            {
                "node_id": "node-1",
                "job_type": "tissue_mask",
                "branch": "preprocessing",
                "image_path": image_path,
                "parameters": {},
                "depends_on": []
            },
            {
                "node_id": "node-2",
                "job_type": "cell_segmentation",
                "branch": "segmentation",
                "image_path": image_path,
                "parameters": {
                    "tile_size": 512,
                    "overlap": 64
                },
                "depends_on": ["node-1"]
            }
        ]
    }
    
    response = requests.post(
        f"{API_BASE}/workflows",
        headers={"X-User-ID": USER_ID},
        json=data
    )
    
    print(f"状态: {response.status_code}")
    if response.status_code == 200:
        workflow = response.json()
        print(f"工作流已创建: {workflow['workflow_id']}")
        print(f"节点数: {len(workflow['nodes'])}")
        return workflow['workflow_id']
    else:
        print(f"错误: {response.text}")
        return None

def test_monitor_job(job_id: str, duration: int = 30):
    """监控任务进度"""
    print(f"\n=== 监控任务进度 (持续 {duration} 秒) ===")
    
    start_time = time.time()
    while time.time() - start_time < duration:
        job = test_get_job(job_id)
        if not job:
            break
        
        if job['status'] in ['SUCCEEDED', 'FAILED', 'CANCELLED']:
            print(f"\n任务已结束: {job['status']}")
            if job.get('result_path'):
                print(f"结果路径: {job['result_path']}")
            if job.get('error'):
                print(f"错误: {job['error']}")
            break
        
        time.sleep(2)

def test_upload_file(file_path: str):
    """测试文件上传"""
    print(f"\n=== 测试文件上传 ({file_path}) ===")
    
    if not Path(file_path).exists():
        print(f"文件不存在: {file_path}")
        return None
    
    with open(file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post(
            f"{API_BASE}/upload",
            headers={"X-User-ID": USER_ID},
            files=files
        )
    
    print(f"状态: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"上传成功: {result['filename']}")
        print(f"路径: {result['path']}")
        print(f"大小: {result['size']} 字节")
        return result['path']
    else:
        print(f"错误: {response.text}")
        return None

def run_basic_tests():
    """运行基本测试"""
    print("=" * 60)
    print("开始运行API测试")
    print("=" * 60)
    
    # 健康检查
    if not test_health():
        print("\n❌ 健康检查失败，服务可能未启动")
        return
    
    # 系统统计
    test_system_stats()
    
    # 列出现有任务
    test_list_jobs()
    
    print("\n" + "=" * 60)
    print("基本测试完成")
    print("=" * 60)

def run_job_test(image_path: str):
    """运行完整的任务测试"""
    print("=" * 60)
    print("开始运行任务测试")
    print("=" * 60)
    
    # 创建任务
    job_id = test_create_job(image_path)
    if not job_id:
        print("\n❌ 创建任务失败")
        return
    
    # 监控任务
    test_monitor_job(job_id, duration=60)
    
    print("\n" + "=" * 60)
    print("任务测试完成")
    print("=" * 60)

def run_workflow_test(image_path: str):
    """运行工作流测试"""
    print("=" * 60)
    print("开始运行工作流测试")
    print("=" * 60)
    
    # 创建工作流
    workflow_id = test_create_workflow(image_path)
    if not workflow_id:
        print("\n❌ 创建工作流失败")
        return
    
    # 监控工作流（通过查询其任务）
    time.sleep(2)
    test_list_jobs()
    
    print("\n" + "=" * 60)
    print("工作流测试完成")
    print("=" * 60)

if __name__ == "__main__":
    import sys
    
    # 运行基本测试
    run_basic_tests()
    
    # 如果提供了图像路径，运行完整测试
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        print(f"\n使用图像: {image_path}")
        
        # 测试上传（如果是本地文件）
        if Path(image_path).exists():
            uploaded_path = test_upload_file(image_path)
            if uploaded_path:
                image_path = uploaded_path
        
        # 运行任务测试
        run_job_test(image_path)
        
        # 运行工作流测试
        # run_workflow_test(image_path)
    else:
        print("\n提示: 使用 'python test_api.py <image_path>' 运行完整测试")
        print("示例: python test_api.py ./uploads/test.jpg")


