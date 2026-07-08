import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Dict, List, Optional

import requests


class NewsFetchError(RuntimeError):
    """抓取新闻失败时抛出的错误。"""


@dataclass
class NewsItem:
    """一条新闻。"""

    title: str
    link: str
    source: str
    published_at: Optional[datetime]
    published_text: str
    summary: str


NEWS_SOURCES = [
    {
        "name": "Google News 中文 AI",
        "url": "https://news.google.com/rss/search",
        "params": {
            "q": "人工智能 OR AI when:2d",
            "hl": "zh-CN",
            "gl": "CN",
            "ceid": "CN:zh-Hans",
        },
    },
    {
        "name": "Google News 国际 AI",
        "url": "https://news.google.com/rss/search",
        "params": {
            "q": "artificial intelligence AI OpenAI Google Microsoft NVIDIA when:2d",
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        },
    },
]


def fetch_ai_news(limit: int = 8) -> List[NewsItem]:
    """抓取 AI 新闻，并返回按发布时间倒序排列的结果。"""
    all_items: List[NewsItem] = []
    errors: List[str] = []

    for source in NEWS_SOURCES:
        try:
            all_items.extend(_fetch_rss_source(source))
        except Exception as exc:
            errors.append(f"{source['name']}：{exc}")

    unique_items = _deduplicate_news(all_items)
    unique_items.sort(key=_sort_key, reverse=True)

    if not unique_items:
        detail = "；".join(errors) if errors else "没有抓取到新闻。"
        raise NewsFetchError(f"没有抓取到可用的 AI 新闻。{detail}")

    return unique_items[:limit]


def _fetch_rss_source(source: Dict[str, object]) -> List[NewsItem]:
    """读取一个 RSS 新闻源。"""
    response = requests.get(
        str(source["url"]),
        params=source["params"],
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items: List[NewsItem] = []

    for item in root.findall(".//item"):
        title = _clean_text(_find_child_text(item, "title"))
        link = _clean_text(_find_child_text(item, "link"))
        summary = _shorten_text(_clean_html(_find_child_text(item, "description")), 220)
        source_name = _clean_text(_find_child_text(item, "source")) or str(source["name"])
        published_at = _parse_datetime(_find_child_text(item, "pubDate"))

        if not title or not link:
            continue

        items.append(
            NewsItem(
                title=title,
                link=link,
                source=source_name,
                published_at=published_at,
                published_text=_format_datetime(published_at),
                summary=summary,
            )
        )

    return items


def _deduplicate_news(items: List[NewsItem]) -> List[NewsItem]:
    """按标题去重。"""
    seen = set()
    unique_items: List[NewsItem] = []

    for item in items:
        key = re.sub(r"\s+", " ", item.title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)

    return unique_items


def _sort_key(item: NewsItem) -> datetime:
    """没有发布时间的新闻排到最后。"""
    return item.published_at or datetime.min.replace(tzinfo=timezone.utc)


def _find_child_text(item: ET.Element, child_name: str) -> str:
    """根据标签名读取子节点文本，兼容带命名空间的 XML。"""
    for child in item:
        local_name = child.tag.split("}")[-1]
        if local_name == child_name:
            return child.text or ""
    return ""


def _parse_datetime(value: str) -> Optional[datetime]:
    """把 RSS 时间字符串转换成 datetime。"""
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _format_datetime(value: Optional[datetime]) -> str:
    """把发布时间格式化成适合日报展示的文本。"""
    if value is None:
        return "未知时间"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _clean_html(value: str) -> str:
    """去掉 RSS 摘要里的 HTML 标签。"""
    text = re.sub(r"<[^>]+>", " ", value or "")
    return _clean_text(text)


def _clean_text(value: str) -> str:
    """清理多余空白字符。"""
    text = unescape(value or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _shorten_text(value: str, max_length: int) -> str:
    """限制摘要长度，避免写入飞书时单段太长。"""
    if len(value) <= max_length:
        return value
    return value[: max_length - 1].rstrip() + "…"
