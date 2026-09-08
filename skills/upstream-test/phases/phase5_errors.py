"""Phase 5：错误码边界。"""
import asyncio
import json
import os
import sys

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import http, auth_headers


async def _bad_key(session, ctx):
    base = ctx["base_url"].rstrip("/")
    body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 4}
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers={"Content-Type": "application/json",
                            "Authorization": "Bearer sk-fake-invalid-xxx"},
                   body=body, timeout=30, session=session)
    return {"case": "无效 key", "expected": 401, "actual": r.status,
            "ok": r.status == 401, "body_excerpt": (r.text or "")[:200]}


async def _no_such_model(session, ctx):
    base = ctx["base_url"].rstrip("/")
    body = {"model": "no-such-model-xyz-12345",
            "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4}
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=auth_headers(ctx["api_key"]), body=body, timeout=30, session=session)
    body_l = (r.text or "").lower()
    has_no_channel = "no_channel" in body_l or "no channel" in body_l or "not_found" in body_l \
        or "model_not_found" in body_l or "model not found" in body_l
    return {"case": "不存在的模型", "expected": "503/404 + no_channel/not_found",
            "actual": r.status, "ok": r.status in (404, 503) and has_no_channel,
            "body_excerpt": (r.text or "")[:300]}


async def _malformed_json(session, ctx):
    base = ctx["base_url"].rstrip("/")
    headers = auth_headers(ctx["api_key"])
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=headers, raw_body=b"{not valid json{{", timeout=30, session=session)
    return {"case": "畸形 JSON", "expected": 400,
            "actual": r.status, "ok": r.status == 400,
            "body_excerpt": (r.text or "")[:200]}


async def _high_concurrency(session, ctx):
    """80 并发，看是否 429。"""
    base = ctx["base_url"].rstrip("/")
    reps = ctx.get("representatives", {})
    model = (reps.get("openai") or reps.get("cn") or ["gpt-4o-mini"])[0]
    body = {"model": model, "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 4}

    async def one():
        r = await http("POST", f"{base}/v1/chat/completions",
                       headers=auth_headers(ctx["api_key"]), body=body,
                       timeout=30, session=session)
        return r.status

    results = await asyncio.gather(*[one() for _ in range(80)], return_exceptions=True)
    statuses = [r for r in results if isinstance(r, int)]
    has_429 = any(s == 429 for s in statuses)
    all_200 = all(s == 200 for s in statuses) and len(statuses) == 80
    return {"case": "80 并发 chat", "expected": "429 或 全 200",
            "actual": f"200={statuses.count(200)} 429={statuses.count(429)} other={len(statuses)-statuses.count(200)-statuses.count(429)}",
            "ok": has_429 or all_200,
            "note": "无 429 不阻塞，记录配置"}


async def _cooldown_followup(session, ctx):
    """触发 cooldown 边界（通用方式：重复调失败模型，看下次返回是否有 retry-after / 503）。
    通用实现：先调一次失败的不存在模型，紧跟再调，记录 retry-after header。"""
    base = ctx["base_url"].rstrip("/")
    body = {"model": "definitely-not-exists-zzz",
            "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4}
    r1 = await http("POST", f"{base}/v1/chat/completions",
                    headers=auth_headers(ctx["api_key"]), body=body, timeout=30, session=session)
    await asyncio.sleep(0.5)
    r2 = await http("POST", f"{base}/v1/chat/completions",
                    headers=auth_headers(ctx["api_key"]), body=body, timeout=30, session=session)
    retry_after = r2.headers.get("retry-after")
    return {"case": "cooldown 期间再调", "expected": "503 + retry-after 或一致 503",
            "actual": f"r1={r1.status} r2={r2.status} retry-after={retry_after}",
            "ok": r2.status in (404, 503)}


async def run(ctx: dict) -> dict:
    timeout = aiohttp.ClientTimeout(total=170)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        cases = await asyncio.gather(
            _bad_key(session, ctx),
            _no_such_model(session, ctx),
            _malformed_json(session, ctx),
            _high_concurrency(session, ctx),
            _cooldown_followup(session, ctx),
            return_exceptions=True,
        )
    out_cases = []
    for c in cases:
        if isinstance(c, Exception):
            out_cases.append({"error": f"{type(c).__name__}: {c}"})
        else:
            out_cases.append(c)
    ok = sum(1 for c in out_cases if c.get("ok"))
    return {"total": len(out_cases), "ok": ok, "cases": out_cases}


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase5.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
