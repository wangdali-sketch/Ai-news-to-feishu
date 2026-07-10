import logging
import os
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin

from .rss_collector import collect_rss


LOGGER = logging.getLogger(__name__)


def collect_social(
    sources: Iterable[Dict[str, Any]],
    lookback_days: int = 2,
    timeout: int = 25,
) -> List[Dict[str, str]]:
    """仅通过用户配置的 RSSHub/官方 RSS 接入社媒，不直接绕过平台限制。"""
    rss_sources = []
    for source in sources:
        if source.get("enabled", False) is not True:
            LOGGER.info(
                "社媒来源未启用：%s（%s）",
                source.get("name", "未知来源"),
                source.get("note", "未配置公开接口"),
            )
            continue
        rss_url = str(source.get("rss_url", "") or source.get("url", "")).strip()
        if not rss_url:
            LOGGER.warning("社媒来源已启用但没有 rss_url/url：%s", source.get("name"))
            continue
        if rss_url.startswith("/"):
            rsshub_base_url = os.getenv("RSSHUB_BASE_URL", "").strip().rstrip("/")
            if not rsshub_base_url:
                LOGGER.warning(
                    "社媒来源使用相对 RSSHub 路径，但未配置 RSSHUB_BASE_URL：%s",
                    source.get("name"),
                )
                continue
            rss_url = urljoin(f"{rsshub_base_url}/", rss_url.lstrip("/"))
        configured = dict(source)
        configured["url"] = rss_url
        configured["platform"] = str(source.get("type", "manual"))
        rss_sources.append(configured)
    return collect_rss(rss_sources, lookback_days=lookback_days, timeout=timeout)
