#!/usr/bin/env python3
"""上游供应商接入全维度测试 — 主入口。

Usage:
    BASE_URL=https://panmode.com API_KEY=sk-xxx \\
    [CHANNEL_NAME=foo] [STRESS_DUR_SEC=300] [STRESS_CC=20] \\
    [SKIP_PHASES=phase4,phase6] \\
    python3 run.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from phases import (
    phase1_models, phase2_protocol, phase3_features, phase4_billing,
    phase5_errors, phase6_stress, phase7_reverify, phase8_report,
)


def parse_env() -> dict:
    base = os.environ.get("BASE_URL")
    key = os.environ.get("API_KEY")
    if not base or not key:
        print("ERROR: BASE_URL 和 API_KEY 必填环境变量", file=sys.stderr)
        sys.exit(2)
    skip = set(s.strip() for s in (os.environ.get("SKIP_PHASES") or "").split(",") if s.strip())
    ts = time.strftime("%Y%m%d_%H%M%S")
    work_dir = ROOT
    data_dir = os.path.join(work_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return {
        "base_url": base.rstrip("/"),
        "api_key": key,
        "channel_name": os.environ.get("CHANNEL_NAME") or "unnamed",
        "stress_dur_sec": int(os.environ.get("STRESS_DUR_SEC", "300")),
        "stress_cc": int(os.environ.get("STRESS_CC", "20")),
        "skip_phases": skip,
        "ts": ts,
        "start_str": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "work_dir": work_dir,
        "data_dir": data_dir,
    }


async def main():
    ctx = parse_env()
    print(f"[upstream-test] BASE={ctx['base_url']} CHANNEL={ctx['channel_name']} "
          f"STRESS={ctx['stress_dur_sec']}s/{ctx['stress_cc']}cc")
    print(f"[upstream-test] data_dir={ctx['data_dir']}")
    print(f"[upstream-test] skip={ctx['skip_phases']}")

    # Phase 1（必跑，后续 phase 依赖 representatives）
    if "phase1" in ctx["skip_phases"]:
        print("[phase1] 跳过 — 但其他 phase 依赖此结果，强制跑一遍")
    print("\n[phase1] 模型探测...")
    p1 = await phase1_models.run(ctx)
    phase1_models.write_data(ctx, p1)
    ctx["representatives"] = p1.get("representatives", {})
    ctx["grouped"] = p1.get("grouped", {})
    print(f"[phase1] 拿到 {p1.get('summary',{}).get('total',0)} 个模型，状态 {p1.get('status')}")

    # Phase 2
    if "phase2" in ctx["skip_phases"]:
        print("[phase2] 跳过")
    else:
        print("\n[phase2] 协议矩阵并发...")
        p2 = await phase2_protocol.run(ctx)
        phase2_protocol.write_data(ctx, p2)
        print(f"[phase2] {p2.get('ok')}/{p2.get('total')} 通过")

    # Phase 3
    if "phase3" in ctx["skip_phases"]:
        print("[phase3] 跳过")
    else:
        print("\n[phase3] 特性测试...")
        p3 = await phase3_features.run(ctx)
        phase3_features.write_data(ctx, p3)
        print(f"[phase3] thinking={len(p3.get('thinking',[]))} "
              f"multimodal={len(p3.get('multimodal',[]))} "
              f"tool={len(p3.get('tool_calling',[]))}")

    # Phase 4
    if "phase4" in ctx["skip_phases"]:
        print("[phase4] 跳过")
    else:
        print("\n[phase4] 计费对账（30 次 token + 5 次 per-call）...")
        p4 = await phase4_billing.run(ctx)
        phase4_billing.write_data(ctx, p4)
        tm = p4.get("token_mode") or {}
        print(f"[phase4] token: ok={tm.get('ok')}/{tm.get('n')} "
              f"prompt={tm.get('prompt_tokens_sum')}")

    # Phase 5
    if "phase5" in ctx["skip_phases"]:
        print("[phase5] 跳过")
    else:
        print("\n[phase5] 错误码边界...")
        p5 = await phase5_errors.run(ctx)
        phase5_errors.write_data(ctx, p5)
        print(f"[phase5] {p5.get('ok')}/{p5.get('total')} 通过")

    # Phase 6
    if "phase6" in ctx["skip_phases"]:
        print("[phase6] 跳过")
    else:
        print(f"\n[phase6] 稳态压测 {ctx['stress_dur_sec']}s × {ctx['stress_cc']}cc...")
        p6 = await phase6_stress.run(ctx)
        phase6_stress.write_data(ctx, p6)
        print(f"[phase6] {p6.get('ok')}/{p6.get('total')} "
              f"成功率 {(p6.get('success_rate') or 0)*100:.1f}%")

    # Phase 7
    if "phase7" in ctx["skip_phases"]:
        print("[phase7] 跳过")
    else:
        print("\n[phase7] 失败项重测...")
        p7 = await phase7_reverify.run(ctx)
        phase7_reverify.write_data(ctx, p7)
        print(f"[phase7] 重测 {p7.get('total_failures')} 项")

    # Phase 8 报告
    print("\n[phase8] 渲染报告...")
    rep = phase8_report.run(ctx)
    print(f"[phase8] 完成 -> {rep['md_path']}")
    print(f"[phase8] 完成 -> {rep['json_path']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[upstream-test] 中断")
        sys.exit(130)
