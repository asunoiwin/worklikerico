"""Phase 7：失败项 wait 70s + 3 轮重测。"""
import asyncio
import json
import os
import sys

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import http, auth_headers


def _collect_failures(ctx: dict) -> list:
    """从 phase2 / phase3 的 JSON 中收集失败 case。"""
    fails = []
    for pname in ("phase2", "phase3"):
        p = os.path.join(ctx["data_dir"], f"{pname}.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                data = json.load(f)
        except Exception:
            continue
        if pname == "phase2":
            for c in data.get("cases", []):
                if not c.get("ok") and c.get("model"):
                    fails.append({"phase": "phase2", "endpoint": c.get("endpoint"),
                                  "model": c["model"], "case": c.get("case"),
                                  "first_status": c.get("status"),
                                  "first_error": c.get("error")})
        else:
            for bucket in ("thinking", "multimodal", "tool_calling"):
                for c in data.get(bucket, []):
                    if not c.get("ok") and c.get("model"):
                        fails.append({"phase": "phase3", "endpoint": c.get("protocol"),
                                      "model": c["model"], "case": bucket,
                                      "first_status": c.get("status"),
                                      "first_error": c.get("error")})
    return fails


async def _retest_one(session, ctx, item):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    model = item["model"]
    ep = item.get("endpoint") or "/v1/chat/completions"

    if "messages" in ep or "anthropic" in ep:
        url = f"{base}/v1/messages"
        body = {"model": model, "max_tokens": 32,
                "messages": [{"role": "user", "content": "hi"}]}
        headers = auth_headers(key, anthropic=True)
    elif "gemini" in ep:
        url = f"{base}/gemini/v1beta/models/{model}:generateContent"
        body = {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
        headers = {"Content-Type": "application/json", "x-goog-api-key": key,
                   "Authorization": f"Bearer {key}"}
    elif "embeddings" in ep:
        url = f"{base}/v1/embeddings"
        body = {"model": model, "input": "hi"}
        headers = auth_headers(key)
    elif "images" in ep:
        url = f"{base}/v1/images/generations"
        body = {"model": model, "prompt": "red", "n": 1, "size": "512x512"}
        headers = auth_headers(key)
    else:
        url = f"{base}/v1/chat/completions"
        body = {"model": model, "max_tokens": 32,
                "messages": [{"role": "user", "content": "hi"}]}
        headers = auth_headers(key)
    r = await http("POST", url, headers=headers, body=body, timeout=60, session=session)
    return {"status": r.status, "ok": 200 <= r.status < 300, "elapsed_ms": r.elapsed_ms,
            "error": r.error, "excerpt": (r.text or "")[:200]}


async def run(ctx: dict) -> dict:
    fails = _collect_failures(ctx)
    out = {"total_failures": len(fails), "items": []}
    if not fails:
        return out

    print(f"  [phase7] 等 70 秒让 cooldown 过期...", flush=True)
    await asyncio.sleep(70)

    timeout = aiohttp.ClientTimeout(total=170)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for item in fails:
            rounds = []
            for r_idx in range(3):
                rounds.append(await _retest_one(session, ctx, item))
                if r_idx < 2:
                    await asyncio.sleep(5)
            ok_count = sum(1 for r in rounds if r["ok"])
            if ok_count == 3:
                verdict = "stable_ok"
            elif ok_count == 0:
                verdict = "stable_fail"
            else:
                verdict = "intermittent"
            out["items"].append({**item, "rounds": rounds,
                                 "ok_count": ok_count, "verdict": verdict})
    return out


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase7.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
