# DAG自动构建设计方案

## 🎯 目标

简化用户创建工作流的方式，从手动定义完整DAG结构改为：
1. 创建job时可选地指定依赖关系
2. 系统自动将有依赖关系的jobs组织成workflow
3. 前端提供直观的界面添加job和依赖

## 📋 当前问题

当前实现要求用户手动定义完整的workflow结构：
```json
{
  "name": "My Workflow",
  "nodes": [
    {
      "node_id": "node_1",
      "job_type": "tissue_mask",
      "depends_on": []  // 需要手动指定依赖
    },
    {
      "node_id": "node_2",
      "job_type": "cell_segmentation",
      "depends_on": ["node_1"]  // 需要手动管理node_id
    }
  ]
}
```

**问题：**
- 用户需要理解DAG概念
- 需要手动管理node_id和依赖关系
- 前端没有对应的UI支持
- 不符合"简单易用"的原则

## 🚀 改进方案

### 方案A：Job级别的依赖（推荐）

**核心思路：** 创建job时可以指定它依赖哪些已存在的jobs

#### 1. 数据模型改进

```python
class JobCreate(BaseModel):
    """创建任务请求"""
    job_type: JobType
    branch: str
    image_path: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list, description="依赖的job_id列表")
    workflow_name: Optional[str] = Field(None, description="可选的workflow名称，用于分组")
```

#### 2. API行为

**创建独立job（无依赖）：**
```json
POST /api/v1/jobs
{
  "job_type": "tissue_mask",
  "branch": "main",
  "image_path": "...",
  "parameters": {...}
}
```

**创建有依赖的job（自动创建workflow）：**
```json
POST /api/v1/jobs
{
  "job_type": "cell_segmentation",
  "branch": "branch1",
  "image_path": "...",
  "depends_on": ["job-uuid-1"],  // 依赖之前创建的job
  "workflow_name": "My Cell Analysis"  // 可选
}
```

#### 3. 系统自动行为

- 当创建第一个有依赖的job时，系统自动创建workflow
- 将依赖的job和新job都加入workflow
- 自动构建DAG结构
- 同一workflow内的jobs自动关联

#### 4. 前端UI改进

**创建Job表单添加：**
```
┌─────────────────────────────────────┐
│ Create New Task                     │
├─────────────────────────────────────┤
│ Task Type: [Cell Segmentation ▼]   │
│ Branch: [main              ]        │
│ Image Path: [/path/to/image]       │
│                                     │
│ ☐ This task depends on other tasks │
│   └─ Select dependent tasks:       │
│       [Show my recent tasks ▼]     │
│       ☐ Task 1 (tissue_mask)       │
│       ☐ Task 2 (preprocessing)     │
│                                     │
│ Workflow Name (optional):          │
│ [My Analysis Pipeline      ]       │
│                                     │
│ [Cancel]  [Create Task]            │
└─────────────────────────────────────┘
```

### 方案B：工作流模板（可选扩展）

提供预定义的workflow模板：

```json
POST /api/v1/workflows/from-template
{
  "template": "cell_analysis_pipeline",
  "image_path": "...",
  "parameters": {...}
}
```

系统自动创建包含多个job的完整workflow：
1. Tissue Mask
2. Cell Segmentation (depends on 1)
3. Post-processing (depends on 2)

## 🔧 实现步骤

### Phase 1: 后端改进
1. ✅ 修改 `JobCreate` schema，添加 `depends_on` 和 `workflow_name` 字段
2. ✅ 修改 `create_job` API，检测依赖关系
3. ✅ 实现自动workflow创建逻辑
4. ✅ 验证依赖的job存在且属于同一用户

### Phase 2: 前端改进
1. ✅ 在创建job表单中添加"依赖选择"功能
2. ✅ 实现job选择器（显示用户的所有已完成/运行中的jobs）
3. ✅ 添加workflow名称输入（可选）
4. ✅ 在workflow视图中显示DAG结构（可视化）

### Phase 3: 可视化增强
1. 🔄 使用图形库（如 D3.js, Cytoscape.js）显示DAG
2. 🔄 支持拖拽添加job到workflow
3. 🔄 实时显示依赖关系箭头

## 📊 对比

| 特性 | 当前实现 | 改进方案A |
|------|---------|-----------|
| 用户需要理解DAG | ✅ 是 | ❌ 否 |
| 手动管理node_id | ✅ 是 | ❌ 否 |
| 前端UI支持 | ❌ 无 | ✅ 有 |
| API调用复杂度 | 高 | 低 |
| 自动workflow创建 | ❌ 否 | ✅ 是 |
| 适合一般用户 | ❌ 否 | ✅ 是 |

## 🎓 符合原始要求

根据 take-home challenge 要求：
1. ✅ "Allow users to define workflows" - 用户通过简单方式定义
2. ✅ "Branch-Aware Scheduling" - branch逻辑保持不变
3. ✅ "Multi-Tenant Isolation" - 自动验证依赖job的所有权
4. ✅ 更符合"易用性"原则
5. ✅ 参考OpenAI Agent Builder的直观设计理念

## 🚦 实施建议

**优先级：**
1. 🔥 高优先级：方案A - Job级别依赖（简单且实用）
2. 🔄 中优先级：前端UI改进
3. ⭐ 低优先级：方案B - 工作流模板（锦上添花）

**时间估计：**
- 后端改进：2-3小时
- 前端基础UI：3-4小时
- DAG可视化：4-6小时（可选）

