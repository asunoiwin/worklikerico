---
name: lint-baseline
description: 代码标准化基线落地 — 给一个项目接入 lint/格式/架构规则，并接进 DTL 提交门的 lint 子门(Gate 3c)。控制逻辑全局化(插件)、质量标准项目化(各仓自带)。Triggers on - 代码标准化 / lint 基线 / 接 eslint / 接 checkstyle / spotless / archunit / 提交门 lint / lint-baseline / code standardization / 接入 lint / 静态检查.
---

# lint-baseline — 代码标准化基线落地

## 这个 skill 在干嘛

把"AI 代码治理三层"落到一个具体项目：①生成前注入规则(design-gate/CLAUDE.md 已有) ②**生成中自动校验(本 skill 的重点：lint 工具拦机械型垃圾)** ③生成后收口(code-review/strict-prod-audit 已有)。

**核心分工（必须守住）**：
- **控制逻辑（"提交前必须过 lint"）→ DTL 插件全局**：已实现为 `02-gate-check.sh` 的 **Gate 3c**，按 staged diff 调项目的 `scripts/lint-staged-dispatch.sh`，无入口优雅 no-op，`DTL_DISABLE_LINT_GATE=1` 逃生。
- **质量标准（具体规则/配置）→ 项目自带**：像单元测试一样写在项目仓库里、随代码进 git。理由：绑死项目的栈/包名/版本，必须自包含(CI/Docker/同事都能跑)。
- **按栈共享基线 → 插件 `baselines/<stack>/`**：多个同栈项目复用一份；本 skill 把基线 **sync(拷贝)** 进项目，项目持有副本。

## 工具能拦 vs 拦不住（别过度承诺）

自动工具约拦 **40%** 的 AI 垃圾——机械型(命名/格式/死代码/裸类型/明显 bug/架构越界)。**语义型(冗余注释/过度防御/职责错位/巨型方法/业务语义错)拦不住**，仍靠 remove-ai-slop + code-review + ArchUnit(结构) + 人。可维护性 = 工具(机械) + ArchUnit(结构) + 人评(语义)，缺一不可。

## 按栈基线（行业标准）

| 栈 | 格式 | 规则/lint | bug 模式 | 架构 |
|---|---|---|---|---|
| Java(Spring) | Spotless(google-java-format) | Checkstyle(命名/import/禁wildcard/文件长度软阈值) | SpotBugs(高置信; Error Prone 在 Java21+Lombok 下暂不进) | ArchUnit |
| Vue3(JS) | Prettier | ESLint(flat, eslint-plugin-vue vue3-recommended; 高噪声降 warn) | — | ESLint 规则 |
| 其他(Go/Python/SQL) | gofmt/ruff/sqlfluff | golangci-lint/ruff/sqlfluff | — | — |

命名规则：Java 类 PascalCase、方法/字段 camelCase、常量 UPPER_SNAKE、包全小写、测试 *Test、枚举 UPPER_SNAKE；Vue 组件多词 PascalCase(给 App.vue 和单词路由页配例外)、props 声明 camelCase / 模板 kebab-case、emits kebab-case。

## 存量安全铁律（落地成败在此，全量推进也必守）

1. **只 gate 增量 staged diff，绝不 gate 存量**。
2. Spotless/Prettier 只 `check` 不全量 `apply`；若全量格式化 → 单独 format-only commit + 写进 `.git-blame-ignore-revs`。
3. Checkstyle/SpotBugs 用 baseline/suppressions 抑制存量，只 fail 新增。SpotBugs baseline 是 bug/class/method 级、非行级。
4. ArchUnit 用 `FreezingArchRule`：先本地生成 store 并提交，CI 禁止创建/更新 store(只报新增)。"禁裸 Map" 这类命中多的，优先**新文件强拦 / 旧核心包 frozen**，别第一天全仓强门。
5. pre-commit 只跑 staged，目标 <20s；全量 SpotBugs 放 CI。
6. **质量插件别绑默认/发版生命周期**(release 走 `mvn package -DskipTests`)：放 Maven `quality` profile，只在 quality workflow 显式调。
7. 前端加 devDeps **必须同步 package-lock.json**(release 用 `npm ci`)。

## 安全执行顺序（codex 终审确认）

1. 项目内 lint dispatch(`scripts/lint-staged-dispatch.sh` 按后缀派发)，先不接钩子/CI。
2. 固定工具版本并更新 lock(npm)/插件版本(maven)。
3. 本地验证 dispatch 对"无文件/无入口/有入口失败/有入口通过"四种都正确。
4. 加 Maven `quality` profile，不绑默认生命周期。
5. 生成并提交 Checkstyle/SpotBugs suppression + ArchUnit frozen store。
6. 加 ArchUnit，保留现有手写架构测试一轮，确认跨模块没漏扫再替换。
7. 接 git pre-commit(`scripts/install-hooks.sh` 装到 .git/hooks)，只跑 staged。
8. DTL Gate 3c 自动接管(发现 dispatch 即生效)。
9. 加 `.github/workflows/quality.yml`：PR 跑 changed-file lint + arch；master/每日跑 full SpotBugs。**不改** release/security workflow。

## 项目落地产物清单

- 前端：`eslint.config.js` `prettier.config.cjs` `stylelint.config.cjs` `.prettierignore` + package.json devDeps/scripts + 更新的 package-lock.json
- 后端：根 pom `quality` profile(spotless+checkstyle+spotbugs) + `config/checkstyle/checkstyle.xml` + `config/spotbugs/exclude.xml`
- 架构：`archunit-junit5` + `*ArchitectureTest`(各模块或专用模块) + frozen store
- 集成：`scripts/lint-staged-dispatch.sh` + `scripts/install-hooks.sh`(装 .git/hooks/pre-commit) + `.github/workflows/quality.yml` + `.git-blame-ignore-revs`
- 项目专属架构规则(随项目)：模块边界、禁裸 Map 核心包、admin 禁直连 axios、migration 危险操作白名单
