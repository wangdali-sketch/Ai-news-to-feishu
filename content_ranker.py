import re
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple


OFFICIAL_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "google.com",
    "deepmind.google",
    "microsoft.com",
    "github.blog",
    "aws.amazon.com",
    "nvidia.com",
    "huggingface.co",
    "arxiv.org",
    "deepseek.com",
    "alibabacloud.com",
}

RELEASE_KEYWORDS = {
    "发布",
    "推出",
    "上线",
    "新模型",
    "新功能",
    "更新",
    "release",
    "launch",
    "introducing",
    "announce",
}

FRONTIER_KEYWORDS = {
    "agent",
    "智能体",
    "mcp",
    "多模态",
    "multimodal",
    "ai coding",
    "cursor",
    "claude code",
    "codex",
    "copilot",
    "开源模型",
    "open source",
    "reasoning",
    "推理模型",
}

LEARNING_KEYWORDS = {
    "教程",
    "指南",
    "入门",
    "实践",
    "示例",
    "课程",
    "tutorial",
    "guide",
    "how to",
    "benchmark",
    "论文",
}

IMPACT_KEYWORDS = {
    "突破",
    "首个",
    "重大",
    "行业",
    "企业",
    "安全",
    "政策",
    "开源",
    "million",
    "billion",
    "breakthrough",
}

CLICKBAIT_KEYWORDS = {
    "震惊",
    "颠覆一切",
    "必看",
    "疯了",
    "史上最强",
    "一夜之间",
    "你绝对想不到",
}

AD_KEYWORDS = {
    "限时优惠",
    "立即购买",
    "扫码购买",
    "付费课程",
    "代理加盟",
    "品牌合作",
    "广告",
}


def rank_content(
    items: Iterable[Dict[str, str]],
    limit: int = 20,
    min_limit: int = 15,
    max_limit: int = 25,
    max_per_source: int = 4,
) -> List[Dict[str, str]]:
    """按价值分排序，并限制单一来源占比。"""
    safe_limit = max(min_limit, min(int(limit), max_limit))
    scored: List[Tuple[int, str, Dict[str, str], List[str]]] = []
    for original in items:
        item = dict(original)
        original_reason = item.get("reason", "").strip()
        score, reasons = score_content(item)
        combined_reasons = ([original_reason] if original_reason else []) + reasons
        item["reason"] = "；".join(dict.fromkeys(combined_reasons)) or "具备 AI 信息价值"
        scored.append((score, item.get("published_at", ""), item, reasons))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)

    selected: List[Dict[str, str]] = []
    deferred: List[Dict[str, str]] = []
    counts = defaultdict(int)
    for _, _, item, _ in scored:
        source_key = item.get("source", "未知来源").lower()
        if counts[source_key] >= max_per_source:
            deferred.append(item)
            continue
        selected.append(item)
        counts[source_key] += 1
        if len(selected) >= safe_limit:
            return selected
    for item in deferred:
        selected.append(item)
        if len(selected) >= safe_limit:
            break
    return selected


def score_content(item: Dict[str, str]) -> Tuple[int, List[str]]:
    """返回分数和可展示的入选理由。"""
    title = item.get("title", "")
    summary = item.get("summary", "")
    url = item.get("original_url") or item.get("url", "")
    text = f"{title} {summary}".lower()
    score = 20
    reasons: List[str] = []

    if item.get("platform") == "official_blog" or any(domain in url.lower() for domain in OFFICIAL_DOMAINS):
        score += 22
        reasons.append("来自官方或一手来源")
    if _contains(text, RELEASE_KEYWORDS):
        score += 18
        reasons.append("涉及新模型、新工具或新功能")
    if _contains(text, FRONTIER_KEYWORDS):
        score += 16
        reasons.append("命中 Agent、多模态、AI 编程、MCP 或开源模型方向")
    if _contains(text, LEARNING_KEYWORDS) or item.get("category") in {"paper", "tutorial", "open_source"}:
        score += 12
        reasons.append("具有学习或实践价值")
    if _contains(text, IMPACT_KEYWORDS):
        score += 10
        reasons.append("可能带来行业影响")
    if len(summary) >= 80 and not re.search(r"\b[A-Z]{8,}\b", title):
        score += 6
        reasons.append("信息较完整，普通学习者较容易理解")
    if item.get("platform") in {"github", "paper"}:
        score += 8
    if item.get("is_manual"):
        score += 100
        reasons.append("用户在 manual_links.txt 中明确收藏")
    if _contains(text, CLICKBAIT_KEYWORDS):
        score -= 25
        reasons.append("标题疑似夸张，已降权")
    if _contains(text, AD_KEYWORDS):
        score -= 30
        reasons.append("疑似广告软文，已降权")
    if item.get("reason", "").startswith("正文抓取失败"):
        score -= 8
    if not item.get("url"):
        score -= 20
    return score, reasons


def _contains(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)
