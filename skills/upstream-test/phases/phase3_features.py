"""Phase 3：thinking / multimodal / tool calling。"""
import asyncio
import json
import os
import sys

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import http, auth_headers
from lib.png import mk_real_png


async def _thinking_anthropic(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {
        "model": model, "max_tokens": 1500,
        "thinking": {"type": "enabled", "budget_tokens": 1024},
        "messages": [{"role": "user", "content": "What is 17 * 23? Show reasoning."}],
    }
    r = await http("POST", f"{base}/v1/messages",
                   headers=auth_headers(key, anthropic=True, beta="extended-thinking-2025-05-14"),
                   body=body, timeout=60, session=session)
    has_thinking = False
    if r.json and isinstance(r.json, dict):
        for blk in r.json.get("content", []) or []:
            if isinstance(blk, dict) and blk.get("type") == "thinking" and blk.get("thinking"):
                has_thinking = True
                break
    return {"protocol": "anthropic", "model": model, "status": r.status,
            "ok": has_thinking, "has_thinking_block": has_thinking,
            "elapsed_ms": r.elapsed_ms, "error": r.error,
            "body_excerpt": (r.text or "")[:300]}


async def _thinking_openai(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model,
            "messages": [{"role": "user", "content": "What is 17 * 23?"}],
            "max_tokens": 800}
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    rc = ""
    if r.json and isinstance(r.json, dict):
        try:
            rc = r.json["choices"][0]["message"].get("reasoning_content") or ""
        except Exception:
            rc = ""
    return {"protocol": "openai-compat", "model": model, "status": r.status,
            "ok": bool(rc), "reasoning_content_len": len(rc),
            "elapsed_ms": r.elapsed_ms, "error": r.error,
            "body_excerpt": (r.text or "")[:300]}


async def _multimodal_openai(session, ctx, model, png_b64):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {
        "model": model, "max_tokens": 100,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "What color is this image? Answer in one word."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
        ]}],
    }
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    txt = ""
    if r.json and isinstance(r.json, dict):
        try:
            txt = r.json["choices"][0]["message"].get("content") or ""
        except Exception:
            pass
    ok = r.status == 200 and any(k in (txt or "").lower() for k in ["red", "orange", "红", "橙"])
    return {"protocol": "openai-vision", "model": model, "status": r.status,
            "ok": ok, "text": txt[:200], "elapsed_ms": r.elapsed_ms, "error": r.error}


async def _multimodal_anthropic(session, ctx, model, png_b64):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {
        "model": model, "max_tokens": 100,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                          "media_type": "image/png", "data": png_b64}},
            {"type": "text", "text": "What color is this? One word."},
        ]}],
    }
    r = await http("POST", f"{base}/v1/messages",
                   headers=auth_headers(key, anthropic=True), body=body,
                   timeout=60, session=session)
    txt = ""
    if r.json and isinstance(r.json, dict):
        for blk in r.json.get("content", []) or []:
            if isinstance(blk, dict) and blk.get("type") == "text":
                txt += blk.get("text", "")
    ok = r.status == 200 and any(k in (txt or "").lower() for k in ["red", "orange", "红", "橙"])
    return {"protocol": "anthropic-vision", "model": model, "status": r.status,
            "ok": ok, "text": txt[:200], "elapsed_ms": r.elapsed_ms, "error": r.error}


async def _multimodal_gemini(session, ctx, model, png_b64):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    url = f"{base}/gemini/v1beta/models/{model}:generateContent"
    body = {"contents": [{"role": "user", "parts": [
        {"text": "What color? One word."},
        {"inline_data": {"mime_type": "image/png", "data": png_b64}},
    ]}]}
    headers = {"Content-Type": "application/json", "x-goog-api-key": key,
               "Authorization": f"Bearer {key}"}
    r = await http("POST", url, headers=headers, body=body, timeout=60, session=session)
    txt = ""
    if r.json and isinstance(r.json, dict):
        try:
            txt = r.json["candidates"][0]["content"]["parts"][0].get("text", "")
        except Exception:
            pass
    ok = r.status == 200 and any(k in (txt or "").lower() for k in ["red", "orange", "红", "橙"])
    return {"protocol": "gemini-vision", "model": model, "status": r.status,
            "ok": ok, "text": txt[:200], "elapsed_ms": r.elapsed_ms, "error": r.error}


