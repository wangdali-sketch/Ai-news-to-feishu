import logging
import os
import re
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from content_schema import build_content_item, clean_text, detect_category


LOGGER = logging.getLogger(__name__)
AI_KEYWORDS = {
    "ai",
    "llm",
    "agent",
    "mcp",
    "machine learning",
    "deep learning",
    "transformer",
    "diffusion",
    "multimodal",
    "人工智能",
    "大模型",
    "智能体",
}


def collect_github(
    sources: Iterable[Dict[str, Any]],
    timeout: int = 25,
) -> List[Dict[str, str]]:
    """读取 GitHub 公开 Trending 页面并筛选 AI 相关项目。"""
    items: List[Dict[str, str]] = []
    for source in sources:
        if source.get("enabled", True) is False:
            continue
        url = str(source.get("url", "")).strip()
        if not url:
            continue
        try:
            items.extend(_collect_trending(source, timeout))
        except Exception as exc:
            LOGGER.warning("GitHub 来源抓取失败：%s；原因：%s", source.get("name", url), exc)
    return items


def _collect_trending(source: Dict[str, Any], timeout: int) -> List[Dict[str, str]]:
    headers = {"User-Agent": "ai-frontier-radar/2.0", "Accept": "text/html"}
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    response = requests.get(
        str(source["url"]),
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    result: List[Dict[str, str]] = []
    for article in soup.select("article.Box-row"):
        link_node = article.select_one("h2 a")
        if not link_node:
            continue
        path = re.sub(r"\s+", "", link_node.get_text(" ", strip=True))
        description_node = article.select_one("p")
        description = clean_text(description_node.get_text(" ", strip=True)) if description_node else ""
        text = f"{path} {description}".lower()
        if not any(keyword in text for keyword in AI_KEYWORDS):
            continue
        language_node = article.select_one("[itemprop='programmingLanguage']")
        language = clean_text(language_node.get_text()) if language_node else "未知语言"
        daily_node = article.select_one("span.d-inline-block.float-sm-right")
        trend = clean_text(daily_node.get_text(" ", strip=True)) if daily_node else "GitHub 今日热门"
        url = urljoin("https://github.com", link_node.get("href", ""))
        summary = f"{description or '暂无项目说明'}；{language}；{trend}"
        result.append(
            build_content_item(
                title=path,
                source=str(source.get("name", "GitHub Trending")),
                platform="github",
                category=detect_category(text, "github"),
                url=url,
                original_url=url,
                summary=summary,
                raw_text=description,
                reason="AI 关键词匹配的 GitHub 公开热门项目",
            )
        )
    LOGGER.info("GitHub 来源采集完成：%s，共 %s 条", source.get("name"), len(result))
    return result
