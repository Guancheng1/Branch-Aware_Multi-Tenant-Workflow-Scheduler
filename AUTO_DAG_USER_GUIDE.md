# 自动DAG构建用户指南

## 🎯 概述

系统现在支持**自动DAG（有向无环图）构建**功能！用户无需手动定义复杂的workflow结构，只需在创建任务时指定依赖关系，系统会自动构建workflow并管理任务执行顺序。

## ✨ 新功能特性

### 1. 任务依赖功能
- 创建任务时可以指定它依赖哪些已存在的任务
- 支持单个或多个依赖
- 系统自动验证依赖的合法性（任务存在、属于同一用户）

### 2. 自动Workflow创建
- 当创建有依赖关系的任务时，系统自动创建workflow
- 如果依赖的任务已在某个workflow中，新任务会加入同一workflow
- 可以为workflow指定自定义名称

### 3. DAG可视化
- 前端自动显示任务之间的依赖关系
- 清晰展示workflow的层级结构
- 支持查看详细的DAG信息

## 📖 使用方法

### 方法1: 通过前端UI（推荐）

#### 步骤1: 创建第一个任务
1. 点击 "Create Task" 按钮
2. 填写任务信息（类型、分支、图像路径等）
3. **不勾选**依赖选项
4. 点击 "Create Task"

#### 步骤2: 创建依赖任务
1. 再次点击 "Create Task" 按钮
2. 填写任务信息
3. ✅ **勾选 "This task depends on other tasks"**
4. 从列表中选择要依赖的任务（可多选）
5. （可选）输入 "Workflow Name"
6. 点击 "Create Task"

#### 步骤3: 查看Workflow
1. 导航到 "Workflows" 标签
2. 查看自动创建的workflow卡片
3. 点击workflow卡片查看详细信息和DAG结构

### 方法2: 通过API

#### 创建独立任务
```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "tissue_mask",
    "branch": "main",
    "image_path": "/path/to/image.svs",
    "parameters": {
      "tile_size": 1024,
      "overlap": 128
    }
  }'
```

响应会包含 `job_id`，例如：`"job_id": "abc123..."`

#### 创建依赖任务
```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "X-User-ID: user-001" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "cell_segmentation",
    "branch": "analysis",
    "image_path": "/path/to/image.svs",
    "parameters": {
      "tile_size": 1024,
      "overlap": 128
    },
    "depends_on": ["abc123..."],
    "workflow_name": "My Analysis Pipeline"
  }'
```

响应会包含：
- `job_id`: 新任务的ID
- `workflow_id`: 自动创建的workflow ID

### 方法3: 使用Python脚本

运行测试脚本查看完整示例：
```bash
python test_auto_dag.py
```

或者在你的代码中：
```python
import requests

BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "your-user-id"

# 创建第一个任务
job1 = requests.post(
    f"{BASE_URL}/jobs",
    json={
        "job_type": "tissue_mask",
        "branch": "preprocessing",
        "image_path": "/path/to/image.svs",
        "parameters": {"tile_size": 512}
    },
    headers={"X-User-ID": USER_ID}
).json()

job1_id = job1['job_id']

# 创建依赖任务
job2 = requests.post(
    f"{BASE_URL}/jobs",
    json={
        "job_type": "cell_segmentation",
        "branch": "segmentation",
        "image_path": "/path/to/image.svs",
        "parameters": {"tile_size": 1024},
        "depends_on": [job1_id],  # 依赖第一个任务
        "workflow_name": "Cell Analysis Workflow"
    },
    headers={"X-User-ID": USER_ID}
).json()

print(f"Workflow created: {job2['workflow_id']}")
```

## 🔍 实例场景

### 场景1: 简单的两步Pipeline

```
[Tissue Mask] → [Cell Segmentation]
```

1. 创建tissue mask任务
2. 创建cell segmentation任务，依赖于tissue mask
3. 系统自动：
   - 创建workflow
   - 等待tissue mask完成后才开始cell segmentation

### 场景2: 多分支Pipeline

```
               ┌→ [Cell Seg - Branch A]
[Tissue Mask] ─┤
               └→ [Cell Seg - Branch B]
```

1. 创建tissue mask任务
2. 创建cell segmentation任务A（branch: branchA），依赖tissue mask
3. 创建cell segmentation任务B（branch: branchB），依赖tissue mask
4. 系统自动：
   - 创建workflow包含3个任务
   - 等tissue mask完成后，**并行执行**两个cell segmentation任务

### 场景3: 复杂的多层Pipeline

```
[Task A] → [Task B] → [Task D]
        ↘ [Task C] ↗
```

1. 创建Task A
2. 创建Task B，依赖A
3. 创建Task C，依赖A
4. 创建Task D，依赖B和C
5. 系统自动：
   - A完成后，B和C并行执行
   - B和C都完成后，D开始执行

## 🎨 前端界面说明

### 创建任务表单
```
┌─────────────────────────────────────┐
│ Create New Task                     │
├─────────────────────────────────────┤
│ Task Type: [Cell Segmentation ▼]   │
│ Branch: [main              ]        │
│ Image Path: [/path/to/image]       │
│                                     │
│ ☑ This task depends on other tasks │  ← 勾选此项
│   └─ Select dependent tasks:       │
│       ☑ Task 1 (tissue_mask)       │  ← 选择依赖
│       ☐ Task 2 (preprocessing)     │
│                                     │
│ Workflow Name (optional):          │
│ [My Analysis Pipeline      ]       │  ← 可选的名称
│                                     │
│ [Cancel]  [Create Task]            │
└─────────────────────────────────────┘
```