async def _tool_openai_stream(session, ctx, model):
    """SSE 流式：累积 chunks 看 tool_calls 增量。"""
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {
        "model": model, "stream": True, "max_tokens": 200,
        "messages": [{"role": "user", "content": "Get weather for Beijing"}],
        "tools": [{"type": "function", "function": {
            "name": "get_weather", "description": "Get weather",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                           "required": ["city"]}}}],
        "tool_choice": "auto",
    }
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    has_tc = "tool_calls" in (r.text or "") and ("function" in (r.text or ""))
    return {"protocol": "openai-stream-tool", "model": model, "status": r.status,
            "ok": has_tc, "tool_calls_in_chunks": has_tc,
            "elapsed_ms": r.elapsed_ms, "error": r.error}


async def _tool_anthropic(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {
        "model": model, "max_tokens": 300,
        "messages": [{"role": "user", "content": "Get weather for Beijing"}],
        "tools": [{"name": "get_weather", "description": "Get weather",
                   "input_schema": {"type": "object",
                                    "properties": {"city": {"type": "string"}},
                                    "required": ["city"]}}],
    }
    r = await http("POST", f"{base}/v1/messages",
                   headers=auth_headers(key, anthropic=True), body=body,
                   timeout=60, session=session)
    has_tu = False
    stop_reason = None
    if r.json and isinstance(r.json, dict):
        stop_reason = r.json.get("stop_reason")
        for blk in r.json.get("content", []) or []:
            if isinstance(blk, dict) and blk.get("type") == "tool_use":
                has_tu = True
                break
    return {"protocol": "anthropic-tool", "model": model, "status": r.status,
            "ok": has_tu, "has_tool_use_block": has_tu, "stop_reason": stop_reason,
            "elapsed_ms": r.elapsed_ms, "error": r.error}


async def run(ctx: dict) -> dict:
    reps = ctx.get("representatives", {})
    grouped = ctx.get("grouped", {})
    out = {"thinking": [], "multimodal": [], "tool_calling": []}

    png_path, png_b64 = mk_real_png()
    out["png_path"] = png_path
    out["png_size"] = len(png_b64)

    timeout = aiohttp.ClientTimeout(total=170)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        order = []

        # thinking 模型挑最多 3 个
        thinking_models = (grouped.get("thinking") or [])[:3]
        for m in thinking_models:
            if m.startswith("claude"):
                tasks.append(_thinking_anthropic(session, ctx, m)); order.append("thinking")
            else:
                tasks.append(_thinking_openai(session, ctx, m)); order.append("thinking")

        # multimodal 三协议
        oa_vision = next((m for m in (reps.get("openai") or []) if "4o" in m or "vision" in m or "gpt-4" in m),
                        (reps.get("openai") or [None])[0])
        an_vision = (reps.get("anthropic") or [None])[0]
        gm_vision = (reps.get("gemini") or [None])[0]
        if oa_vision:
            tasks.append(_multimodal_openai(session, ctx, oa_vision, png_b64)); order.append("multimodal")
        if an_vision:
            tasks.append(_multimodal_anthropic(session, ctx, an_vision, png_b64)); order.append("multimodal")
        if gm_vision:
            tasks.append(_multimodal_gemini(session, ctx, gm_vision, png_b64)); order.append("multimodal")

        # tool calling
        oa_chat = (reps.get("openai") or reps.get("cn") or [None])[0]
        if oa_chat:
            tasks.append(_tool_openai_stream(session, ctx, oa_chat)); order.append("tool_calling")
        if an_vision:
            tasks.append(_tool_anthropic(session, ctx, an_vision)); order.append("tool_calling")

        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True),
                                             timeout=170)
        except asyncio.TimeoutError:
            results = [Exception("phase3_overall_timeout")] * len(tasks)

    for i, r in enumerate(results):
        bucket = order[i] if i < len(order) else "thinking"
        if isinstance(r, Exception):
            out[bucket].append({"error": f"{type(r).__name__}: {r}"})
        else:
            out[bucket].append(r)
    return out


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase3.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
