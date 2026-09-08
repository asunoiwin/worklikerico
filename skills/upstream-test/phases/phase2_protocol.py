"""Phase 2：8 端点协议矩阵。"""
import asyncio
import json
import os
import sys

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import http, auth_headers


def _pick_first(reps: dict, *cats):
    """从 representatives 里按 cats 顺序找第一个非空类的第一个模型。"""
    for c in cats:
        lst = reps.get(c) or []
        if lst:
            return lst[0]
    return None


def _pick_chat_model(reps):
    """优先 openai > anthropic > gemini > cn。"""
    return _pick_first(reps, "openai", "anthropic", "gemini", "cn")


async def _case_chat(session, ctx, model, stream=False, tools=False):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Say 'hi' in one word."}],
        "max_tokens": 32,
    }
    if stream:
        body["stream"] = True
    if tools:
        body["tools"] = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                               "required": ["city"]},
            },
        }]
        body["messages"] = [{"role": "user", "content": "What's the weather in Beijing?"}]
        body["tool_choice"] = "auto"
    r = await http("POST", f"{base}/v1/chat/completions",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    return _record(f"/v1/chat/completions", model,
                   "stream" if stream else ("tool_calling" if tools else "basic"), r)


async def _case_messages(session, ctx, model, stream=False, thinking=False):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    headers = auth_headers(key, anthropic=True,
                           beta=("extended-thinking-2025-05-14" if thinking else None))
    body = {
        "model": model,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Say hi."}],
    }
    if stream:
        body["stream"] = True
    if thinking:
        body["thinking"] = {"type": "enabled", "budget_tokens": 1024}
        body["max_tokens"] = 1500
    r = await http("POST", f"{base}/v1/messages",
                   headers=headers, body=body, timeout=60, session=session)
    case = "thinking" if thinking else ("stream" if stream else "basic")
    return _record("/v1/messages", model, case, r)


async def _case_gemini_generate(session, ctx, model, stream=False):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    method = "streamGenerateContent" if stream else "generateContent"
    url = f"{base}/gemini/v1beta/models/{model}:{method}"
    body = {"contents": [{"role": "user", "parts": [{"text": "Say hi"}]}]}
    headers = {"Content-Type": "application/json", "x-goog-api-key": key,
               "Authorization": f"Bearer {key}"}
    r = await http("POST", url, headers=headers, body=body, timeout=60, session=session)
    return _record(f"/gemini/...:{method}", model, "stream" if stream else "basic", r)


async def _case_responses(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model, "input": "Say hi.", "max_output_tokens": 32}
    r = await http("POST", f"{base}/v1/responses",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    return _record("/v1/responses", model, "basic", r)


async def _case_embeddings(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model, "input": "hello world"}
    r = await http("POST", f"{base}/v1/embeddings",
                   headers=auth_headers(key), body=body, timeout=30, session=session)
    rec = _record("/v1/embeddings", model, "dims", r)
    if r.status == 200 and isinstance(r.json, dict):
        try:
            rec["dims"] = len(r.json["data"][0]["embedding"])
        except Exception:
            pass
    return rec


async def _case_image(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model, "prompt": "a red square", "n": 1, "size": "512x512"}
    r = await http("POST", f"{base}/v1/images/generations",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    return _record("/v1/images/generations", model, "n=1", r)


async def _case_tts(session, ctx, model):
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    body = {"model": model, "input": "Hello", "voice": "alloy", "response_format": "mp3"}
    r = await http("POST", f"{base}/v1/audio/speech",
                   headers=auth_headers(key), body=body, timeout=60, session=session)
    rec = _record("/v1/audio/speech", model, "bytes", r)
    rec["body_bytes"] = len(r.text or "")
    return rec


async def _case_stt(session, ctx, model):
    """multipart 上传一个微小 mp3（实际是空 wav 头），让上游自己回 400/422 也算调通了路径。"""
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    # 构造一个最小 wav (44 字节头，0 数据)
    import struct
    wav = b"RIFF" + struct.pack("<I", 36) + b"WAVE" + b"fmt " + struct.pack("<I", 16)
    wav += struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16) + b"data" + struct.pack("<I", 0)
    boundary = "----upstreamtest"
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}".encode())
    parts.append(f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n"
                 "Content-Type: audio/wav\r\n\r\n".encode() + wav)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    headers = {"Authorization": f"Bearer {key}",
               "Content-Type": f"multipart/form-data; boundary={boundary}"}
    r = await http("POST", f"{base}/v1/audio/transcriptions",
                   headers=headers, raw_body=body, timeout=60, session=session)
    return _record("/v1/audio/transcriptions", model, "text", r)


def _record(endpoint, model, case, resp):
    ok = 200 <= resp.status < 300
    return {
        "endpoint": endpoint,
        "model": model,
        "case": case,
        "status": resp.status,
        "elapsed_ms": resp.elapsed_ms,
        "ok": ok,
        "error": resp.error,
        "body_excerpt": (resp.text or "")[:400],
    }


async def run(ctx: dict) -> dict:
    reps = ctx.get("representatives", {})
    cases = []

    chat_model = _pick_chat_model(reps)
    claude_model = _pick_first(reps, "anthropic")
    gemini_model = _pick_first(reps, "gemini")
    openai_model = _pick_first(reps, "openai")
    embed_model = _pick_first(reps, "embedding")
    image_model = _pick_first(reps, "image")
    audio_models = reps.get("audio") or []
    tts_model = next((m for m in audio_models if "tts" in m.lower()), None)
    stt_model = next((m for m in audio_models if "whisper" in m.lower() or "transcribe" in m.lower()), None)

    timeout = aiohttp.ClientTimeout(total=180)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        # /v1/chat/completions: basic + stream + tool_calling
        for cat in ["openai", "anthropic", "gemini", "cn"]:
            m = _pick_first(reps, cat)
            if m:
                tasks.append(_case_chat(session, ctx, m, stream=False))
        if chat_model:
            tasks.append(_case_chat(session, ctx, chat_model, stream=True))
            tasks.append(_case_chat(session, ctx, chat_model, tools=True))

        if claude_model:
            tasks.append(_case_messages(session, ctx, claude_model, stream=False))
            tasks.append(_case_messages(session, ctx, claude_model, stream=True))

        if gemini_model:
            tasks.append(_case_gemini_generate(session, ctx, gemini_model, stream=False))
            tasks.append(_case_gemini_generate(session, ctx, gemini_model, stream=True))

        if openai_model:
            tasks.append(_case_responses(session, ctx, openai_model))

        if embed_model:
            tasks.append(_case_embeddings(session, ctx, embed_model))
        if image_model:
            tasks.append(_case_image(session, ctx, image_model))
        if tts_model:
            tasks.append(_case_tts(session, ctx, tts_model))
        if stt_model:
            tasks.append(_case_stt(session, ctx, stt_model))

        try:
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True),
                                             timeout=170)
        except asyncio.TimeoutError:
            results = [{"error": "phase2_overall_timeout"}]

    cases = []
    for r in results:
        if isinstance(r, Exception):
            cases.append({"error": f"{type(r).__name__}: {r}"})
        elif isinstance(r, dict):
            cases.append(r)

    ok = sum(1 for c in cases if c.get("ok"))
    return {"total": len(cases), "ok": ok, "cases": cases}


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase2.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
