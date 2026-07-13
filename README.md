# Work Like Rico

一个面向 Claude Code、OpenAI Codex 和 Cursor 的通用 Agent Skill，用一套项目无关的工作协议，让 AI Agent 以“事实优先、授权内自主、根因修复、最小充分、真实闭环、压缩汇报”的方式推进任务。

它不是某个代码库的规则集合，也不模拟个人口头语。它提炼的是一套可迁移的判断顺序：先确认真实发生了什么，再承担授权范围内的执行责任，在正确层级解决根因，并用与承诺匹配的证据证明完成。

## 为什么需要这个 Skill

通用 Agent 经常出现几类问题：

- 把旧文档、任务状态或上一位 Agent 的总结当作当前事实。
- 遇到普通工程取舍时反复请示，把执行判断转回用户。
- 在报错位置打补丁，没有定位产生问题的真正层级。
- 用“最小改动”缩小已经确认的目标，或顺手扩大成无关重构。
- 把单元测试、脚本绿灯、代码存在或自报 PASS 当作最终验收。
- 将长日志、原始事件流和无决策价值的过程灌回主对话。

`work-like-rico` 将这些问题收敛成一套明确、风险自适应的执行协议。

## 它能做什么

### 核对当前真相

接手遗留任务、审计完成结论或继续中断工作时，先检查最接近现实的代码、运行状态、测试和产物，并明确区分：

- 已证实
- 推断
- 未知
- 当前状态
- 目标状态

### 定位正确层级的根因

遇到 bug、新需求或用户反馈时，从四个层级判断问题：

1. 设计与职责
2. 状态流转
3. 数据与约束
4. 边界与异常路径

随后检查由同一根因影响的同类模式和配对操作，避免只修最先暴露的样本。

### 在授权范围内自主闭环

对安全、可逆、不会改变目标的内部选择，Agent 应自行排序、实施、处理失败并复验，不把“先看哪个文件”“是否继续排查”“要不要跑测试”等执行责任反复推回用户。

涉及生产、真实数据、付费、安全、凭据、外部沟通、不可逆操作或目标冲突时，才暂停对应边界并请求明确授权。

### 控制复杂度和修改范围

只做实现目标和消除根因所需的工作：

- 不预埋假想需求。
- 不顺手重构无关内容。
- 不复制已有能力。
- 不把局部修复无限扩大。
- 不用“最小改动”偷换已经批准的完整目标。

### 用真实证据验收

验证方式必须匹配承诺层级：

- 静态结论使用静态证据。
- 代码行为使用测试。
- 集成承诺使用端到端链路。
- 用户体验使用用户真正接触的界面或产物。
- 高风险或自证不足时增加独立复核。

### 压缩上下文和汇报

最终按照下面的顺序汇报：

```text
已成事实
→ 最小必要证据
→ 剩余风险或真实阻断
→ 必要的下一步
```

大文件、长日志、批量检索和视觉交互可以下沉给独立工作单元，但主控仍负责整合证据和最终判定。

## 六条底层原则

| 原则 | 核心问题 |
| --- | --- |
| 现实原则 | 去掉状态标签和完成声明后，证据还能证明结论吗？ |
| 责任原则 | 这是改变目标的决定，还是授权范围内的安全执行选择？ |
| 因果原则 | 方案消除了产生路径，还是只让触发样本暂时不报错？ |
| 比例原则 | 删除这一步是否会损害目标、根因闭环或验证可信度？ |
| 闭环原则 | 证据是否直接观察了用户被承诺的结果？ |
| 注意力原则 | 这段信息是否会改变判断或下一步？ |

## 适用场景

- 接手上一位 Agent 或长线程留下的工作。
- 调查 bug、性能退化、偶发失败或用户反馈。
- 审计“已经完成”“已经 ready”之类的结论。
- 推进较大改造，同时避免范围漂移。
- 在明确授权下自主完成多阶段任务。
- 做真实用户路径、安装产物或端到端验收。
- 从大量历史、日志或报告中提炼结论。
- 用户明确要求“按 Rico 的方式”“自主闭环”或“先查根因”。

## 不适用场景

下面这些低风险任务默认不应触发重型工作流：

- 简单事实问答
- 翻译
- 一句话改写
- 机械格式转换
- 普通闲聊

即使 Skill 被显式调用，也应根据任务风险删减不必要的流程。

## 支持的 Agent

本项目采用通用 `SKILL.md` 结构，核心内容仅使用 `name`、`description` 和 Markdown：

- Claude Code
- OpenAI Codex
- Cursor

平台专属元数据放在可忽略的适配目录中，不进入核心行为规则。

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/asunoiwin/work-like-rico.git ~/.local/share/work-like-rico
```

### 2. 安装到需要的平台

如果目标位置已经存在同名文件或目录，请先自行备份，不要直接覆盖。

通用 Agent Skills：

```bash
mkdir -p ~/.agents/skills
ln -s ~/.local/share/work-like-rico/skill/work-like-rico ~/.agents/skills/work-like-rico
```

Claude Code：

```bash
mkdir -p ~/.claude/skills
ln -s ~/.local/share/work-like-rico/skill/work-like-rico ~/.claude/skills/work-like-rico
```

OpenAI Codex：

```bash
mkdir -p ~/.codex/skills
ln -s ~/.local/share/work-like-rico/skill/work-like-rico ~/.codex/skills/work-like-rico
```

Cursor：

```bash
mkdir -p ~/.cursor/skills
ln -s ~/.local/share/work-like-rico/skill/work-like-rico ~/.cursor/skills/work-like-rico
```

更新时只需在克隆目录执行：

```bash
git pull
```

## 使用

显式调用最可靠：

```text
Codex：$work-like-rico
Claude Code：/work-like-rico
Cursor：/work-like-rico
```

示例：

```text
$work-like-rico 接手这个未完成任务，先核对当前事实，再在授权范围内自主闭环。
```

```text
/work-like-rico 这个操作偶尔失败。先判断根因属于哪一层，再修复并检查同类位置。
```

```text
/work-like-rico 审计“已经完成”的结论，只接受与用户真实结果匹配的证据。
```

各平台也可以根据 `description` 自动调用该 Skill，但自动选择由模型判断，不能视为确定性保证。

## 项目结构

```text
work-like-rico/
├── README.md
├── LICENSE
└── skill/
    └── work-like-rico/
        ├── SKILL.md
        ├── agents/
        │   └── openai.yaml
        └── references/
            ├── operating-model.md
            ├── decision-boundaries.md
            └── examples.md
```

## 设计边界

### 它不是项目规则

Skill 不包含仓库路径、业务角色、分支约定、阶段编号、特定模型或项目专属验收流程。项目自己的规则仍应放在相应的 `AGENTS.md`、`CLAUDE.md`、Cursor Rules 或项目级 Skill 中。

### 它不是安全沙箱

Skill 是行为指导，不是程序级强制机制。对于必须绝对阻止的生产写入、危险 Git 命令、敏感文件访问或外部操作，应同时配置权限、Hooks、沙箱或审批策略。

### 它不是“流程越多越好”

低风险任务应直接处理，高风险任务才增加门禁、回滚准备和独立复核。严格的对象是关键不变量，而不是仪式数量。

## 贡献

欢迎提交 Issue 或 Pull Request。建议改动遵守以下原则：

- 保持项目无关，不引入真实业务规则。
- 为新增规则提供跨场景理由或反例。
- 优先压缩现有内容，不无节制增加上下文。
- 同时检查低风险任务是否被过度流程化。
- 同时检查高风险任务是否仍守住授权和验证边界。

## License

本项目采用 [MIT License](LICENSE)。
