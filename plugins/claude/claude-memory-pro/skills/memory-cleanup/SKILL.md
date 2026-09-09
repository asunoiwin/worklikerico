---
name: memory-cleanup
description: 在用户明确要求时清理 Claude Memory Pro 的噪声、重复和过期记忆。
---

先检查清理范围和候选；用户授权后再调用 `memory_cleanup`。报告实际删除、合并和保留数量，不把命令成功当作数据验收。
