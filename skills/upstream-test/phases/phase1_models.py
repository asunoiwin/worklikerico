"""Phase 1：GET /v1/models 探测分类。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.http import http, auth_headers
from lib.classify import group_models, pick_representatives


async def run(ctx: dict) -> dict:
    base = ctx["base_url"].rstrip("/")
    key = ctx["api_key"]
    url = f"{base}/v1/models"
    resp = await http("GET", url, headers=auth_headers(key), timeout=30)
    out = {
        "endpoint": url,
        "status": resp.status,
        "elapsed_ms": resp.elapsed_ms,
        "error": resp.error,
        "models": [],
        "grouped": {},
        "representatives": {},
        "summary": {},
    }
    if resp.status == 200 and isinstance(resp.json, dict):
        items = resp.json.get("data") or []
        ids = [it.get("id") for it in items if isinstance(it, dict) and it.get("id")]
        out["models"] = ids
        grouped = group_models(ids)
        out["grouped"] = grouped
        out["representatives"] = pick_representatives(grouped, per_cat=2)
        out["summary"] = {k: len(v) for k, v in grouped.items()}
        out["summary"]["total"] = len(ids)
    else:
        out["body_excerpt"] = (resp.text or "")[:500]
    return out


def write_data(ctx: dict, out: dict):
    path = os.path.join(ctx["data_dir"], "phase1.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return path
