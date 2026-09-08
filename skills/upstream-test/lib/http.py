"""统一异步 HTTP 工具，所有异常捕获后返回 status+body。"""
import asyncio
import json as _json
import time
from typing import Any, Dict, Optional, Tuple

try:
    import aiohttp
except ImportError:
    raise SystemExit("缺少依赖 aiohttp，请 pip3 install aiohttp")


DEFAULT_TIMEOUT = 60


class HttpResp:
    __slots__ = ("status", "headers", "text", "json", "elapsed_ms", "error", "raw")

    def __init__(self, status=0, headers=None, text="", json_obj=None,
                 elapsed_ms=0.0, error=None, raw=None):
        self.status = status
        self.headers = headers or {}
        self.text = text
        self.json = json_obj
        self.elapsed_ms = elapsed_ms
        self.error = error
        self.raw = raw

    def to_dict(self):
        return {
            "status": self.status,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "error": self.error,
            "body_excerpt": (self.text or "")[:800],
        }


async def http(method: str, url: str,
               headers: Optional[Dict[str, str]] = None,
               body: Any = None,
               timeout: int = DEFAULT_TIMEOUT,
               session: Optional[aiohttp.ClientSession] = None,
               raw_body: Optional[bytes] = None) -> HttpResp:
    """统一 HTTP 调用：永不抛异常，所有失败都填到 HttpResp.error。"""
    headers = dict(headers or {})
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    t0 = time.time()
    data = None
    json_body = None
    if raw_body is not None:
        data = raw_body
    elif isinstance(body, (bytes, bytearray)):
        data = body
    elif isinstance(body, str):
        data = body
    elif body is not None:
        json_body = body
    try:
        to = aiohttp.ClientTimeout(total=timeout)
        async with session.request(method, url, headers=headers, data=data,
                                   json=json_body, timeout=to) as resp:
            text = await resp.text()
            elapsed = (time.time() - t0) * 1000
            j = None
            try:
                j = _json.loads(text)
            except Exception:
                pass
            return HttpResp(status=resp.status,
                            headers={k.lower(): v for k, v in resp.headers.items()},
                            text=text, json_obj=j, elapsed_ms=elapsed)
    except asyncio.TimeoutError:
        return HttpResp(status=0, elapsed_ms=(time.time() - t0) * 1000,
                        error=f"timeout({timeout}s)")
    except Exception as e:
        return HttpResp(status=0, elapsed_ms=(time.time() - t0) * 1000,
                        error=f"{type(e).__name__}: {str(e)[:200]}")
    finally:
        if own_session:
            await session.close()


async def stream_http(method: str, url: str,
                      headers: Optional[Dict[str, str]] = None,
                      body: Any = None,
                      timeout: int = DEFAULT_TIMEOUT,
                      session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
    """流式请求：返回 ttfb / max_chunk_gap / chunks / final_text。"""
    headers = dict(headers or {})
    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    t0 = time.time()
    ttfb = None
    last_t = t0
    max_gap = 0.0
    chunks = []
    raw_text_parts = []
    error = None
    status = 0
    try:
        to = aiohttp.ClientTimeout(total=timeout)
        async with session.request(method, url, headers=headers,
                                   json=body if not isinstance(body, (str, bytes)) else None,
                                   data=body if isinstance(body, (str, bytes)) else None,
                                   timeout=to) as resp:
            status = resp.status
            async for line in resp.content:
                now = time.time()
                if ttfb is None:
                    ttfb = (now - t0) * 1000
                gap = (now - last_t) * 1000
                if gap > max_gap:
                    max_gap = gap
                last_t = now
                try:
                    raw_text_parts.append(line.decode("utf-8", errors="ignore"))
                except Exception:
                    pass
                chunks.append(line)
    except asyncio.TimeoutError:
        error = f"timeout({timeout}s)"
    except Exception as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        if own_session:
            await session.close()
    total = (time.time() - t0) * 1000
    return {
        "status": status,
        "ttfb_ms": round(ttfb, 1) if ttfb else None,
        "max_chunk_gap_ms": round(max_gap, 1),
        "total_ms": round(total, 1),
        "chunk_count": len(chunks),
        "raw": "".join(raw_text_parts),
        "error": error,
    }


def auth_headers(api_key: str, anthropic: bool = False, beta: Optional[str] = None) -> Dict[str, str]:
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if anthropic:
        h["x-api-key"] = api_key
        h["anthropic-version"] = "2023-06-01"
        if beta:
            h["anthropic-beta"] = beta
    return h
