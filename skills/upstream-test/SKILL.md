---
name: upstream-test
description: 上游供应商接入后的全维度模型批量测试流程。用于新接入 newapi 类上游/新增渠道/版本回归。一次调用产出确定结论和完整测试报告。Triggers on - 新接入上游测试 / 渠道测试 / 模型批量测试 / 上游验证 / 接入回归 / 全维度测试报告 / supplier acceptance test / channel onboarding test.
---

# 上游供应商接入测试 Skill

**目标**：新上游接入或新增渠道时，跑一次完整流程产出确定的接入决策报告，避免每次手工凑测试。

**调用前置**：用户必须提供
- `BASE_URL`：被测站点 API base（如 https://panmode.com）
- `API_KEY`：测试用 API Key（super-admin 或权限充足的用户 key）
- `CHANNEL_NAME`（可选）：渠道标识，用于报告标题
- `STRESS_DUR_SEC`（可选，默认 300）：压测时长
- `STRESS_CC`（可选，默认 20）：压测并发数

如缺则向用户询问，**不要假设默认值**。

---

## 流程概览（务必按此顺序）

```
[Phase 1 探测]   /v1/models 抓全模型 → 分类
[Phase 2 协议]   并发跑 8 端点矩阵
[Phase 3 特性]   thinking / multimodal / tool calling
[Phase 4 计费]   token + per-call 双模式对账
[Phase 5 边界]   401/402/403/429/503 + 畸形 JSON
[Phase 6 稳态]   持续负载 + 超长上下文 + CF100s
[Phase 7 重测]   归类"上游"前必须重测 3 次 + cooldown 等待
[Phase 8 报告]   生成 Markdown + JSON
```

每个 phase 失败不终止，全部跑完再统一分析。

---

## Phase 1：模型探测与分类

```python
GET {BASE_URL}/v1/models
Authorization: Bearer {API_KEY}
```

按命名模式分类：
- **OpenAI**：gpt-* / o1-* / dall-e-* / whisper-* / tts-*
- **Anthropic**：Codex-*
- **Gemini**：gemini-*
- **国产**：deepseek-* / qwen-* / glm-* / kimi-* / moonshot-* / doubao-* / minimax-* / yi-*
- **Image**：flux-* / midjourney / stable-* / seedream-* / recraft-*
- **Embedding**：*embedding* / *embed*
- **Rerank**：*rerank*
- **Audio**：whisper-* / tts-* / *transcribe* / *-audio-* / *-realtime-*
- **Video**：kling-* / sora-* / veo-* / runway-* / pika-*
- **Thinking 变体**：*-thinking / *-r1 / *-reasoner / o1-*

输出：每类挑 2-3 个代表（newest + oldest 各一）作为后续测试用例。

---

## Phase 2：协议矩阵（并发）

8 个端点必测：

| 端点 | 协议家族 | 测试模型 | 用例 |
|---|---|---|---|
| `/v1/chat/completions` | OpenAI | OpenAI/Codex/Gemini/国产 各 1 | basic / stream / tool_calling |
| `/v1/messages` | Anthropic 原生 | Codex × 1 | basic / stream / thinking |
| `/gemini/v1beta/models/{m}:generateContent` | Gemini 原生 | Gemini × 1 | basic |
| `/gemini/v1beta/models/{m}:streamGenerateContent` | Gemini 原生 | Gemini × 1 | stream |
| `/v1/responses` | OpenAI Responses | gpt × 1 | basic / stream |
| `/v1/embeddings` | OpenAI | embedding × 3 | dims |
| `/v1/images/generations` | OpenAI | image × 3 | n=1 |
| `/v1/audio/speech` | OpenAI TTS | tts × 1 | bytes |
| `/v1/audio/transcriptions` | OpenAI STT | whisper × 1 | text |

**实现要点**：
- 用 `asyncio.gather` 同时打全部，墙钟控制在 2 分钟内
- timeout=60s/req，total=180s
- **每条记录：status / 耗时ms / 上游错误原文**
- **不要单条失败就 raise**，记下来继续

