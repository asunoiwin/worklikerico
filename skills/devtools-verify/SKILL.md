---
name: devtools-verify
description: 用 Chrome DevTools MCP 读 DOM / 网络请求 / console 日志做结构化 UI 断言，替代部分 playwright 截图验证。比 playwright 快（复用现有 Chrome 无冷启）、比截图准（直接读元素属性而非肉眼对图）。Triggers on - devtools-verify / UI 验证 / 按钮验证 / DOM 断言 / chrome devtools / 界面检查 / 元素状态.
---

# devtools-verify — 用结构化数据验证 UI

## 为什么有这个 skill

playwright 截图验证的两个老问题：
1. **慢**：每次启动浏览器要 5-10 秒冷启
2. **不准**：靠肉眼看截图判断"按钮是不是禁用了"——人眼会看错，AI 通过截图判断更不准

devtools-verify 用 Chrome DevTools MCP 走开发者协议**直接读 DOM**：拿到的是结构化数据（`<button disabled>` 的 disabled 属性是 true 还是 false），不依赖截图。

## 跟 playwright-audit 的分工

| 用途 | 推荐工具 |
|---|---|
| 开发期快速验证（边写边看效果） | **devtools-verify** |
| 一测（dev 环境穷尽场景） | **devtools-verify** + playwright（混用） |
| 二测（独立 agent 复现一测预期） | **playwright-audit**（保持现状） |
| 视觉回归（截图对比 baseline） | playwright |
| 用户视角端到端流程 | playwright |

简单说：**开发期和一测优先用 devtools-verify**，二测和视觉回归用 playwright。

## 安装前提

需要在 `~/.mcp.json` 装 Chrome DevTools MCP。**如果还没装，第一次触发本 skill 时先提示用户安装步骤，不要自动改 .mcp.json**。

推荐配置（写到 mcpServers 段下）：

```json
"chrome-devtools": {
  "command": "npx",
  "args": ["-y", "chrome-devtools-mcp@latest"]
}
```

装好后会出现一批 `mcp__chrome-devtools__*` 工具：
- `list_pages` / `new_page` — 管理 tab
- `evaluate_script` — 在页面跑 JS 拿数据
- `take_snapshot` — 抓 DOM 树（accessibility tree）
- `get_network_requests` — 看接口调用
- `get_console_messages` — 看 console 报错
- `click` / `fill` — 操作页面

## 验证流程模板

### 场景 1：按钮状态验证（最常翻车的场景）

```javascript
// 用 evaluate_script 跑一段 JS 直接读 DOM
const btn = document.querySelector('[data-testid="submit-btn"]');
return {
  exists: !!btn,
  disabled: btn?.disabled,
  text: btn?.innerText,
  classes: btn?.className,
  visible: btn?.offsetParent !== null
};
```

断言："按钮文字是「提交」、disabled=false、可见"——而不是看截图说"按钮看起来正常"。

### 场景 2：列表数据验证

```javascript
return Array.from(document.querySelectorAll('[data-testid="list-item"]'))
  .map(el => ({ text: el.innerText, id: el.dataset.id }));
```

断言："列表 5 条、第一条 id=123、文字含「新订单」"——结构化对照。

### 场景 3：网络请求验证

```javascript
// 配合 get_network_requests 看接口调用
// 验证："点击按钮后调用了 POST /api/orders、返回 200"
```

### 场景 4：console 报错检查

每个 UI 验证流程末尾都跑一次 `get_console_messages`，没 error/warning 才算通过。

## 写测试断言的标准

断言必须是**结构化布尔判定**，不是"看起来 OK"。

| 反面 | 正面 |
|---|---|
| 按钮看起来能点 | `button.disabled === false` |
| 列表显示正常 | `items.length === 5 && items[0].id === '123'` |
| 弹窗弹出来了 | `document.querySelector('.modal').style.display !== 'none'` |
| 没报错 | `consoleMessages.filter(m => m.level === 'error').length === 0` |

## 在 design-test-loop 插件中的位置

一测阶段（IMPL_DONE → T1_PASS）开始时，主 agent 应输出 devtools-verify 断言清单。插件 hook 检查 transcript 含 `evaluate_script` 或 `take_snapshot` 调用——没调用 → 推断只看代码没看效果 → 告警。

## hotfix 快速版

紧急 hotfix 至少跑：
1. `evaluate_script` 验证改动点的元素状态对了
2. `get_console_messages` 没新增 error

跳过完整流程但**不允许只看代码**。

## 关键字提示（插件用来识别）

输出含以下任一即算调用本 skill：
- `devtools-verify：` 段落标记
- 出现 `mcp__chrome-devtools__evaluate_script` 工具调用
- 出现 `mcp__chrome-devtools__take_snapshot` 工具调用
