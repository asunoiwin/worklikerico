---
name: remove-ai-slop
description: 清理 AI 生成痕迹（slop）—— 冗余注释 / 过度防御 try-catch / 类型逃逸 / 单次使用变量 / 与文件风格不一致处。只清不重构、不拆方法、不评架构。是 design-test-loop 插件的"清理环"——git commit 前先清 slop 再自审。Triggers on - remove-ai-slop / 清理 slop / AI 痕迹 / 删冗余注释 / 提交前清理 / deslop / 屎山清理 / code slop.
---

# remove-ai-slop — 清掉 AI 写代码的痕迹

## 这个 skill 在干嘛

AI 生成的代码常带一眼能认出的"机器味"：废话注释、为不可能场景写的防御、声明完只用一次的临时变量、和全文风格打架的写法。
这个 skill 只做一件事：**把这些 slop 揪出来清掉**。它**不重构、不拆方法、不评架构**——边界极窄，所以零误伤。

插件会在你跑 `git commit` 前检查输出里有没有清理痕迹，没有就提示先清一遍再提交（清理 → 自审 → commit）。

## 核心提示词（原文，严格按此范围工作）

> Remove code slop. Use when cleaning up AI-generated code. Check the changes and remove all AI generated slop introduced. This includes:
> - Extra comments that a human wouldn't add or is inconsistent with the rest of the file (useful doc comments are good to keep)
> - Extra defensive checks or try/catch blocks that are abnormal for that area of the codebase (especially if called by trusted/validated codepaths)
> - Casts to any to get around type issues
> - Variables that are only used a single time right after declaration, preferring inlining
> - Any other style inconsistent with the file
>
> Report at the end with a 1-3 sentence summary.

## 边界（必须守住，这是它最大的价值）

- 只看 **本次改动（diff）** 引入的痕迹，不动文件里既有的历史代码。
- **风格一致 ≠ slop**：某段防御 / 类型转换若是该文件/该区域一贯的写法，就保留，不要清。判据是"对这块代码是否反常"。
- **有信息量的注释保留**：版本追溯、变更原因、业务约束说明都不是 slop。
- **不拆方法、不抽公共逻辑、不改语义、不评架构**——那是 simplify / code-review 的事，不是这里的事。
- 清理只动该动的；clean 后逐条确认"是否改变行为"，只清纯粹无行为影响的。

## 检测范围速查

| 类型 | 清 | 不清 |
|---|---|---|
| 注释 | 机器生成的套话、假 `@param`、和方法名重复的废话 | 业务说明、版本追溯、变更原因 |
| try-catch | 对本区域反常的多余防御（上游已校验还兜） | 与全文一致的副作用隔离防御 |
| 类型转换 | 为绕类型检查的 `as any` 之流 | 从 Map/Object 取值的常规强转 |
| 变量 | 声明后只用一次、可直接内联的 | 后续多处 set/get 的临时对象 |

## 输出格式（中文）

1. **发现清单**：每条 = `[位置 file:行号]` + `[类型]` + `[为什么是 slop]` + `[清理后是否破坏行为]`
2. **范围声明**：明确写出哪些东西"按边界不动"（防止越权清理）
3. **总结**：1-3 句

**结尾必须带这行标记**（插件靠它识别清理环已走过）：

```
remove-ai-slop：已清理（或：本次改动无 slop 可清）
```
