#!/usr/bin/env python3
"""
测试多租户Branch隔离

验证不同用户的同名branch不会互相影响，可以并行执行。

测试场景：
1. User 1 在 "main" branch 创建任务
2. User 2 在 "main" branch 创建任务
3. 验证两个任务可以并行执行（不会串行）
"""
import requests
import json
import time
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"
IMAGE_PATH = "/Users/Donytu/Desktop/take_home_project/Branch-Aware_Multi-Tenant-Workflow-Scheduler/CMU-1-JP2K-33005.svs"

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def check_health():
    """检查系统健康状态"""
    try:
        response = requests.get(f"{BASE_URL}/health")
        return response.status_code == 200
    except Exception:
        return False

def create_job(user_id, job_type, branch, job_name=""):
    """创建任务"""
    headers = {"X-User-ID": user_id}
    
    job_data = {
        "job_type": job_type,
        "branch": branch,
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 512,
            "overlap": 64
        }
    }
    
    print(f"\n📤 [{user_id}] 创建任务{job_name}:")
    print(f"   类型: {job_type}")
    print(f"   分支: {branch}")
    print(f"   时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    
    response = requests.post(
        f"{BASE_URL}/jobs",
        json=job_data,
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        job_id = result['job_id']
        print(f"   ✅ Job ID: {job_id}")
        return result
    else:
        print(f"   ❌ 创建失败: {response.text}")
        return None

def get_job_status(user_id, job_id):
    """获取任务状态"""
    headers = {"X-User-ID": user_id}
    
    try:
        response = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=headers)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def get_system_stats():
    """获取系统统计"""
    try:
        response = requests.get(f"{BASE_URL}/stats/system")
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None

def monitor_jobs(jobs_info, duration=30):
    """监控多个任务的执行情况"""
    print_section(f"监控任务执行（{duration}秒）")
    
    start_time = time.time()
    check_count = 0
    
    # 记录任务开始运行的时间
    job_start_times = {}
    
    while time.time() - start_time < duration:
        check_count += 1
        all_done = True
        
        print(f"\n⏱️  检查 #{check_count} - {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 80)
        
        for job_info in jobs_info:
            user_id = job_info['user_id']
            job_id = job_info['job_id']
            job_name = job_info['name']
            
            job = get_job_status(user_id, job_id)
            if job:
                status = job['status']
                progress = job.get('progress_percent', 0)
                
                # 记录任务开始时间
                if status == 'RUNNING' and job_id not in job_start_times:
                    job_start_times[job_id] = time.time()
                    print(f"🚀 [{job_name}] 开始执行! (启动时间: {datetime.now().strftime('%H:%M:%S.%f')[:-3]})")
                
                print(f"   [{job_name:15}] {status:10} - {progress:5.1f}% - User: {user_id}")
                
                if status in ['PENDING', 'RUNNING']:
                    all_done = False
        
        # 显示系统统计
        stats = get_system_stats()
        if stats:
            print(f"\n   📊 系统状态:")
            print(f"      Workers: {stats['active_workers']}/{stats['max_workers']}")
            print(f"      Active Users: {stats['active_users']}/{stats['max_active_users']}")
            print(f"      Queue Depth: {stats['queue_depth']}")
            if stats.get('per_branch_queue_depth'):
                print(f"      Per-Branch Queue: {stats['per_branch_queue_depth']}")
        
        if all_done:
            print("\n✅ 所有任务已完成!")
            break
        
        time.sleep(2)
    
    # 分析结果
    print_section("执行结果分析")
    
    if len(job_start_times) >= 2:
        start_times = sorted(job_start_times.values())
        time_diff = start_times[1] - start_times[0]
        
        print(f"\n⏱️  任务启动时间差: {time_diff:.2f} 秒")
        
        if time_diff < 3:
            print(f"✅ 任务几乎同时启动 (差异 < 3秒)")
            print(f"✅ 不同用户的同名branch可以并行执行!")
            return True
        else:
            print(f"⚠️  任务启动有明显延迟 (差异 > 3秒)")
            print(f"❌ 可能存在串行执行问题!")
            return False
    else:
        print(f"⚠️  无法判断 - 未记录到足够的启动时间")
        return None

def test_scenario_1():
    """
    场景1: 两个用户在同名branch创建任务
    预期: 应该并行执行
    """
    print_section("场景1: 同名Branch并行测试")
    print("User1 和 User2 都在 'main' branch 创建任务")
    print("预期结果: 两个任务应该并行执行（几乎同时开始）")
    
    # User 1 创建任务
    job1 = create_job("user-branch-test-1", "tissue_mask", "main", "User1-Main")
    if not job1:
        print("❌ User 1 任务创建失败")
        return False
    
    # 稍微延迟一下，确保任务已提交
    time.sleep(0.5)
    
    # User 2 创建任务（同名branch）
    job2 = create_job("user-branch-test-2", "tissue_mask", "main", "User2-Main")
    if not job2:
        print("❌ User 2 任务创建失败")
        return False
    
    # 监控执行
    jobs_info = [
        {"user_id": "user-branch-test-1", "job_id": job1['job_id'], "name": "User1-Main"},
        {"user_id": "user-branch-test-2", "job_id": job2['job_id'], "name": "User2-Main"}
    ]
    
    return monitor_jobs(jobs_info, duration=40)

def test_scenario_2():
    """
    场景2: 同一用户在不同branch创建任务
    预期: 应该并行执行
    """
    print_section("场景2: 同用户不同Branch并行测试")
    print("User1 在 'branch-a' 和 'branch-b' 创建任务")
    print("预期结果: 两个任务应该并行执行")
    
    # User 1 在 branch-a 创建任务
    job1 = create_job("user-branch-test-3", "tissue_mask", "branch-a", "User1-BranchA")
    if not job1:
        print("❌ Branch A 任务创建失败")
        return False
    
    time.sleep(0.5)
    
    # User 1 在 branch-b 创建任务
    job2 = create_job("user-branch-test-3", "tissue_mask", "branch-b", "User1-BranchB")
    if not job2:
        print("❌ Branch B 任务创建失败")
        return False
    
    # 监控执行
    jobs_info = [
        {"user_id": "user-branch-test-3", "job_id": job1['job_id'], "name": "User1-BranchA"},
        {"user_id": "user-branch-test-3", "job_id": job2['job_id'], "name": "User1-BranchB"}
    ]
    
    return monitor_jobs(jobs_info, duration=40)

def test_scenario_3():
    """
    场景3: 同一用户在同一branch创建两个任务
    预期: 应该串行执行
    """
    print_section("场景3: 同用户同Branch串行测试")
    print("User1 在 'main' branch 创建两个任务")
    print("预期结果: 两个任务应该串行执行（第二个等第一个完成）")
    
    # User 1 创建第一个任务
    job1 = create_job("user-branch-test-4", "tissue_mask", "main", "User1-Task1")
    if not job1:
        print("❌ Task 1 创建失败")
        return False
    
    time.sleep(0.5)
    
    # User 1 创建第二个任务（同branch）
    job2 = create_job("user-branch-test-4", "tissue_mask", "main", "User1-Task2")
    if not job2:
        print("❌ Task 2 创建失败")
        return False
    
    # 监控执行
    jobs_info = [
        {"user_id": "user-branch-test-4", "job_id": job1['job_id'], "name": "User1-Task1"},
        {"user_id": "user-branch-test-4", "job_id": job2['job_id'], "name": "User1-Task2"}
    ]
    
    result = monitor_jobs(jobs_info, duration=60)
    
    # 对于串行场景，启动时间差应该很大
    if result is False:
        print("✅ 任务串行执行（符合预期）")
        return True
    else:
        print("⚠️  任务可能并行了（不符合预期）")
        return False

def main():
    print_section("多租户Branch隔离测试")
    print("本测试验证修复后的Branch隔离功能")
    print("确保不同用户的同名branch可以并行执行")
    
    # 检查系统健康
    print("\n🔍 检查系统健康...")
    if not check_health():
        print("❌ 系统未就绪")
        sys.exit(1)
    print("✅ 系统就绪")
    
    results = {}
    
    # 测试场景1：不同用户同名branch（最关键）
    print("\n" + "🎯" * 40)
    results['scenario_1'] = test_scenario_1()
    time.sleep(3)
    
    # 测试场景2：同用户不同branch
    print("\n" + "🎯" * 40)
    results['scenario_2'] = test_scenario_2()
    time.sleep(3)
    
    # 测试场景3：同用户同branch（应该串行）
    print("\n" + "🎯" * 40)
    results['scenario_3'] = test_scenario_3()
    
    # 总结
    print_section("测试总结")
    
    print("\n📊 测试结果:")
    print(f"   场景1（不同用户同名branch）: {'✅ PASS' if results.get('scenario_1') else '❌ FAIL'}")
    print(f"   场景2（同用户不同branch）  : {'✅ PASS' if results.get('scenario_2') else '❌ FAIL'}")
    print(f"   场景3（同用户同branch）    : {'✅ PASS' if results.get('scenario_3') else '❌ FAIL'}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n" + "🎉" * 40)
        print("✅ 所有测试通过!")
        print("✅ 多租户Branch隔离功能正常工作!")
        print("🎉" * 40)
        return 0
    else:
        print("\n" + "⚠️ " * 40)
        print("❌ 部分测试失败，请检查实现")
        return 1

if __name__ == "__main__":
    sys.exit(main())

