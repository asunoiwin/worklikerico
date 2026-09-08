"""Phase 8：渲染 markdown + json 报告。"""
import json
import os
import sys
import time
from datetime import datetime


def _load(ctx, name):
    p = os.path.join(ctx["data_dir"], f"{name}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def _check(b):
    return "通过" if b else "失败"


def _icon(b):
    return "[OK]" if b else "[FAIL]"


def _ms(v):
    if v is None:
        return "-"
    return f"{v:.0f}"


def render_md(ctx, ts):
    p1 = _load(ctx, "phase1") or {}
    p2 = _load(ctx, "phase2") or {}
    p3 = _load(ctx, "phase3") or {}
    p4 = _load(ctx, "phase4") or {}
    p5 = _load(ctx, "phase5") or {}
    p6 = _load(ctx, "phase6") or {}
    p7 = _load(ctx, "phase7") or {}

    total_cases = (p2.get("total") or 0) + (p5.get("total") or 0)
    ok_cases = (p2.get("ok") or 0) + (p5.get("ok") or 0)
    pass_pct = (ok_cases / total_cases * 100) if total_cases else 0

    lines = []
    name = ctx.get("channel_name") or "未命名渠道"
    lines.append(f"# {name} 上游接入测试报告\n")
    lines.append(f"**测试时间**：{ctx.get('start_str')} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**测试 BASE**：{ctx['base_url']}")
    lines.append(f"**测试 Key**：{ctx['api_key'][:8]}…")
    lines.append(f"**panmode 版本**：（未自动获取）")
    lines.append(f"**总用例数**：{total_cases}")
    lines.append(f"**通过率**：{ok_cases}/{total_cases} = {pass_pct:.1f}%")

    # 决策
    decision = "暂缓"
    if pass_pct >= 95:
        decision = "接入"
    elif pass_pct < 85:
        decision = "拒绝"
    lines.append(f"**关键决策**：[{decision}]")
    lines.append("")

    # 一、Phase 1
    lines.append("## 一、Phase 1 模型探测")
    summary = p1.get("summary") or {}
    lines.append(f"- /v1/models 总数：{summary.get('total', 0)}")
    cats = ["openai", "anthropic", "gemini", "cn", "image", "embedding",
            "rerank", "audio", "video", "thinking"]
    parts = [f"{c}={summary.get(c, 0)}" for c in cats]
    lines.append("- 分类：" + " / ".join(parts))
    lines.append("")

    # 二、Phase 2
    lines.append(f"## 二、Phase 2 协议矩阵 ({p2.get('ok', 0)}/{p2.get('total', 0)})")
    lines.append("| 端点 | 模型 | 用例 | 状态 | 时延 ms | 备注 |")
    lines.append("|---|---|---|---|---|---|")
    for c in p2.get("cases", []):
        lines.append(f"| {c.get('endpoint','-')} | {c.get('model','-')} | {c.get('case','-')} | "
                     f"{_icon(c.get('ok'))} {c.get('status','-')} | {_ms(c.get('elapsed_ms'))} | "
                     f"{(c.get('error') or '')[:80]} |")
    lines.append("")

    # 三、Phase 3
    lines.append("## 三、Phase 3 特性")
    lines.append("### 3.1 Thinking")
    lines.append("| 模型 | 协议 | thinking 字段 | reasoning_content |")
    lines.append("|---|---|---|---|")
    for r in p3.get("thinking", []):
        lines.append(f"| {r.get('model','-')} | {r.get('protocol','-')} | "
                     f"{_icon(r.get('has_thinking_block')) if 'has_thinking_block' in r else '-'} | "
                     f"{r.get('reasoning_content_len','-')} |")
    lines.append("")
    lines.append("### 3.2 Multimodal（真实 PNG）")
    lines.append("| 协议 | 模型 | 状态 | 返回文本 |")
    lines.append("|---|---|---|---|")
    for r in p3.get("multimodal", []):
        lines.append(f"| {r.get('protocol','-')} | {r.get('model','-')} | "
                     f"{_icon(r.get('ok'))} {r.get('status','-')} | {(r.get('text') or '')[:80]} |")
    lines.append("")
    lines.append("### 3.3 Tool calling")
    lines.append("| 协议 | 模型 | 流式 tool_calls | tool_use block |")
    lines.append("|---|---|---|---|")
    for r in p3.get("tool_calling", []):
        lines.append(f"| {r.get('protocol','-')} | {r.get('model','-')} | "
                     f"{r.get('tool_calls_in_chunks', '-')} | {r.get('has_tool_use_block', '-')} |")
    lines.append("")

    # 四、Phase 4
    lines.append("## 四、Phase 4 计费对账")
    lines.append("| 模式 | 模型 | n 次 | OK 次 | prompt | completion | 备注 |")
    lines.append("|---|---|---|---|---|---|---|")
    tm = p4.get("token_mode")
    if tm:
        lines.append(f"| token | {tm.get('model')} | {tm.get('n')} | {tm.get('ok')} | "
                     f"{tm.get('prompt_tokens_sum')} | {tm.get('completion_tokens_sum')} | "
                     f"客户端聚合，未对接服务器侧 |")
    pc = p4.get("percall_mode")
    if pc:
        lines.append(f"| 按次 | {pc.get('model')} | {pc.get('n')} | {pc.get('ok')} | - | - | "
                     f"成功调用 {pc.get('calls_billable')} 次 |")
    lines.append("")
    lines.append("**判定**：[INFO] 客户端聚合记录已留存；服务器/上游对账待接 admin API")
    lines.append("")

    # 五、Phase 5
    lines.append("## 五、Phase 5 错误码边界")
    lines.append("| 用例 | 期望 | 实际 | 状态 |")
    lines.append("|---|---|---|---|")
    for c in p5.get("cases", []):
        lines.append(f"| {c.get('case','-')} | {c.get('expected','-')} | "
                     f"{c.get('actual','-')} | {_icon(c.get('ok'))} |")
    lines.append("")

    # 六、Phase 6
    lines.append("## 六、Phase 6 稳态压测")
    cfg = p6.get("config", {})
    lines.append(f"- 配置：DUR={cfg.get('dur_sec')}s / CC={cfg.get('cc')} / "
                 f"上下文 {cfg.get('context_chars')} 字符 / 模型 {cfg.get('model')}")
    lines.append(f"- 实际成功：{p6.get('ok')}/{p6.get('total')}（"
                 f"{(p6.get('success_rate') or 0)*100:.1f}%）")
    ts1 = p6.get("ttfb_stats") or {}
    gs = p6.get("max_chunk_gap_stats") or {}
    lines.append(f"- TTFB p50/p95/p99：{_ms(ts1.get('p50'))} / {_ms(ts1.get('p95'))} / {_ms(ts1.get('p99'))} ms")
    lines.append(f"- max_chunk_gap p50/p95/p99：{_ms(gs.get('p50'))} / {_ms(gs.get('p95'))} / {_ms(gs.get('p99'))} ms")
    lines.append(f"- CF 100s 触发：{p6.get('cf_100s_count', 0)} 次")
    lines.append(f"- 失败时间窗：{p6.get('fail_window_max_sec', 0)}s（连续失败窗口）")
    lines.append(f"- 实际 QPS：{p6.get('qps_actual', 0):.2f}")
    sr = p6.get("success_rate") or 0
    if sr >= 0.99:
        verdict = "[OK] 稳态可用"
    elif sr >= 0.95:
        verdict = "[WARN] 偶发"
    else:
        verdict = "[FAIL] 不稳定"
    lines.append(f"\n**判定**：{verdict}")
    lines.append("")

    # 七、Phase 7
    lines.append("## 七、Phase 7 重测确认（仅展示首次失败的）")
    if p7.get("items"):
        lines.append("| 用例 | 首次结果 | 重测 1 | 重测 2 | 重测 3 | 归类 |")
        lines.append("|---|---|---|---|---|---|")
        for it in p7.get("items", []):
            r = it.get("rounds", [])
            r1 = f"{_icon(r[0].get('ok'))} {r[0].get('status')}" if len(r) > 0 else "-"
            r2 = f"{_icon(r[1].get('ok'))} {r[1].get('status')}" if len(r) > 1 else "-"
            r3 = f"{_icon(r[2].get('ok'))} {r[2].get('status')}" if len(r) > 2 else "-"
            v = {"stable_ok": "cooldown 假象，实际 OK",
                 "stable_fail": "**真上游不通**",
                 "intermittent": "上游间歇不稳"}.get(it.get("verdict"), it.get("verdict"))
            lines.append(f"| {it.get('model')} / {it.get('case')} | "
                         f"[FAIL] {it.get('first_status')} | {r1} | {r2} | {r3} | {v} |")
    else:
        lines.append("（无首次失败项 / 已全部通过）")
    lines.append("")

    # 八、未通过归类
    lines.append("## 八、未通过项归类与建议")
    stable_fail = [it for it in (p7.get("items") or []) if it.get("verdict") == "stable_fail"]
    intermittent = [it for it in (p7.get("items") or []) if it.get("verdict") == "intermittent"]
    lines.append("### 真上游不通（建议下线 / 联系上游）")
    if stable_fail:
        for it in stable_fail:
            lines.append(f"- {it.get('model')} / {it.get('case')}：3 轮全失败")
    else:
        lines.append("- 无")
    lines.append("\n### 上游偶发不稳（建议保留 + 监控）")
    if intermittent:
        for it in intermittent:
            lines.append(f"- {it.get('model')}：3 轮中 {it.get('ok_count')} 次通过")
    else:
        lines.append("- 无")
    lines.append("\n### panmode 配置缺失 / 旧版本（自查）")
    lines.append("- 见 Phase 7 归类表，需对照 admin 渠道配置自查")
    lines.append("")

    # 九、保障可承诺度
    lines.append("## 九、客户保障可承诺度")
    lines.append("| 项 | 状态 |")
    lines.append("|---|---|")
    p2_ok_pct = (p2.get('ok', 0) / p2.get('total', 1)) if p2.get('total') else 0
    p5_ok_pct = (p5.get('ok', 0) / p5.get('total', 1)) if p5.get('total') else 0
    lines.append(f"| 计费正确 | {'[OK]' if (p4.get('token_mode') or {}).get('ok',0) > 0 else '[WARN]'} 客户端聚合记录 |")
    lines.append(f"| 流式不丢 | {'[OK]' if sr >= 0.95 else '[FAIL]'} |")
    lines.append(f"| 错误码合规 | {'[OK]' if p5_ok_pct >= 0.6 else '[WARN]'} |")
    lines.append(f"| Cooldown 区分 | {'[OK]' if p7.get('items') is not None else '[WARN]'} |")
    lines.append(f"| 稳态 QPS 上限 | ~{p6.get('qps_actual', 0):.2f} QPS（{(sr)*100:.1f}% 成功率）|")
    lines.append(f"| 单点故障 | [WARN] 单渠道 = 单 SPOF |")
    lines.append("")

    # 十、决策
    lines.append("## 十、决策建议")
    if pass_pct >= 95:
        lines.append(f"- [x] **接入**：通过率 {pass_pct:.1f}% ≥ 95%，关键功能基本 OK")
        lines.append(f"- [ ] 暂缓接入")
        lines.append(f"- [ ] 拒绝接入")
    elif pass_pct >= 85:
        lines.append(f"- [ ] 接入")
        lines.append(f"- [x] **暂缓接入**：通过率 {pass_pct:.1f}% 低于 95%")
        lines.append(f"- [ ] 拒绝接入")
    else:
        lines.append(f"- [ ] 接入")
        lines.append(f"- [ ] 暂缓接入")
        lines.append(f"- [x] **拒绝接入**：通过率 {pass_pct:.1f}% < 85%")
    lines.append("")
    return "\n".join(lines)


def render_json(ctx, ts):
    return {
        "channel": ctx.get("channel_name"),
        "base_url": ctx["base_url"],
        "started_at": ctx.get("start_str"),
        "ended_at": datetime.now().isoformat(),
        "phase1": _load(ctx, "phase1"),
        "phase2": _load(ctx, "phase2"),
        "phase3": _load(ctx, "phase3"),
        "phase4": _load(ctx, "phase4"),
        "phase5": _load(ctx, "phase5"),
        "phase6": _load(ctx, "phase6"),
        "phase7": _load(ctx, "phase7"),
    }


def run(ctx: dict) -> dict:
    ts = ctx.get("ts", time.strftime("%Y%m%d_%H%M%S"))
    md = render_md(ctx, ts)
    j = render_json(ctx, ts)
    md_path = os.path.join(ctx["work_dir"], f"report-{ts}.md")
    json_path = os.path.join(ctx["work_dir"], f"report-{ts}.json")
    with open(md_path, "w") as f:
        f.write(md)
    with open(json_path, "w") as f:
        json.dump(j, f, ensure_ascii=False, indent=2)
    return {"md_path": md_path, "json_path": json_path}
