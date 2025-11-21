#!/usr/bin/env python3
"""
测试Docker环境中InstanSeg是否真的在工作
"""
import requests
import json
import time

API_BASE = "http://localhost:8000/api/v1"
USER_ID = "docker-test-instanseg"
IMAGE_PATH = "/app/CMU-1-JP2K-33005.svs"

def create_job():
    """创建一个小规模的细胞分割任务"""
    url = f"{API_BASE}/jobs"
    headers = {
        "X-User-ID": USER_ID,
        "Content-Type": "application/json"
    }
    
    data = {
        "job_type": "cell_segmentation",
        "branch": "test",
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 512,  # 小尺寸快速测试
            "overlap": 64
        }
    }
    
    print(f"📤 创建测试任务...")
    print(f"  - Image: {IMAGE_PATH}")
    print(f"  - Tile size: 512")
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code != 200:
        print(f"❌ 创建任务失败: {response.status_code}")
        print(response.text)
        return None
    
    job = response.json()
    print(f"✅ 任务创建成功! Job ID: {job['job_id']}")
    return job['job_id']

def monitor_job(job_id, max_wait=None):
    """监控任务并查找InstanSeg真实推理的证据"""
    if max_wait:
        print(f"\n🔍 监控任务进度 (最多等待{max_wait}秒)...")
    else:
        print(f"\n🔍 监控任务进度 (无时间限制)...")
    
    start_time = time.time()
    last_progress = -1
    
    while True:
        elapsed = time.time() - start_time
        
        if max_wait and elapsed > max_wait:
            print(f"\n⏱️ 超时")
            break
        
        url = f"{API_BASE}/jobs/{job_id}"
        headers = {"X-User-ID": USER_ID}
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"\n❌ 无法获取任务状态")
            break
        
        job = response.json()
        status = job['status']
        progress = job.get('progress_percent', 0)
        
        if progress != last_progress:
            print(f"[{elapsed:.1f}s] 状态: {status} | 进度: {progress:.1f}%")
            last_progress = progress
        
        if status == "SUCCEEDED":
            print(f"\n✅ 任务成功完成! 耗时: {elapsed:.1f}秒")
            return job
        elif status == "FAILED":
            print(f"\n❌ 任务失败")
            print(f"错误: {job.get('error', 'Unknown')}")
            return None
        
        time.sleep(2)
    
    return None

def check_logs_for_instanseg():
    """检查Docker日志中是否有真实InstanSeg推理的证据"""
    import subprocess
    
    print("\n🔎 检查Docker日志中的InstanSeg推理证据...")
    
    try:
        result = subprocess.run(
            ["docker", "compose", "logs", "--tail", "500", "app"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        logs = result.stdout + result.stderr
        
        # 查找关键标记
        markers = {
            "✅ InstanSeg导入成功": False,
            "✅ [MODEL] InstanSeg": False,
            "🔬 [SEGMENT] 使用真实InstanSeg": False,
            "✅ [INSTANSEG_REAL]": False,
        }
        
        for marker in markers:
            if marker in logs:
                markers[marker] = True
                print(f"  ✓ 找到: {marker}")
        
        # 检查是否使用Mock模式
        if "使用Mock方法分割" in logs:
            print(f"  ✗ 警告: 发现Mock模式标记!")
            return False
        
        # 验证逻辑：
        # 1. 优先检查启动时的标记（导入和模型加载）
        # 2. 如果找不到启动标记，检查推理时的标记（说明已经运行很久了）
        startup_ok = markers["✅ InstanSeg导入成功"] and markers["✅ [MODEL] InstanSeg"]
        inference_ok = markers["🔬 [SEGMENT] 使用真实InstanSeg"] and markers["✅ [INSTANSEG_REAL]"]
        
        if startup_ok or inference_ok:
            print("\n✅ InstanSeg在Docker中正常工作!")
            if inference_ok and not startup_ok:
                print("  ℹ️ (启动日志已被新日志覆盖，但推理标记证实了InstanSeg正在工作)")
            return True
        else:
            print("\n⚠️ InstanSeg可能未正确加载")
            return False
            
    except Exception as e:
        print(f"  ✗ 检查日志失败: {e}")
        return False

def main():
    print("=" * 70)
    print("Docker环境 - InstanSeg真实推理验证")
    print("=" * 70)
    print()
    
    # 1. 检查API连接
    print("🔗 测试API连接...")
    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        print(f"✅ API连接成功\n")
    except Exception as e:
        print(f"❌ API连接失败: {e}")
        return
    
    # 2. 创建测试任务
    job_id = create_job()
    if not job_id:
        return
    
    # 3. 监控任务（无时间限制，让InstanSeg完成完整的推理）
    result = monitor_job(job_id, max_wait=None)
    
    # 4. 检查日志
    instanseg_working = check_logs_for_instanseg()
    
    print()
    print("=" * 70)
    if result and instanseg_working:
        print("🎉 验证成功! InstanSeg在Docker中真实运行!")
    elif result:
        print("⚠️ 任务完成,但需要检查是否使用了真实InstanSeg")
    else:
        print("❌ 验证失败")
    print("=" * 70)

if __name__ == "__main__":
    main()

