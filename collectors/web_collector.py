import logging
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from content_schema import build_content_item, clean_text, detect_category, detect_platform


LOGGER = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; AIFrontierRadar/2.0; public-page-reader)"


def fetch_public_page(
    url: str,
    *,
    source: str = "",
    platform: str = "",
    category: str = "",
    timeout: int = 20,
) -> Dict[str, str]:
    """读取无需登录的公开网页，不绕过登录、验证码或付费墙。"""
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"},
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "html" not in content_type and "text" not in content_type:
        raise ValueError(f"页面不是可读取的文本内容：{content_type or '未知类型'}")

    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()

    title = _meta(soup, "property", "og:title") or _meta(soup, "name", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    description = (
        _meta(soup, "property", "og:description")
        or _meta(soup, "name", "description")
        or _meta(soup, "name", "twitter:description")
    )
    published = (
        _meta(soup, "property", "article:published_time")
        or _meta(soup, "name", "date")
        or _time_value(soup)
    )
    container = soup.find("article") or soup.find("main") or soup.body
    paragraphs = []
    if container:
        paragraphs = [
            clean_text(node.get_text(" ", strip=True))
            for node in container.find_all(["p", "h1", "h2", "li"])
        ]
    raw_text = clean_text(" ".join(value for value in paragraphs if len(value) >= 20))[:6000]
    summary = clean_text(description) or raw_text[:500]
    final_url = response.url
    final_platform = platform or detect_platform(final_url)
    final_category = category or detect_category(f"{title} {summary}", final_platform)
    return build_content_item(
        title=title or urlparse(final_url).netloc or "未获取到标题",
        source=source or urlparse(final_url).netloc,
        platform=final_platform,
        category=final_category,
        url=final_url,
        original_url=final_url,
        published_at=published,
        summary=summary,
        raw_text=raw_text,
        reason="已从无需登录的公开网页提取可见信息",
        body_fetch_attempted=True,
        body_fetch_success=bool(raw_text),
    )


def collect_web_sources(
    sources: Iterable[Dict[str, Any]],
    timeout: int = 20,
) -> List[Dict[str, str]]:
    """采集 sources.yml 中用户明确配置的公开网页。"""
    items: List[Dict[str, str]] = []
    for source in sources:
        if source.get("enabled", True) is False:
            continue
        url = str(source.get("url", "")).strip()
        if not url:
            continue
        try:
            items.append(
                fetch_public_page(
                    url,
                    source=str(source.get("name", "")),
                    platform=str(source.get("platform", "")),
                    category=str(source.get("category", "")),
                    timeout=timeout,
                )
            )
        except Exception as exc:
            LOGGER.warning("公开网页抓取失败：%s；原因：%s", url, exc)
            items.append(
                build_content_item(
                    title=urlparse(url).netloc or "未获取到标题",
                    source=str(source.get("name", "")) or urlparse(url).netloc,
                    platform=str(source.get("platform", "")) or detect_platform(url),
                    category=str(source.get("category", "")),
                    url=url,
                    original_url=url,
                    summary="原文抓取失败，仅基于标题和摘要整理",
                    reason="原文抓取失败，仅基于标题和摘要整理",
                    fetch_success=False,
                    body_fetch_attempted=True,
                    body_fetch_success=False,
                )
            )
    return items


def _meta(soup: BeautifulSoup, key: str, value: str) -> str:
    node = soup.find("meta", attrs={key: value})
    return clean_text(node.get("content", "")) if node else ""


def _time_value(soup: BeautifulSoup) -> str:
    node = soup.find("time")
    if not node:
        return ""
    return clean_text(node.get("datetime", "") or node.get_text(" ", strip=True))