### 2.x 流式 SSE usage 帧校验（关键，本轮回归必测）

**所有 stream=true 用例**末尾必须能从 SSE 流中解析出 `usage`（OpenAI/Responses）或 `usage_metadata`（Gemini）或 `message_delta.usage`（Anthropic）：

| 协议 | usage 帧位置 | 字段 |
|---|---|---|
| OpenAI chat.completions stream | 倒数第 2 帧（`[DONE]` 前），`choices=[]` 且含 `usage` | `usage.prompt_tokens / completion_tokens` |
| OpenAI Responses stream | `response.completed` 事件含 `response.usage` | `input_tokens / output_tokens` |
| Anthropic messages stream | `message_delta` event + `message_stop` | `usage.input_tokens / output_tokens` |
| Gemini streamGenerateContent | 末帧 `usageMetadata` | `promptTokenCount / candidatesTokenCount` |

判定 ❌（必须报）：
- 收到 `[DONE]` 但全程没出现过 usage 字段 → 上游或网关漏发，会导致 panmode 计费 fallback 估算
- usage 出现在中间帧但末尾被丢弃 → 网关只读末帧的实现会漏

实现：每条 stream 用例独立维护 `seen_usage = False`，整流跑完检查；记入报告 Phase 2 表格的"usage 字段"列。

### 2.y upstream 200 + error body 分类（BUG-N 回归）

newapi 类上游常见返回 HTTP 200 但 body 是 `{"error":{...}}` —— 旧版本会被错误归为 `upstream_other`，新版应能识别为对应类型（rate_limit / quota / auth / model_unavailable）。

构造：找一个余额=0 或上下文超长触发 quota 的模型用例，发请求，断言：
- HTTP code = 上游真实返回（200 或 400+）
- 若 panmode 已修复，会基于 message 关键词重新分类（`额度/quota/insufficient` → `quota_exceeded`；`rate/限流/429` → `rate_limit`）
- panmode 不应回 `upstream_other`

---

## Phase 3：特性测试

### 3.1 Thinking blocks
对每个 thinking 变体模型（如 Codex-sonnet-4-thinking / Codex-opus-4-5-thinking / deepseek-r1 / doubao-seed-thinking）：

- Anthropic 用 `/v1/messages` body 含 `thinking: {type:'enabled', budget_tokens:1024}`，header 加 `anthropic-beta: extended-thinking-2025-05-14`
- OpenAI o1 / 国产 r1 用 `/v1/chat/completions`，看响应 `choices[0].message.reasoning_content`

判定 ✅：
- Anthropic: `content[].type` 含 'thinking' 且 `thinking` 字段非空
- OpenAI 兼容: `reasoning_content` 长度 > 0

### 3.2 Multimodal（真实图片）
**必须用真实 PNG，不要 1x1**（容易被上游图像验证拒）。

```python
# macOS 现成测试图
sips -s format png /System/Library/Desktop\ Pictures/Solid\ Colors/Red\ Orange.png \
    --resampleWidth 200 --out /tmp/test.png
PNG_B64 = base64.b64encode(open('/tmp/test.png','rb').read()).decode()
```

3 个协议都测：
- OpenAI: `image_url: {url: "data:image/png;base64,..."}`
- Anthropic: `image: {source: {type:'base64', media_type:'image/png', data: ...}}`
- Gemini: `inline_data: {mime_type:'image/png', data: ...}`

判定 ✅：返回文本描述里能识别出图像主色调（如"红"、"red"）

### 3.3 Tool calling
- OpenAI 流式：body 含 `tools` + `stream:true`，看 chunks 里有无 `tool_calls`
- Codex messages：body 含 Anthropic `tools`，看响应有无 `tool_use` block + `stop_reason: tool_use`

---

## Phase 4：计费对账

**前置：先查渠道加价比例（决定判定阈值）**
```
GET /api/admin/channels?id={id}  # 看 markup / price_ratio / surcharge_pct 字段
```
- 加价 = 0%（如自用 bltcy 直采渠道）→ **本站消费必须 = 上游消耗，零误差**
- 加价 > 0%（如分销渠道）→ 本站消费 = 上游消耗 × (1+加价)，误差容忍 ±0.5%（精度损失而非业务差异）
- 阶梯/折扣定价 → 按渠道配置公式计算预期值，误差 ±0.5%

