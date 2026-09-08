---
name: orchestrate
description: 分析任务复杂度并自动决定是否启动多 agent 协作。对复杂任务自动创建 supervisor agent 进行编排。
user-invocable: true
arguments:
  - name: task
    description: 要执行的任务描述
    required: true
---

# 多 Agent 编排启动

用户请求执行以下任务：$ARGUMENTS

## 你的工作流程

### Step 1: 复杂度分析

分析任务文本，检测以下特征并计分：

| 特征 | 信号词 | 分值 |
|------|--------|------|
| research | 调研/搜索/对比/分析 | +1 |
| planning | 设计/架构/规划/方案 | +1 |
| implementation | 开发/编写/实现/修改/构建 | +1 |
| audit | 审查/测试/验证/检查 | +1 |
| documentation | 文档/报告/手册 | +1 |
| 任务长度 > 100字 | | +1 |
| 多步骤 | 先...然后...最后 | +2 |
| 并行 | 同时/分别/各自 | +2 |

### Step 2: 路由决策

- **score < 3**: 告诉用户"任务简单，直接执行"，然后直接执行任务
- **score 3-5**: 告诉用户"中等复杂度，启动 2-3 个 agent 协作"，然后启动 supervisor agent
- **score >= 6**: 告诉用户"高复杂度，启动完整多 agent 编排"，然后启动 supervisor agent

### Step 3: 执行

对于 score >= 3 的任务：
1. 用 TaskCreate 创建总任务
2. 启动 supervisor agent（subagent_type 不指定，使用 name: "supervisor"），传入完整的任务描述和复杂度分析结果
3. 等待 supervisor 完成编排

对于 score < 3 的任务：
直接执行，不需要多 agent。

### 输出要求

先向用户报告复杂度分析结果和路由决策，然后执行。
