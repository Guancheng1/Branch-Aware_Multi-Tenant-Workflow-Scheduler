#!/usr/bin/env python3
"""
测试自动DAG创建功能

该脚本测试新的Job依赖功能：
1. 创建一个独立的tissue mask任务
2. 创建一个依赖于tissue mask的cell segmentation任务
3. 验证系统自动创建workflow并构建DAG
"""
import requests
import json
import time
import sys

BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "test-auto-dag-user"
IMAGE_PATH = "/Users/Donytu/Desktop/take_home_project/Branch-Aware_Multi-Tenant-Workflow-Scheduler/CMU-1-JP2K-33005.svs"

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def check_health():
    """检查系统健康状态"""
    print_section("检查系统健康")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ 系统健康检查通过")
            return True
        else:
            print(f"❌ 系统健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到系统: {e}")
        return False

def create_job(job_data):
    """创建任务"""
    headers = {"X-User-ID": USER_ID}
    
    print(f"\n📤 创建任务...")
    print(f"类型: {job_data['job_type']}")
    print(f"分支: {job_data['branch']}")
    if job_data.get('depends_on'):
        print(f"依赖: {job_data['depends_on']}")
    if job_data.get('workflow_name'):
        print(f"工作流名称: {job_data['workflow_name']}")
    
    response = requests.post(
        f"{BASE_URL}/jobs",
        json=job_data,
        headers=headers
    )
    
    if response.status_code == 200:
        result = response.json()
        job_id = result['job_id']
        workflow_id = result.get('workflow_id')
        
        print(f"✅ 任务创建成功!")
        print(f"   Job ID: {job_id}")
        if workflow_id:
            print(f"   Workflow ID: {workflow_id}")
            print(f"   🎉 系统自动创建了workflow!")
        return result
    else:
        print(f"❌ 任务创建失败!")
        print(f"   状态码: {response.status_code}")
        print(f"   错误: {response.text}")
        return None

def get_workflows():
    """获取用户的所有workflows"""
    headers = {"X-User-ID": USER_ID}
    
    response = requests.get(f"{BASE_URL}/workflows", headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ 获取workflows失败: {response.text}")
        return []

def display_workflow_info(workflow):
    """显示workflow信息"""
    print(f"\n🔄 Workflow: {workflow['name']}")
    print(f"   ID: {workflow['workflow_id']}")
    print(f"   状态: {workflow['status']}")
    print(f"   节点数: {len(workflow['nodes'])}")
    print(f"   任务数: {len(workflow['job_ids'])}")
    print(f"   进度: {workflow['progress_percent']:.1f}%")
    
    print(f"\n   📊 DAG结构:")
    for node in workflow['nodes']:
        node_id = node['node_id'].replace('job_', '')[:8]
        print(f"      - [{node['job_type']}] {node_id}")
        if node['depends_on']:
            for dep in node['depends_on']:
                dep_id = dep.replace('job_', '')[:8]
                print(f"          └─ depends on: {dep_id}")

def main():
    print_section("自动DAG创建功能测试")
    print("本测试将演示如何通过Job依赖自动构建Workflow DAG")
    
    # 检查系统健康
    if not check_health():
        sys.exit(1)
    
    # 步骤1: 创建第一个独立任务（Tissue Mask）
    print_section("步骤1: 创建独立的Tissue Mask任务")
    
    job1_data = {
        "job_type": "tissue_mask",
        "branch": "preprocessing",
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 512,
            "overlap": 64
        }
    }
    
    job1 = create_job(job1_data)
    if not job1:
        print("❌ 第一个任务创建失败，终止测试")
        sys.exit(1)
    
    job1_id = job1['job_id']
    
    # 等待一下，确保任务已被系统接受
    time.sleep(2)
    
    # 步骤2: 创建依赖于第一个任务的第二个任务（Cell Segmentation）
    print_section("步骤2: 创建依赖于Task 1的Cell Segmentation任务")
    print(f"此任务将依赖于任务: {job1_id}")
    
    job2_data = {
        "job_type": "cell_segmentation",
        "branch": "segmentation",
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 1024,
            "overlap": 128
        },
        "depends_on": [job1_id],  # 依赖第一个任务
        "workflow_name": "自动创建的分析Pipeline"  # 指定workflow名称
    }
    
    job2 = create_job(job2_data)
    if not job2:
        print("❌ 第二个任务创建失败，终止测试")
        sys.exit(1)
    
    # 步骤3: 验证workflow是否自动创建
    print_section("步骤3: 验证Workflow自动创建")
    
    workflows = get_workflows()
    
    if len(workflows) == 0:
        print("❌ 没有找到workflow，自动创建可能失败")
        sys.exit(1)
    
    print(f"✅ 找到 {len(workflows)} 个workflow(s)")
    
    for workflow in workflows:
        display_workflow_info(workflow)
    
    # 步骤4: 创建第三个任务，依赖于第二个任务，加入同一个workflow
    print_section("步骤4: 创建第三个任务，扩展现有workflow")
    
    job2_id = job2['job_id']
    
    job3_data = {
        "job_type": "cell_segmentation",
        "branch": "analysis",
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 1024,
            "overlap": 128
        },
        "depends_on": [job2_id],  # 依赖第二个任务
        "workflow_name": "自动创建的分析Pipeline"  # 同一个workflow名称
    }
    
    job3 = create_job(job3_data)
    if not job3:
        print("⚠️ 第三个任务创建失败")
    
    # 再次获取workflows，看是否更新
    time.sleep(1)
    workflows = get_workflows()
    
    print(f"\n📊 最终Workflow状态:")
    for workflow in workflows:
        display_workflow_info(workflow)
    
    # 步骤5: 测试创建一个多依赖的任务
    print_section("步骤5: 创建有多个依赖的任务")
    
    job4_data = {
        "job_type": "cell_segmentation",
        "branch": "final",
        "image_path": IMAGE_PATH,
        "parameters": {
            "tile_size": 512,
            "overlap": 64
        },
        "depends_on": [job1_id, job2_id],  # 依赖多个任务
        "workflow_name": "多依赖测试Workflow"
    }
    
    job4 = create_job(job4_data)
    if job4:
        print("✅ 多依赖任务创建成功")
    
    # 最终结果
    print_section("测试总结")
    
    workflows = get_workflows()
    print(f"✅ 共创建了 {len(workflows)} 个workflow(s)")
    print(f"✅ 自动DAG构建功能测试完成")
    print(f"\n💡 提示:")
    print(f"   - 打开前端界面查看workflow视图")
    print(f"   - 在创建任务时勾选'依赖其他任务'即可使用此功能")
    print(f"   - 系统会自动根据依赖关系构建DAG")
    
    print(f"\n🌐 访问前端: http://localhost:8000")
    print(f"   导航到 'Workflows' 标签查看创建的DAG")

if __name__ == "__main__":
    main()