测试 2 种计费模式各 30 次：
- **按 token**：常规 chat 模型（gpt-4o-mini）
- **按次（per-call）**：image / midjourney / 部分音频

分别记录：
- 客户端聚合的 prompt_tokens / completion_tokens 总和
- panmode 端 `t_usage_log` 同窗口 SUM 比对（用 admin SQL 端点或 admin API）
- 上游（如 bltcy）`/api/log/self` 同窗口比对（如可获取）

判定 ✅（按加价分档）：
- 零加价场景：**panmode cost SUM = 上游 cost SUM 必须 100% 吻合**（任何差异都是 BUG，常见原因：流式 usage 漏帧 fallback 估算、failover 双扣、按次模型走了按 token 公式）
- 有加价场景：差异 = (本站−上游)/上游 ≈ 加价比例 ±0.5%
- token 数维度：客户端聚合 prompt_tokens + completion_tokens **必须** = panmode `t_usage_log` SUM = 上游计数（三方 token 数零差异，否则就是某一层在丢/估算）

**报告必须分别给出**："token 数三方差异" 和 "金额三方差异"，不能混在一起报。

### 4.x failover 双扣检测（关键）
故意构造让 A 渠道失败 → 自动切 B 成功。两次方法：
- 临时把 A 渠道的 base_url 改坏（admin API），或调一个只有 A 支持但实际不通的模型组合
- 一次成功的请求结束后查 `t_usage_log`：**只能有 1 条**记账记录（应记 B 渠道的成本）
- 若出现 2 条 → 重试时双扣 BUG

### 4.y 流式超时 completion=0 检测（lesson 1）
- 构造一个超长 prompt（30k+ token）让上游响应慢
- 用 `stream=true` 调用，主动在 90s 时断开客户端连接
- 查 `t_usage_log`：若 completion_tokens=0 但 prompt_tokens 非 0 → **应有"估算"标记**或 cost 中体现 fallback。完全 0 输出 token 入库 = BUG

---

## Phase 5：错误码边界

| 用例 | 期望 |
|---|---|
| 无效 key `sk-fake-xxx` | 401 |
| 余额=0 调 chat | 402 + type:insufficient_quota |
| API key 设 allowed_models=['gpt-4o-mini']，调 deepseek-v3 | 403 + type:model_not_allowed |
| 80 并发 chat（同 key）| 看是否 429（许多系统默认无 user rate limit，**记录但不阻塞**）|
| 不存在的模型 `no-such-model-xyz` | 503 + type:no_channel |
| 触发 cooldown 后请求 | 503 + type:channel_cooldown + Retry-After header |
| 畸形 JSON body | 400 + type:invalid_request |

注意 **HTTP/2 把 header 名称小写化**，Python urllib `headers.get('Retry-After')` 需用小写 `retry-after`。

---

## Phase 6：稳态压测（合并测）

用单个脚本同时验证：
- 超长上下文（30k token 输入）
- 持续负载（默认 5 分钟 × 20 并发）
- CF 100s 边界（监测 max_chunk_gap > 100s）
- 流式断流监测

参考实现已从发布包移除；如需压测，请按本节约束在项目临时目录实现并保留结果摘要。

关键指标：
- TTFB / max_chunk_gap / total_elapsed 的 p50/p95/p99
- CF 100s 触发计数（>0 是黄旗）
- 失败时间窗（连续失败 = 上游或 panmode 故障；零散失败 = 偶发）
- 实际 QPS（受上游响应时间制约）

判定通过：
- 失败率 < 1%
- p95 < 30s（取决于业务，可调）
- 0 次 CF 100s 触发

---

## Phase 7：重测确认（关键防误判）

**任何首次失败的 case 都不能直接归"上游问题"**，必须：

