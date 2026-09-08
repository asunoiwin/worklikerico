# upstream-test 执行说明

按 SKILL.md 的 8 阶段流程，对新接入上游做全维度回归测试。

## 调用

```bash
BASE_URL=https://panmode.com \
API_KEY=sk-xxx \
CHANNEL_NAME=bltcy \
STRESS_DUR_SEC=300 \
STRESS_CC=20 \
python3 run.py
```

## 必填环境变量

- `BASE_URL`：被测站点 API base
- `API_KEY`：测试用 key

## 可选

- `CHANNEL_NAME`：渠道标识，写入报告标题
- `STRESS_DUR_SEC`：压测时长，默认 300
- `STRESS_CC`：压测并发数，默认 20
- `SKIP_PHASES`：跳过 phase（逗号分隔），如 `phase4,phase6`

## 输出

- `data/phase{1..7}.json`：每 phase 原始数据
- `report-{ts}.md` / `report-{ts}.json`：最终报告

## 依赖

- Python 3.9+
- `aiohttp`
- macOS `sips`（用于生成真实 PNG，若不存在自动 fallback 内置 PNG）
