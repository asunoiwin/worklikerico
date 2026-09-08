"""Phase 6：稳态压测 + 长上下文 + CF100s。"""
import asyncio
import json
import os
import sys
import time

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import stream_http, auth_headers
from lib.pct import stats


def _gen_long_context(approx_tokens: int) -> str:
    """生成约 approx_tokens 个 token 的英文（按 4 char ~ 1 token 估算）。"""
    base = "The quick brown fox jumps over the lazy dog. " * 100
    char_target = approx_tokens * 4
    s = (base * (char_target // len(base) + 1))[:char_target]
    return s


async def _worker(session, ctx, model, ctx_text, deadline, results, idx, fail_log):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    while time.time() < deadline:
        body = {
            "model": model, "stream": True, "max_tokens": 64,
            "messages": [
                {"role": "user", "content": ctx_text + "\n\nReply: ok"}
            ],
        }
        t0 = time.time()
        r = await stream_http("POST", f"{base}/v1/chat/completions",
                              headers=auth_headers(key), body=body,
                              timeout=60, session=session)
        ok = r["status"] == 200 and (r.get("error") is None) and r.get("chunk_count", 0) > 0
        rec = {
            "t": int(t0), "status": r["status"], "ok": ok,
            "ttfb_ms": r.get("ttfb_ms"), "max_chunk_gap_ms": r.get("max_chunk_gap_ms"),
            "total_ms": r.get("total_ms"), "chunks": r.get("chunk_count"),
            "error": r.get("error"),
        }
        results.append(rec)
        if not ok:
            fail_log.append(int(t0))


async def run(ctx: dict) -> dict:
    dur = int(ctx.get("stress_dur_sec", 300))
    cc = int(ctx.get("stress_cc", 20))
    reps = ctx.get("representatives", {})
    model = (reps.get("openai") or reps.get("cn") or reps.get("gemini") or [None])[0]

    out = {"config": {"dur_sec": dur, "cc": cc, "model": model}}
    if not model:
        out["error"] = "no chat-capable model picked"
        return out

    # 长上下文 ~ 5k tokens（不要过大避免成本爆炸）
    ctx_text = _gen_long_context(5000)
    out["config"]["context_chars"] = len(ctx_text)

    deadline = time.time() + dur
    results = []
    fail_log = []
    timeout = aiohttp.ClientTimeout(total=dur + 60)
    connector = aiohttp.TCPConnector(limit=cc * 2)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        tasks = [_worker(session, ctx, model, ctx_text, deadline, results, i, fail_log)
                 for i in range(cc)]
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True),
                                   timeout=dur + 30)
        except asyncio.TimeoutError:
            pass

    total = len(results)
    ok = sum(1 for r in results if r["ok"])
    ttfbs = [r["ttfb_ms"] for r in results if r["ttfb_ms"]]
    gaps = [r["max_chunk_gap_ms"] for r in results if r.get("max_chunk_gap_ms")]
    totals = [r["total_ms"] for r in results if r.get("total_ms")]
    cf100s = sum(1 for g in gaps if g > 100_000)

    # 连续失败窗口
    fails_sorted = sorted(fail_log)
    max_consec = 0
    cur_start = None
    cur_end = None
    last = None
    for t in fails_sorted:
        if last is None or t - last > 5:
            if cur_start is not None:
                max_consec = max(max_consec, cur_end - cur_start)
            cur_start = t
        cur_end = t
        last = t
    if cur_start is not None:
        max_consec = max(max_consec, cur_end - cur_start)

    out.update({
        "total": total, "ok": ok, "fail": total - ok,
        "success_rate": (ok / total) if total else 0,
        "ttfb_stats": stats(ttfbs),
        "max_chunk_gap_stats": stats(gaps),
        "total_ms_stats": stats(totals),
        "cf_100s_count": cf100s,
        "fail_window_max_sec": max_consec,
        "qps_actual": total / dur if dur else 0,
    })
    return out


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase6.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
