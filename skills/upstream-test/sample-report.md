# bltcy 上游接入测试报告

**测试时间**：2026-04-29 23:42:33 - 2026-04-29 23:51:51
**测试 BASE**：https://panmode.com
**测试 Key**：sk-G51CT…
**panmode 版本**：（未自动获取）
**总用例数**：19
**通过率**：14/19 = 73.7%
**关键决策**：[拒绝]

## 一、Phase 1 模型探测
- /v1/models 总数：876
- 分类：openai=179 / anthropic=31 / gemini=46 / cn=217 / image=79 / embedding=6 / rerank=6 / audio=22 / video=66 / thinking=70

## 二、Phase 2 协议矩阵 (9/14)
| 端点 | 模型 | 用例 | 状态 | 时延 ms | 备注 |
|---|---|---|---|---|---|
| /v1/chat/completions | o4-mini-high-all | basic | [OK] 200 | 17155 |  |
| /v1/chat/completions | claude-sonnet-4-6-thinking | basic | [OK] 200 | 14786 |  |
| /v1/chat/completions | gemini-pro | basic | [FAIL] 503 | 11512 |  |
| /v1/chat/completions | qwen3.6-plus | basic | [OK] 200 | 14391 |  |
| /v1/chat/completions | o4-mini-high-all | stream | [OK] 200 | 17220 |  |
| /v1/chat/completions | o4-mini-high-all | tool_calling | [OK] 200 | 22463 |  |
| /v1/messages | claude-sonnet-4-6-thinking | basic | [OK] 200 | 18381 |  |
| /v1/messages | claude-sonnet-4-6-thinking | stream | [OK] 200 | 14324 |  |
| /gemini/...:generateContent | gemini-pro | basic | [FAIL] 503 | 11517 |  |
| /gemini/...:streamGenerateContent | gemini-pro | stream | [FAIL] 503 | 840 |  |
| /v1/responses | o4-mini-high-all | basic | [OK] 200 | 39557 |  |
| /v1/embeddings | text-embedding-3-small | dims | [OK] 200 | 12098 |  |
| /v1/images/generations | z-image-turbo | n=1 | [FAIL] 503 | 11727 |  |
| /v1/audio/transcriptions | whisper-1 | text | [FAIL] 500 | 880 |  |

## 三、Phase 3 特性
### 3.1 Thinking
| 模型 | 协议 | thinking 字段 | reasoning_content |
|---|---|---|---|
| claude-3-7-sonnet-20250219-thinking | anthropic | [FAIL] | - |
| claude-3-7-sonnet-thinking | anthropic | [FAIL] | - |
| claude-haiku-4-5-20251001-thinking | anthropic | [OK] | - |

### 3.2 Multimodal（真实 PNG）
| 协议 | 模型 | 状态 | 返回文本 |
|---|---|---|---|
| openai-vision | chatgpt-4o-latest | [FAIL] 503 |  |
| anthropic-vision | claude-sonnet-4-6-thinking | [OK] 200 | Red. |
| gemini-vision | gemini-pro | [FAIL] 503 |  |

### 3.3 Tool calling
| 协议 | 模型 | 流式 tool_calls | tool_use block |
|---|---|---|---|
| openai-stream-tool | o4-mini-high-all | False | - |
| anthropic-tool | claude-sonnet-4-6-thinking | - | True |

## 四、Phase 4 计费对账
| 模式 | 模型 | n 次 | OK 次 | prompt | completion | 备注 |
|---|---|---|---|---|---|---|
| token | o4-mini-high-all | 30 | 30 | 420 | 634 | 客户端聚合，未对接服务器侧 |
| 按次 | z-image-turbo | 5 | 2 | - | - | 成功调用 2 次 |

**判定**：[INFO] 客户端聚合记录已留存；服务器/上游对账待接 admin API

## 五、Phase 5 错误码边界
| 用例 | 期望 | 实际 | 状态 |
|---|---|---|---|
| 无效 key | 401 | 401 | [OK] |
| 不存在的模型 | 503/404 + no_channel/not_found | 503 | [OK] |
| 畸形 JSON | 400 | 400 | [OK] |
| 80 并发 chat | 429 或 全 200 | 200=80 429=0 other=0 | [OK] |
| cooldown 期间再调 | 503 + retry-after 或一致 503 | r1=503 r2=503 retry-after=None | [OK] |

## 六、Phase 6 稳态压测
- 配置：DUR=60s / CC=5 / 上下文 20000 字符 / 模型 o4-mini-high-all
- 实际成功：33/33（100.0%）
- TTFB p50/p95/p99：6925 / 12937 / 14400 ms
- max_chunk_gap p50/p95/p99：7591 / 12937 / 14400 ms
- CF 100s 触发：0 次
- 失败时间窗：0s（连续失败窗口）
- 实际 QPS：0.55

**判定**：[OK] 稳态可用

## 七、Phase 7 重测确认（仅展示首次失败的）
| 用例 | 首次结果 | 重测 1 | 重测 2 | 重测 3 | 归类 |
|---|---|---|---|---|---|
| gemini-pro / basic | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| gemini-pro / basic | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| gemini-pro / stream | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| z-image-turbo / n=1 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| whisper-1 / text | [FAIL] 500 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| claude-3-7-sonnet-20250219-thinking / thinking | [FAIL] 200 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| claude-3-7-sonnet-thinking / thinking | [FAIL] 0 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| chatgpt-4o-latest / multimodal | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| gemini-pro / multimodal | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | [FAIL] 503 | **真上游不通** |
| o4-mini-high-all / tool_calling | [FAIL] 200 | [OK] 200 | [OK] 200 | [OK] 200 | cooldown 假象，实际 OK |

## 八、未通过项归类与建议
### 真上游不通（建议下线 / 联系上游）
- gemini-pro / basic：3 轮全失败
- gemini-pro / basic：3 轮全失败
- gemini-pro / stream：3 轮全失败
- z-image-turbo / n=1：3 轮全失败
- whisper-1 / text：3 轮全失败
- claude-3-7-sonnet-20250219-thinking / thinking：3 轮全失败
- claude-3-7-sonnet-thinking / thinking：3 轮全失败
- chatgpt-4o-latest / multimodal：3 轮全失败
- gemini-pro / multimodal：3 轮全失败

### 上游偶发不稳（建议保留 + 监控）
- 无

### panmode 配置缺失 / 旧版本（自查）
- 见 Phase 7 归类表，需对照 admin 渠道配置自查

## 九、客户保障可承诺度
| 项 | 状态 |
|---|---|
| 计费正确 | [OK] 客户端聚合记录 |
| 流式不丢 | [OK] |
| 错误码合规 | [OK] |
| Cooldown 区分 | [OK] |
| 稳态 QPS 上限 | ~0.55 QPS（100.0% 成功率）|
| 单点故障 | [WARN] 单渠道 = 单 SPOF |

## 十、决策建议
- [ ] 接入
- [ ] 暂缓接入
- [x] **拒绝接入**：通过率 73.7% < 85%
