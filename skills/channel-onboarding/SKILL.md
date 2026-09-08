---
name: channel-onboarding
description: 新接入 LLM 上游/渠道时的标准化 SOP — 基于 larktokenweb 平台插件化契约，覆盖 6 个 SPI 接口选型、API root 三概念辨析、6 步接入流程、3 条硬断言验证。Triggers on - 新接渠道 / 接入上游 / 渠道接入 / upstream / channel / SPI / 插件对接 / plugin contract / UpstreamSyncAdapter / UpstreamGroupProbe / UpstreamTokenLister / UpstreamUsageReconciler / UpstreamUptimeProvider / UpstreamAccountBalanceFetcher / normalizeApiBaseUrl / 上游插件 / 新插件 / 接入验证 / supplier onboarding / channel onboarding.
---

# Channel Onboarding Skill

**核心定位**：每次新接入任意 LLM 上游/渠道时的执行向导。把"上游插件化契约"文档（`docs/upstream-plugin-contract.md`）蒸馏成可操作的 6 步 SOP + 验证清单，确保插件边界清晰、能力 fail-closed、API root 不混用。

**与 design-gate / blast-radius 的关系**：本 skill 聚焦**渠道接入领域知识**（SPI 选型、API root 辨析、能力开关配置），不重复 design-gate 的 PM gating 六子项，也不重复 blast-radius 的图谱分析。接入新渠道同样必须走 design-gate（新功能路径），本 skill 在 design-gate DESIGN_DONE 之后、编码阶段作为领域补充使用。

---

## 触发场景

1. **新上游插件模块**：创建 `platform-upstream-<protocol>/` 模块，接入从未支持的 LLM 提供商
2. **渠道能力扩展**：已有插件新增 SPI 实现（例如 newapi 新增 `UpstreamUptimeProvider`）
3. **API root 配置疑问**：渠道 base_url 应该填什么、官网地址和 API 地址如何区分
4. **接入验证标准疑问**：新渠道上线前应验证哪些维度、HTTP 200 是否足够
5. **能力开关 UI 适配**：前端按钮应该如何根据插件能力动态显示/禁用

---

## 节 1：SPI 能力清单

平台通过 6 个 SPI 接口消费上游能力。每个 SPI **按需实现**——上游没有对应接口就不注册，不注册 = 前端禁用 + 后台跳过，绝不 fallback 到其他插件。

| SPI 接口 | 用途 | 关键输出字段 | 注册触发条件 |
|---|---|---|---|
| `UpstreamSyncAdapter` | 模型列表与价格同步；生成模型列表、渠道成本、用户售价、价格变更告警 | model、group、billing mode、input/output cost、native currency、exchange rate、last_seen、price_diff | **必须实现**，所有插件基础能力 |
| `UpstreamGroupProbe` | 批量录入 token 时校验 provider group 是否存在；上游分组探测 | group key 列表、is_supported_probe | 上游有分组管理接口才实现；无则不注册或返回固定语义分组 |
| `UpstreamAccountBalanceFetcher` | 账户级余额展示和低余额告警 | balance、used、quota、request_count、currency/rate | 上游有账户级余额查询接口才实现 |
| `UpstreamTokenLister` | 从上游选择性导入 token、本地 token 对齐 | token_id、name、masked_key、group、status、quota | 上游有 token 管理接口才实现 |
| `UpstreamUsageReconciler` | 本地扣费与上游扣费对账、异常告警 | token_id、token_name、cost、window、request_count | 上游有账单/用量明细接口才实现 |
| `UpstreamUptimeProvider` | L1/L2/L3 模型检查、熔断前置判断 | group、model/brand、status、reason、checked_time | 上游有状态页或健康数据源才实现 |

### 注册规则

- 所有 SPI 的 `code()` 返回值必须一致（例如 `"newapi"`、`"dreamto"`），且全局唯一
- 注册表：`UpstreamRegistry.listProtocols()` → `/api/admin/upstream/protocols`
- 前端能力开关字段：`supportsModelsProbe` / `supportsAccountBalance` / `supportsTokenList` / `supportsUsageReconcile`
- 不支持的能力：返回"能力不存在"，前端按钮禁用，后台定时任务跳过 — **绝不 fallback 到 newapi**

---

## 节 2：API root 三概念辨析

接入时最常出错的地方。以下三个概念**不得混用**：