### Workflow视图
显示所有workflow及其DAG结构：

```
┌──────────────────────────────────────┐
│ 🔄 Workflow                          │
│ My Analysis Pipeline                 │
│                                      │
│ DAG STRUCTURE:                       │
│ 🎯 Mask (abc123)                    │
│        ↓                             │
│ 🔬 Seg (def456)                     │
│                                      │
│ 2 nodes | 2 tasks                   │
│ Progress: ████████░░ 85%            │
└──────────────────────────────────────┘
```

## ⚙️ API字段说明

### JobCreate Schema

```python
{
  "job_type": str,              # 任务类型: "cell_segmentation" 或 "tissue_mask"
  "branch": str,                # 分支名称（同分支任务串行执行）
  "image_path": str,            # 图像文件路径
  "parameters": dict,           # 任务参数
  "depends_on": list[str],      # 【新增】依赖的job_id列表
  "workflow_name": str | None   # 【新增】可选的workflow名称
}
```

### 响应字段

创建有依赖的任务时，响应会包含：
```json
{
  "job_id": "uuid-of-new-job",
  "workflow_id": "uuid-of-workflow",  // 自动创建的workflow ID
  "user_id": "your-user-id",
  "status": "PENDING",
  ...
}
```

## 🚨 注意事项

### 1. 依赖验证
- 依赖的任务必须存在
- 依赖的任务必须属于同一用户
- 不能创建循环依赖

### 2. Branch行为
- 同一branch内的任务仍然串行执行
- 不同branch的任务可以并行执行
- 依赖关系会覆盖branch规则（依赖必须先完成）

### 3. Workflow命名
- 如果不指定workflow_name，系统自动生成名称
- 多个任务可以使用相同的workflow_name来组织在一起
- 建议为相关任务使用有意义的workflow名称

### 4. 执行顺序
系统会根据DAG自动确定执行顺序：
1. 优先执行没有依赖的任务（根节点）
2. 等待依赖完成后执行下一层任务
3. 遵守branch的串行规则
4. 在满足条件的情况下最大化并行度

## 🔧 故障排查

### 问题1: "Dependent job not found"
**原因**: 指定的依赖任务不存在
**解决**: 
- 确认job_id正确
- 先创建被依赖的任务

### 问题2: "Cannot depend on job from another user"
**原因**: 尝试依赖其他用户的任务
**解决**: 只能依赖自己的任务

### 问题3: Workflow没有自动创建
**原因**: 可能没有指定depends_on或workflow_name
**解决**: 
- 确保至少指定了depends_on或workflow_name
- 检查API请求格式是否正确

### 问题4: 前端看不到依赖选项
**原因**: 可能是缓存问题
**解决**:
- 刷新页面（Ctrl+Shift+R或Cmd+Shift+R）
- 清除浏览器缓存

## 📊 对比：旧方式 vs 新方式

### 旧方式（手动定义DAG）
```json
POST /api/v1/workflows
{
  "name": "My Workflow",
  "nodes": [
    {
      "node_id": "node_1",
      "job_type": "tissue_mask",
      "depends_on": []
    },
    {
      "node_id": "node_2",
      "job_type": "cell_segmentation",
      "depends_on": ["node_1"]  // 需要手动管理node_id
    }
  ]
}
```
**缺点**: 复杂、需要理解DAG、手动管理ID

### 新方式（自动构建DAG）
```json
POST /api/v1/jobs
{
  "job_type": "cell_segmentation",
  "branch": "main",
  "image_path": "...",
  "depends_on": ["existing-job-id"]  // 直接使用job_id
}
```
**优点**: 简单、直观、自动管理

## 🎓 最佳实践

1. **任务命名**: 虽然系统不要求命名任务，但建议在workflow_name中使用有意义的名称

2. **分支规划**: 合理使用branch来控制并行度
   - 同类任务使用同一branch（串行）
   - 不同类任务使用不同branch（并行）

3. **依赖最小化**: 只指定必要的依赖，让系统自动优化并行度

4. **先测试后部署**: 使用小图像测试workflow逻辑，确认无误后再处理大图像

5. **监控进度**: 在Workflows视图中实时监控任务执行情况

## 🚀 快速开始

1. 启动系统:
   ```bash
   python main.py
   ```

2. 打开浏览器访问: `http://localhost:8000`

3. 创建第一个任务（无依赖）

4. 创建第二个任务，勾选"依赖其他任务"，选择第一个任务

5. 切换到"Workflows"标签查看自动创建的DAG

6. 享受自动化的任务编排！🎉

## 📚 更多资源

- [完整API文档](http://localhost:8000/docs)
- [测试脚本](./test_auto_dag.py)
- [架构设计文档](./DAG_IMPROVEMENT_DESIGN.md)
- [原始需求](./UPenn_TissueLab_Hiring%20(1).md)

---

**有问题或建议？** 欢迎提Issue或联系开发团队！

