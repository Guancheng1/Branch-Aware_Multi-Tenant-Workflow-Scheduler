#!/usr/bin/env python3
"""
测试Docker环境中的API - 创建图像分割任务并监控进度
"""
import requests
import json
import time
import sys

# 配置
API_BASE = "http://localhost:8000/api/v1"
USER_ID = "test-user-123"
IMAGE_PATH = "/app/CMU-1-JP2K-33005.svs"

def create_job():
    """创建一个细胞分割任务"""
    url = f"{API_BASE}/jobs"
    headers = {
        "X-User-ID": USER_ID,
        "Content-Type": "application/json"
    }
    
    data = {
        "job_type": "cell_segmentation",
        "branch": "main",
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 512,
            "overlap": 64
        }
    }
    
    print(f"📤 创建任务...")
    print(f"  - User ID: {USER_ID}")
    print(f"  - Image: {IMAGE_PATH}")
    print(f"  - Tile size: 512, Overlap: 64")
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"❌ 创建任务失败: {response.status_code}")
        print(response.text)
        return None
    
    job = response.json()
    print(f"✅ 任务创建成功!")
    print(f"  - Job ID: {job['job_id']}")
    print(f"  - Status: {job['status']}")
    print()
    
    return job['job_id']


def get_job_status(job_id):
    """获取任务状态"""
    url = f"{API_BASE}/jobs/{job_id}"
    headers = {"X-User-ID": USER_ID}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return None
    
    return response.json()


def monitor_job(job_id, max_wait=None):
    """监控任务进度"""
    if max_wait:
        print(f"🔍 监控任务进度 (最多等待{max_wait}秒)...")
    else:
        print(f"🔍 监控任务进度 (无时间限制)...")
    print(f"  Job ID: {job_id}")
    print()
    
    start_time = time.time()
    last_progress = -1
    
    while True:
        elapsed = time.time() - start_time
        
        if max_wait and elapsed > max_wait:
            print(f"\n⏱️ 超时 ({max_wait}秒)")
            break
        
        job = get_job_status(job_id)
        
        if not job:
            print(f"\n❌ 无法获取任务状态")
            break
        
        status = job['status']
        progress = job.get('progress_percent', 0)
        tiles_processed = job.get('tiles_processed', 0)
        tiles_total = job.get('tiles_total', 0)
        message = job.get('current_message', '')
        
        # 只在进度变化时打印
        if progress != last_progress:
            print(f"[{elapsed:.1f}s] 状态: {status} | 进度: {progress:.1f}% | 瓦片: {tiles_processed}/{tiles_total}")
            if message:
                print(f"         消息: {message}")
            last_progress = progress
        
        # 检查是否完成
        if status == "SUCCEEDED":
            print(f"\n✅ 任务成功完成!")
            print(f"  - 总耗时: {elapsed:.1f}秒")
            if job.get('result_path'):
                print(f"  - 结果路径: {job['result_path']}")
            break
        
        elif status == "FAILED":
            print(f"\n❌ 任务失败")
            if job.get('error'):
                print(f"  - 错误: {job['error']}")
            break
        
        elif status == "CANCELLED":
            print(f"\n⚠️ 任务已取消")
            break
        
        time.sleep(1)


def main():
    print("=" * 60)
    print("Docker环境 - 图像分割任务测试")
    print("=" * 60)
    print()
    
    # 1. 测试API连接
    print("🔗 测试API连接...")
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        print(f"✅ API连接成功 (状态码: {response.status_code})")
    except Exception as e:
        print(f"❌ API连接失败: {e}")
        sys.exit(1)
    
    print()
    
    # 2. 创建任务
    job_id = create_job()
    if not job_id:
        print("❌ 无法创建任务，退出")
        sys.exit(1)
    
    # 3. 监控任务
    monitor_job(job_id, max_wait=None)  # 无时间限制，让任务完整执行
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()

