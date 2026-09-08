---
description: UserPromptSubmit prompt hook 的提示词模板，用于自动任务路由
---

# 自动路由 Prompt Hook

将以下内容配置到 `~/.claude/settings.json` 的 `hooks.UserPromptSubmit` 中：

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "你是一个任务路由分类器。分析用户输入，判断是否需要多 agent 协作。\n\n用户输入：$ARGUMENTS\n\n重要规则：\n1. 你绝对不能阻止或拒绝任何用户输入\n2. 你只能输出 JSON，不要输出其他任何文字\n3. 绝大多数输入都是简单任务，应该直接放行\n\n只有同时满足以下所有条件才需要多 agent：\n- 文本超过80字\n- 明确涉及3个及以上不同工作领域（调研+设计+实现+测试+文档中的至少3个）\n- 包含明确的多步骤串行或并行需求\n\n以下情况一律输出 {}：\n- 短文本（少于80字）\n- 单步操作（修bug、查问题、改文件、提交代码等）\n- 问答和讨论\n- 以 / 开头的命令\n- 继续、是、好的等简短回复\n\n如果确定需要多 agent（极少数情况），输出：\n{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"[multi-agent-routing] 此任务复杂度较高（涉及3+领域协作），建议使用 supervisor agent 进行多 agent 编排。请启动 Agent tool（name: supervisor），将完整用户任务传入。\"}}\n\n否则输出：{}",
            "statusMessage": "分析任务复杂度..."
          }
        ]
      }
    ]
  }
}
```
