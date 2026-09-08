"""按命名模式将模型分类。"""
import re
from typing import Dict, List


CATEGORIES = ["openai", "anthropic", "gemini", "cn", "image", "embedding",
              "rerank", "audio", "video", "thinking", "other"]


def classify(model_id: str) -> List[str]:
    """返回模型可能归属的所有类别（一个模型可多归类，如 thinking + openai）。"""
    m = (model_id or "").lower()
    cats = []

    if re.match(r"^(gpt-|o1-|o3-|o4-|chatgpt|dall-e|davinci|babbage|text-davinci)", m):
        cats.append("openai")
    if m.startswith("claude-") or m.startswith("claude_"):
        cats.append("anthropic")
    if m.startswith("gemini-") or m.startswith("gemini_") or m.startswith("models/gemini"):
        cats.append("gemini")
    if re.match(r"^(deepseek|qwen|glm|kimi|moonshot|doubao|minimax|yi-|baichuan|spark|hunyuan|ernie|step-|abab)", m):
        cats.append("cn")
    if re.match(r"^(flux|midjourney|mj-|stable-|sd-|seedream|recraft|ideogram|dall-e|imagen)", m) \
            or "image" in m and "embedding" not in m:
        cats.append("image")
    if "embedding" in m or m.endswith("-embed") or "-embed-" in m or m.startswith("text-embedding"):
        cats.append("embedding")
    if "rerank" in m:
        cats.append("rerank")
    if m.startswith("whisper") or m.startswith("tts-") or "transcribe" in m \
            or "-audio-" in m or "-realtime-" in m:
        cats.append("audio")
    if re.match(r"^(kling|sora|veo|runway|pika|cogvideox|hailuo)", m):
        cats.append("video")
    if m.endswith("-thinking") or m.endswith("-r1") or "-reasoner" in m \
            or m.startswith("o1-") or m.startswith("o3-") or "thinking" in m:
        cats.append("thinking")

    if not cats:
        cats.append("other")
    return cats


def group_models(model_ids: List[str]) -> Dict[str, List[str]]:
    """返回 {category: [model_id, ...]}。"""
    out = {c: [] for c in CATEGORIES}
    for mid in model_ids:
        for c in classify(mid):
            out[c].append(mid)
    return out


_LEGACY = ("davinci", "babbage", "ada", "curie", "text-davinci",
           "text-babbage", "text-ada", "text-curie", "code-davinci",
           "instruct", "edit", "search-")


def _is_legacy(m: str) -> bool:
    ml = m.lower()
    return any(k in ml for k in _LEGACY)


def pick_representatives(grouped: Dict[str, List[str]], per_cat: int = 2) -> Dict[str, List[str]]:
    """每类挑 newest + oldest 各一个（newest = 字典序大；oldest = 字典序小）。
    优先排除 legacy / instruct / edit 系列。"""
    out = {}
    for cat, lst in grouped.items():
        if not lst:
            continue
        # 先过滤 legacy
        primary = sorted(set(m for m in lst if not _is_legacy(m)))
        if not primary:
            primary = sorted(set(lst))
        if len(primary) <= per_cat:
            out[cat] = primary
        else:
            out[cat] = [primary[-1], primary[0]]
    return out