1. **等 70 秒**（让 ChannelHealthCache 60s cooldown 自然过期）
2. **重测同一 case 3 次**，间隔 ≥5 秒
3. 判定：
   - 3/3 通过 → 之前是 cooldown 假象，**真实 ✅**
   - 0/3 通过 → 真上游不通，**记入"真上游不通"**
   - 1-2/3 通过 → 上游偶发性能波动，**记入"间歇不稳"**

**重测前先查渠道状态**确认不是 panmode 自动禁用：
```
GET /api/channels?page=1&size=10  # 看 fail_count / test_status
```

如果是 cooldown 误返 no_channel，需要让被测站升级到含 BUG-R 修复的版本（v1.4.42+）。

---

## Phase 8：报告输出

生成 2 份：
- `report-{timestamp}.md`：人读
- `report-{timestamp}.json`：机读 + 后续对账

### Markdown 报告骨架（必须包含全部章节，不可裁剪）

```markdown
# {CHANNEL_NAME} 上游接入测试报告

**测试时间**：{start} - {end}
**测试 BASE**：{BASE_URL}
**测试 Key**：{KEY[:8]}…
**panmode 版本**：{从 /api/admin/update/current 拿，如能拿到}
**总用例数**：{N}
**通过率**：{ok}/{N} = {pct}%
**关键决策**：[ ] 接入 [ ] 暂缓 [ ] 拒绝（理由：...）

## 一、Phase 1 模型探测
- /v1/models 总数：{count}
- 分类：OpenAI={n} / Anthropic={n} / Gemini={n} / 国产={n} / Image={n} / Embed={n} / Rerank={n} / Audio={n} / Video={n}

## 二、Phase 2 协议矩阵 ({pass}/{total})
| 端点 | 模型 | 用例 | 状态 | 时延 ms | 备注 |
| ... |

## 三、Phase 3 特性
### 3.1 Thinking
| 模型 | thinking 字段返回 | reasoning_content |
| ... |

### 3.2 Multimodal（真实 PNG）
| 协议 | 模型 | 状态 | 返回文本 |
| OpenAI vision | gpt-4o | ✅ | "红色背景" |
| Anthropic vision | Codex-3-5-sonnet | ✅ | "纯红色" |
| Gemini vision | gemini-2.5-flash | ✅ | "纯色橙红色" |

### 3.3 Tool calling
| 协议 | 流式 tool_calls 增量 | tool_use block |
| ... |

## 四、Phase 4 计费对账
| 模式 | n 次 | prompt_tokens | completion_tokens | 客户端 cost | 服务器 cost | 公式 cost | 误差 |
| token | 30 | ... | ... | ... | ... | ... | ±X% |
| 按次 | 30 | - | - | ... | ... | ... | ±X% |

**判定**：✅ 计费链路正确 / ⚠️ 误差超 5% 待查

## 五、Phase 5 错误码边界
| 用例 | 期望 | 实际 | 状态 |
| 无效 key | 401 | ... | ✅/❌ |
| 余额=0 | 402 | ... | ... |
| 不在 allowed_models | 403 | ... | ... |
| 80 并发 | 429 或全 200 | ... | ⚠️ 配置 |
| 未配置模型 | 503 no_channel | ... | ... |
| cooldown 期间 | 503 channel_cooldown + Retry-After | ... | ... |
| 畸形 JSON | 400 | ... | ... |

## 六、Phase 6 稳态压测
- 配置：DUR={dur}s / CC={cc} / 上下文 {ctx} 字符
- 实际成功：{ok}/{total}（{pct}%）
- TTFB p50/p95/p99：... ms
- max_chunk_gap p50/p95/p99：... ms
- CF 100s 触发：{n} 次
- 失败时间窗：{seconds}s（连续失败窗口）

**判定**：✅ 稳态可用 / ⚠️ 偶发 / ❌ 不稳定

## 七、Phase 7 重测确认（仅展示首次失败的）
| 用例 | 首次结果 | 重测 1 | 重测 2 | 重测 3 | 归类 |
| Codex-vision | ❌ 503 | ✅ | ✅ | ✅ | **cooldown 假象，实际 OK** |
| moonshot-v1-8k | ❌ 503 | ❌ | ❌ | ❌ | **真上游不通** |

## 八、未通过项归类与建议

### 真上游不通（建议下线 / 联系上游）
- 模型 X：3 轮 503 + 同系列其他模型同样失败
- ...

### 上游偶发不稳（建议保留 + 监控）
- 模型 Y：5 次中 1 次失败，gap 大

### panmode 配置缺失（admin 自查）
- 模型 Z：no_channel 但 panmode 渠道未配置
- 建议：channel 管理添加 ...

### 旧版本上游不维护
- v3.1 / older：建议从模型列表下线，引导用户用新版本

## 九、客户保障可承诺度
| 项 | 状态 |
|---|---|
| 计费正确 | ✅/❌ |
| 流式不丢 | ✅/❌ |
| 错误码合规 | ✅/❌ |
| Cooldown 区分 | ✅/❌ |
| 稳态 QPS 上限 | ~{n} QPS（{pct}% 成功率）|
| 单点故障 | ⚠️ 单渠道 = 单 SPOF |

## 十、决策建议
[ ] **接入**：通过率 ≥95%，关键功能全 ✅
[ ] **暂缓接入**：失败 5-15% 或部分关键功能 ❌（具体: ...）
[ ] **拒绝接入**：失败 >15% 或鉴权/计费有重大问题
```

