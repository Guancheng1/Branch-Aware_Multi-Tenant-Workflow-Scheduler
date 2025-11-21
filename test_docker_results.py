#!/usr/bin/env python3
"""
测试Docker环境中的结果文件访问
"""
import requests
import json
import sys

# Docker环境的服务器地址
BASE_URL = "http://localhost:8000"

def test_api_health():
    """测试API是否可访问"""
    print("🏥 测试API健康状况...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"  ✅ API正常运行")
            return True
        else:
            print(f"  ❌ API异常，状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 无法连接到服务器: {e}")
        print(f"  提示: 确保Docker容器正在运行并且端口8000已映射")
        return False

def get_completed_jobs():
    """获取已完成的任务列表"""
    print("\n📋 获取已完成的任务...")
    try:
        # 使用docker测试用户
        headers = {'X-User-ID': 'docker-test-final'}
        response = requests.get(f"{BASE_URL}/api/v1/jobs", headers=headers, timeout=5)
        
        if response.status_code == 200:
            jobs = response.json()
            completed_jobs = [j for j in jobs if j.get('status') == 'SUCCEEDED']
            print(f"  ✅ 找到 {len(completed_jobs)} 个已完成的任务")
            return completed_jobs
        else:
            print(f"  ❌ 获取任务失败，状态码: {response.status_code}")
            return []
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return []

def test_result_files(job):
    """测试单个任务的结果文件访问"""
    user_id = job.get('user_id')
    job_id = job.get('job_id')
    
    print(f"\n🔍 测试任务 {job_id[:8]}... 的结果文件")
    print(f"   用户ID: {user_id}")
    print(f"   任务状态: {job.get('status')}")
    
    # 构建结果文件路径
    json_path = f"/results/{user_id}/{job_id}/segmentation_results.json"
    image_path = f"/results/{user_id}/{job_id}/visualization.jpg"
    
    success_count = 0
    
    # 测试JSON文件
    print(f"\n  📄 测试JSON文件...")
    json_url = BASE_URL + json_path
    print(f"     URL: {json_url}")
    try:
        response = requests.get(json_url, timeout=10)
        if response.status_code == 200:
            print(f"     ✅ JSON文件访问成功!")
            data = response.json()
            print(f"     📊 图像尺寸: {data.get('image_width')} x {data.get('image_height')}")
            print(f"     📊 检测细胞数: {data.get('total_cells')}")
            success_count += 1
        else:
            print(f"     ❌ 失败! 状态码: {response.status_code}")
            print(f"     响应: {response.text[:200]}")
    except Exception as e:
        print(f"     ❌ 错误: {e}")
    
    # 测试图像文件
    print(f"\n  🖼️  测试图像文件...")
    image_url = BASE_URL + image_path
    print(f"     URL: {image_url}")
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            print(f"     ✅ 图像文件访问成功!")
            print(f"     📦 文件大小: {len(response.content) / 1024:.2f} KB")
            print(f"     🎨 Content-Type: {response.headers.get('content-type')}")
            success_count += 1
        else:
            print(f"     ❌ 失败! 状态码: {response.status_code}")
    except Exception as e:
        print(f"     ❌ 错误: {e}")
    
    return success_count == 2

def test_static_files():
    """测试静态文件访问"""
    print(f"\n📁 测试静态文件访问...")
    
    static_url = f"{BASE_URL}/static/index.html"
    print(f"  测试: {static_url}")
    try:
        response = requests.get(static_url, timeout=5)
        if response.status_code == 200:
            print(f"  ✅ 静态文件可访问")
            return True
        else:
            print(f"  ❌ 失败! 状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        return False

def main():
    print("=" * 60)
    print("🐳 Docker环境结果文件访问测试")
    print("=" * 60)
    print(f"服务器地址: {BASE_URL}\n")
    
    # 1. 测试API健康状况
    if not test_api_health():
        print("\n❌ 服务器未运行，退出测试")
        sys.exit(1)
    
    # 2. 测试静态文件
    test_static_files()
    
    # 3. 获取已完成的任务
    completed_jobs = get_completed_jobs()
    
    if not completed_jobs:
        print("\n⚠️  没有找到已完成的任务")
        print("   提示: 请先运行一个任务并等待完成")
        
        # 提供创建测试任务的示例代码
        print("\n💡 创建测试任务示例:")
        print("   curl -X POST http://localhost:8000/api/v1/jobs \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -H 'X-User-ID: docker-test-final' \\")
        print("     -d '{")
        print('       "job_type": "cell_segmentation",')
        print('       "branch": "main",')
        print('       "image_path": "CMU-1-JP2K-33005.svs",')
        print('       "parameters": {"tile_size": 1024, "overlap": 128}')
        print("     }'")
        sys.exit(0)
    
    # 4. 测试每个已完成任务的结果文件
    print(f"\n{'=' * 60}")
    success_count = 0
    for i, job in enumerate(completed_jobs[:3], 1):  # 只测试前3个
        print(f"\n任务 {i}/{min(len(completed_jobs), 3)}")
        print("-" * 60)
        if test_result_files(job):
            success_count += 1
    
    # 5. 总结
    print(f"\n{'=' * 60}")
    print("📊 测试总结")
    print("=" * 60)
    print(f"已完成任务数: {len(completed_jobs)}")
    print(f"测试任务数: {min(len(completed_jobs), 3)}")
    print(f"成功访问结果: {success_count}/{min(len(completed_jobs), 3)}")
    
    if success_count > 0:
        print("\n✅ 结果文件可以正常访问!")
        print("\n💡 下一步:")
        print("   1. 在浏览器打开: http://localhost:8000")
        print("   2. 进入「任务管理」页面")
        print("   3. 点击已完成的任务")
        print("   4. 在弹窗中点击「查看结果」按钮")
    else:
        print("\n❌ 结果文件访问失败!")
        print("\n🔧 排查建议:")
        print("   1. 检查Docker容器中results目录是否有文件")
        print("   2. 检查main.py中是否正确挂载了/results目录")
        print("   3. 重启Docker容器后再试")

if __name__ == "__main__":
    main()