| 概念 | 典型示例 | 用途 | 归属 |
|---|---|---|---|
| **推荐渠道 base_url（API root）** | `https://api.example.ai` | 框架在后面拼标准 LLM endpoint（`/v1/chat/completions` 等） | 渠道配置，用户填写 |
| **官网/控制台地址** | `https://www.example.ai`、`https://console.example.ai` | 人类访问、价格页抓取；不作为推荐 API root | 插件内部或文档，不暴露给框架 |
| **管理/元数据接口 URL** | `https://api.example.ai/v1/models`、价格页 URL | 插件内部拉模型、价格、余额、token 列表 | 插件内部硬编码，不通过 base_url 传递 |

### 框架消费规则

- 框架只在 **API root 后拼固定协议 endpoint**，入口为 `UpstreamProtocol.normalizeApiBaseUrl()` + `UpstreamRegistry.normalizeApiBaseUrl()`
- 框架绝不在 `RelayController`、`ModelHealthService`、`ChannelHealthService` 里写某个上游的官网域名特例
- 新增上游只允许通过插件重写 `normalizeApiBaseUrl()` 暴露 API root

### 兼容兜底逻辑

若存在"用户误填官网/控制台地址"风险，可在插件 `UpstreamSyncAdapter` 重写 `normalizeApiBaseUrl()` 做映射：

```java
@Override
public String normalizeApiBaseUrl(String inputUrl) {
    // 用户可能填 www.example.ai，标准化为 api.example.ai
    if (inputUrl.contains("www.example.ai") || inputUrl.contains("example.ai/")) {
        return "https://api.example.ai";
    }
    return super.normalizeApiBaseUrl(inputUrl); // 默认去尾斜杠
}
```

兼容兜底是**安全网，不是推荐路径**。渠道文档应明确告知用户填写 API root。

---

## 节 3：6 步标准化接入 SOP

### 步骤 1：定义插件 code

- 格式：小写 kebab-case（`newapi`、`dreamto`、`openrouter`）
- 所有 SPI 实现类的 `code()` 方法返回值必须一致
- 验证：`grep -r 'code()' platform-upstream-<protocol>/` 确认全部一致

### 步骤 2：明确三类地址

填写以下清单后才能开始编码：

```
推荐 API root：____________________（用户应填写的渠道 base_url）
官网/控制台地址：____________________（不作为 API root，仅内部用）
管理接口 URL 模板：____________________（插件内部，如 {api_root}/v1/models）
兼容兜底映射是否必要：是/否
```

若 API root 和官网不同 → 必须实现 `normalizeApiBaseUrl()` 兜底

### 步骤 3：按能力逐一选型实现

对照节 1 的 SPI 清单，逐行回答"该上游是否有此接口"：

```
UpstreamSyncAdapter：必须实现
UpstreamGroupProbe：有分组接口? Y/N → 实现/不注册
UpstreamAccountBalanceFetcher：有余额接口? Y/N
UpstreamTokenLister：有 token 管理接口? Y/N
UpstreamUsageReconciler：有账单/用量接口? Y/N
UpstreamUptimeProvider：有状态页/健康接口? Y/N
```

未注册的能力 = 前端按钮禁用 + 后台 fail-closed，不需要任何额外代码

### 步骤 4：输出平台标准字段

插件内部完成所有转换，框架不猜上游私有格式：

- 模型名、厂商、model_type、支持 endpoint、计费模式 → 转成 `t_upstream_*` 表结构
- 所有成本字段 → 统一换算为平台内部单位（不保留上游私有单位）
- 币种 → 插件内换算清楚，框架不处理外币
- 不支持的字段 → 留空值或不填，不伪造

自检问题：`ModelTypeInference.inferPublicCatalogType()` 是否正确识别该上游模型类型？

### 步骤 5：接入框架能力开关

后端注册：在 `platform-upstream-<protocol>` 模块的 `@Component` 实现类上正确实现对应 SPI

前端适配：确认页面按照 `supportsXxx` 标志裁剪按钮和字段：

```
/api/admin/upstream/protocols 返回能力字段 → 对应前端 v-if/disabled
```

验证：调 `/api/admin/upstream/protocols` 接口，确认新插件的 code 出现在列表中，且只有已实现的能力为 `true`

### 步骤 6：验证（见节 4 三条硬断言）

---

## 节 4：接入验证三条硬断言

这三条缺一不可，HTTP 200 不等于接入成功：

### 断言 1：管理接口数据非空且结构正确

