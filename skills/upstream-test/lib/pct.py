"""百分位计算（不依赖 numpy）。"""
from typing import List, Optional


def pct(arr: List[float], p: float) -> Optional[float]:
    """计算分位数 p（0~100）。线性插值。"""
    if not arr:
        return None
    s = sorted(arr)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def stats(arr: List[float]) -> dict:
    if not arr:
        return {"n": 0, "min": None, "max": None, "avg": None,
                "p50": None, "p95": None, "p99": None}
    return {
        "n": len(arr),
        "min": min(arr),
        "max": max(arr),
        "avg": sum(arr) / len(arr),
        "p50": pct(arr, 50),
        "p95": pct(arr, 95),
        "p99": pct(arr, 99),
    }
