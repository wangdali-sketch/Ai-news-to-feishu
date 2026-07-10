import re
from typing import Any, Dict, Iterable, List

from .rss_collector import collect_rss


def collect_arxiv(
    sources: Iterable[Dict[str, Any]],
    lookback_days: int = 2,
    timeout: int = 25,
) -> List[Dict[str, str]]:
    """通过 arXiv 官方 RSS 采集论文。"""
    items = collect_rss(sources, lookback_days=lookback_days, timeout=timeout)
    for item in items:
        item["platform"] = "paper"
        item["category"] = "paper"
        item["reason"] = "来自 arXiv 官方公开 RSS 的近期论文"
        value = item.get("original_url") or item.get("url", "")
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#/]+)", value)
        if not match:
            match = re.search(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", value)
        if match:
            paper_id = match.group(1).removesuffix(".pdf")
            abs_url = f"https://arxiv.org/abs/{paper_id}"
            item["url"] = abs_url
            item["original_url"] = abs_url
    return items