```
❌ 错误验证方式：curl 返回 HTTP 200
✅ 正确验证方式：解析响应后标准字段非空，且数量符合预期
  - UpstreamSyncAdapter：t_upstream_model 有 N 条新增记录，cost > 0
  - UpstreamAccountBalanceFetcher：balance 字段有值，非 0/null
  - UpstreamTokenLister：至少 1 条 token 记录，masked_key 格式正确
```

### 断言 2：LLM 调用打到插件输出的 API root

```
❌ 错误：实际请求打到了用户填写的官网地址（www.example.ai）
✅ 正确：抓包或日志确认实际 HTTP 请求域名 = normalizeApiBaseUrl() 返回值
  验证方法：
  - 查 relay 日志中的 channel base_url
  - 或用 mitmproxy 抓取出站请求
  - 确认 Host 头 = api.example.ai，而非 www.example.ai
```

### 断言 3：不支持的能力 fail-closed

```
❌ 错误：未注册 UpstreamTokenLister，但前端仍显示"导入 Token"按钮
❌ 错误：未注册但后台定时任务仍调用，抛 NullPointerException
✅ 正确三件事同时满足：
  1. 前端对应按钮禁用或不显示（按 supportsTokenList=false）
  2. 手动调 /api/admin/upstream/tokens 返回"能力不存在"错误码
  3. 定时任务日志显示该 code 的任务被跳过（不是报错，是主动跳过）
```

---

## 失败模式（典型反模式）

### 反模式 1：把官网地址当 API root 填入渠道

**表现**：用户填 `https://www.example.ai`，框架拼出 `https://www.example.ai/v1/chat/completions`，返回 404

**根因**：设计层 — 没有实现 `normalizeApiBaseUrl()` 兜底，且文档未明确推荐地址

**解法**：插件实现兜底映射 + 渠道文档明确标注推荐 API root

### 反模式 2：不支持能力返回空数组而非"能力不存在"

**表现**：`UpstreamTokenLister` 未实现，但被框架调用时返回空 `[]`，前端误以为"上游没有 token"而非"功能不支持"

**根因**：设计层 — SPI 未实现时默认行为未定义为 fail-closed

**解法**：不实现该 SPI 接口 = 框架自动 fail-closed，不要实现一个返回空值的空方法

### 反模式 3：多个 SPI 实现类的 code() 不一致

**表现**：`UpstreamSyncAdapter.code()` 返回 `"example-ai"`，`UpstreamGroupProbe.code()` 返回 `"exampleai"`，注册表中出现两个条目

**根因**：数据结构层 — code 语义重载/不统一

**解法**：所有 SPI 实现类继承同一个 `BaseExamplePlugin` 或引用同一个常量 `CODE = "example-ai"`

---

## 与现有体系对接

| Skill | 分工边界 |
|---|---|
| **design-gate v4** | PM gating 六子项 + 架构师视野（blast radius + grep 三栏）。新渠道接入属于"新功能"，必须先走 design-gate DESIGN_DONE 才能编码。本 skill 在 DESIGN_DONE 后补充渠道领域知识，不重复 PM gating |
| **blast-radius** | 修改现有 SPI 接口定义时，用 blast-radius 查哪些调用方受影响。本 skill 聚焦新接入，不覆盖图谱分析 |
| **strict-prod-audit** | 接入完成后的双轮测试。节 4 的三条硬断言是一测的最低验收标准，嵌入 strict-prod-audit 一测 checklist |
| **upstream-test** | 批量模型测试（多 model 并发验证响应格式）。本 skill 的验证聚焦接入正确性，upstream-test 聚焦模型质量 |

---

## 快速检查清单（接入完成后自检）

```
[ ] plugin code 全局唯一，所有 SPI code() 一致
[ ] 三类地址已区分：API root / 官网 / 管理接口 URL
[ ] 仅实现上游实际有接口的 SPI，未实现的不注册
[ ] normalizeApiBaseUrl() 已处理官网误填兜底（如需要）
[ ] /api/admin/upstream/protocols 能力开关字段与实现一致
[ ] 断言 1：管理接口返回数据解析后字段非空
[ ] 断言 2：LLM 调用 Host 头 = normalizeApiBaseUrl() 输出
[ ] 断言 3：未注册能力 → 前端禁用 + 后台 fail-closed + 定时任务跳过
[ ] ModelTypeInference 正确识别该上游模型类型
[ ] 所有成本字段已在插件内换算为平台单位
```