---

## 实现规范

### 脚本组织
```
test-{ts}/
├── run.py               # 主入口，按 phase 跑
├── phase1_models.py     # 探测分类
├── phase2_protocol.py   # 8 端点矩阵
├── phase3_features.py   # thinking + multi + tool
├── phase4_billing.py    # 对账
├── phase5_errors.py     # 错误码
├── phase6_stress.py     # 压测
├── phase7_reverify.py   # 重测
├── phase8_report.py     # 渲染
├── data/                # 各阶段 raw JSON
└── report-{ts}.md
```

### 必备工具函数（不要重写）
- `http(method, url, headers, body, timeout)`：统一异步 HTTP，捕获所有异常返 status+body
- `mk_real_png()`：用 sips 生成 200x200 真实 PNG
- `wait_cooldown(70)`：等 ChannelHealthCache cooldown 自然过期
- `query_usage_log(start, end)`：调 admin API 拿 panmode t_usage_log 聚合
- `pct(arr, p)`：百分位计算（非 numpy）

### 输入参数规范
- 所有可调参数从环境变量读：`BASE_URL` / `API_KEY` / `STRESS_DUR_SEC` / `STRESS_CC` / `MODEL_ALLOW_LIST` / `SKIP_PHASES`
- 缺关键参数（BASE/KEY）报错退出，**不假设默认**

### 防止误判（关键！）
1. 任何 503 / 524 / timeout 都进 phase7 重测队列
2. 触发 cooldown 后必须 wait 70s
3. 同时观察上游同类多个模型，单点失败 vs 整组失败要区分
4. 报告里"真上游不通"必须有"重测 N 次稳定失败 + 同类模型 X/Y/Z 同样失败"作为证据

---

## 调用方式

```bash
# 标准调用
BASE_URL=https://panmode.com \
API_KEY=sk-xxx \
CHANNEL_NAME=bltcy-2026q2 \
STRESS_DUR_SEC=1800 \
STRESS_CC=100 \
python3 run.py

# 跳过某 phase（增量回归）
SKIP_PHASES=phase4,phase6 python3 run.py
```

输出：`report-{ts}.md` + `report-{ts}.json` 在工作目录。

---

## 历史经验（避免踩坑）

参考 `Codex-memory-pro` lesson scope:larktokenweb 中：
- API 测试矩阵覆盖维度（协议 × 类别 × 特性 × 计费）
- RelayController 多协议透传不能走 chat.completions 适配器
- 上游问题归类必须重测确认（cooldown 假象）
- 站点核心代码不应硬编码 newapi 上游特性

每次跑完 skill 把新发现 lesson_capture 到 scope:larktokenweb，下次召回。
