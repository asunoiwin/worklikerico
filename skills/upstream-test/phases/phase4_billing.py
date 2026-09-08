"""Phase 4：计费对账（token + per-call）。"""
import asyncio
import json
import os
import sys
import time

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import http, auth_headers


N_TOKEN = 30
N_PERCALL = 5  # image 测试少跑几次免得钱


async def _one_chat(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model, "max_tokens": 64,
            "messages": [{"role": "user", "content": "Reply with 5 short words."}]}
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    rec = {"ok": 200 <= r.status < 300, "status": r.status, "elapsed_ms": r.elapsed_ms,
           "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if r.json and isinstance(r.json, dict):
        u = r.json.get("usage") or {}
        rec["prompt_tokens"] = u.get("prompt_tokens", 0) or 0
        rec["completion_tokens"] = u.get("completion_tokens", 0) or 0
        rec["total_tokens"] = u.get("total_tokens", 0) or 0
    return rec


async def _one_image(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model, "prompt": "tiny red square", "n": 1, "size": "512x512"}
    r = await http("POST", f"{base}/v1/images/generations",
                   headers=auth_headers(key), body=body, timeout=90, session=session)
    return {"ok": 200 <= r.status < 300, "status": r.status, "elapsed_ms": r.elapsed_ms}


async def run(ctx: dict) -> dict:
    reps = ctx.get("representatives", {})
    out = {"token_mode": None, "percall_mode": None, "window_start": None, "window_end": None}

    # 选 token 模型（优先 gpt-4o-mini）
    openai_models = reps.get("openai") or []
    token_model = next((m for m in openai_models if "mini" in m.lower()), None) \
        or (openai_models[0] if openai_models else None) \
        or (reps.get("cn") or [None])[0]
    image_model = (reps.get("image") or [None])[0]

    out["window_start"] = int(time.time())
    timeout = aiohttp.ClientTimeout(total=170)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if token_model:
            results = await asyncio.gather(
                *[_one_chat(session, ctx, token_model) for _ in range(N_TOKEN)],
                return_exceptions=True)
            recs = [r for r in results if isinstance(r, dict)]
            ok = [r for r in recs if r["ok"]]
            out["token_mode"] = {
                "model": token_model, "n": len(recs), "ok": len(ok),
                "prompt_tokens_sum": sum(r["prompt_tokens"] for r in ok),
                "completion_tokens_sum": sum(r["completion_tokens"] for r in ok),
                "total_tokens_sum": sum(r["total_tokens"] for r in ok),
            }
        if image_model:
            results = await asyncio.gather(
                *[_one_image(session, ctx, image_model) for _ in range(N_PERCALL)],
                return_exceptions=True)
            recs = [r for r in results if isinstance(r, dict)]
            ok = [r for r in recs if r["ok"]]
            out["percall_mode"] = {
                "model": image_model, "n": len(recs), "ok": len(ok),
                "calls_billable": len(ok),
            }
    out["window_end"] = int(time.time())
    out["note"] = "无 admin SQL 端点访问，仅记录客户端聚合；服务器侧对账需另接 admin API"
    return out


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase4.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
