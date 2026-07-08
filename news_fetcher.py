import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

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


DEFAULT_SOURCE_FILE = "news_sources.json"
DEFAULT_LIMIT = 8
DEFAULT_LOOKBACK_DAYS = 2

AI_KEYWORDS = [
    "ai",
    "人工智能",
    "大模型",
    "生成式",
    "机器学习",
    "深度学习",
    "智能体",
    "agent",
    "agents",
    "llm",
    "openai",
    "chatgpt",
    "anthropic",
    "claude",
    "deepmind",
    "gemini",
    "deepseek",
    "nvidia",
    "gpu",
    "芯片",
    "算力",
    "模型",
    "机器人",
    "robot",
]

FRONTIER_KEYWORDS = [
    "model",
    "模型",
    "large language model",
    "llm",
    "agent",
    "智能体",
    "release",
    "launch",
    "推出",
    "发布",
    "open source",
    "开源",
    "benchmark",
    "评测",
    "research",
    "研究",
    "inference",
    "推理",
    "training",
    "训练",
    "token",
    "context",
    "多模态",
    "multimodal",
    "chip",
    "accelerator",
    "gpu",
    "算力",
    "芯片",
    "robot",
    "机器人",
]

NOISE_KEYWORDS = [
    "股票",
    "股价",
    "概念股",
    "受益股",
    "上涨",
    "下跌",
    "收涨",
    "收跌",
    "财报",
    "市值",
    "stocks",
    "shares",
    "stock market",
    "lawsuit",
    "shooting",
]

TRUSTED_DOMAINS = [
    "openai.com",
    "blog.google",
    "huggingface.co",
    "nvidia.com",
    "microsoft.com",
    "aws.amazon.com",
    "arxiv.org",
]


def fetch_ai_news(limit: Optional[int] = None, lookback_days: Optional[int] = None) -> List[NewsItem]:
    """抓取最新 AI 新闻，并返回按发布时间倒序排列的结果。"""
    limit = limit or _get_int_env("AI_NEWS_LIMIT", DEFAULT_LIMIT)
    lookback_days = lookback_days or _get_int_env("AI_NEWS_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS)
    max_per_source = _get_int_env("AI_NEWS_MAX_PER_SOURCE", 3)
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    sources = load_news_sources(lookback_days=lookback_days)

    all_items: List[NewsItem] = []
    errors: List[str] = []

    for source in sources:
        try:
            all_items.extend(_fetch_source(source, cutoff=cutoff))
        except Exception as exc:
            errors.append(f"{source.get('name', '未知新闻源')}：{exc}")

    ai_items = [item for item in all_items if _looks_like_ai_news(item)]
    unique_items = _deduplicate_news(ai_items)
    unique_items.sort(key=lambda item: (_frontier_score(item), _sort_key(item)), reverse=True)

    if not unique_items:
        detail = "；".join(errors) if errors else "没有抓取到新闻。"
        raise NewsFetchError(f"没有抓取到可用的 AI 新闻。{detail}")

    return _diversify_items(unique_items, limit=limit, max_per_source=max_per_source)


def load_news_sources(lookback_days: int) -> List[Dict[str, Any]]:
    """从环境变量或配置文件读取新闻源。"""
    raw_json = os.getenv("AI_NEWS_SOURCES_JSON", "").strip()
    if raw_json:
        config = json.loads(raw_json)
    else:
        source_file = os.getenv("AI_NEWS_SOURCES_FILE", DEFAULT_SOURCE_FILE).strip() or DEFAULT_SOURCE_FILE
        config_path = Path(source_file)
        if not config_path.is_absolute():
            config_path = Path(__file__).resolve().parent / config_path
        config = json.loads(config_path.read_text(encoding="utf-8"))

    raw_sources = config.get("sources", config)
    if not isinstance(raw_sources, list):
        raise NewsFetchError("新闻源配置格式错误：需要 sources 列表。")

    sources = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        if source.get("enabled", True) is False:
            continue
        formatted = _format_source_values(source, lookback_days=lookback_days)
        if formatted.get("type", "rss") != "rss":
            continue
        if not formatted.get("url"):
            continue
        sources.append(formatted)

    if not sources:
        raise NewsFetchError("没有启用任何 AI 新闻源。")

    return sources


def _fetch_source(source: Dict[str, Any], cutoff: datetime) -> List[NewsItem]:
    """读取一个 RSS 或 Atom 新闻源。"""
    response = requests.get(
        str(source["url"]),
        params=source.get("params"),
        headers={"User-Agent": "ai-news-to-feishu/1.0"},
        timeout=25,
    )
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items: List[NewsItem] = []

    for node in _iter_feed_entries(root):
        item = _parse_feed_entry(node, source)
        if not item:
            continue
        if item.published_at and item.published_at < cutoff:
            continue
        items.append(item)

    return items


def _parse_feed_entry(node: ET.Element, source: Dict[str, Any]) -> Optional[NewsItem]:
    """把 RSS item 或 Atom entry 转换成统一新闻对象。"""
    title = _clean_text(_find_child_text(node, ["title"]))
    link = _extract_link(node)
    summary = _extract_summary(node)
    source_name = _extract_source_name(node) or str(source.get("name", "未知来源"))
    published_at = _parse_datetime(_find_child_text(node, ["pubDate", "published", "updated", "dc:date"]))

    if not title or not link:
        return None

    return NewsItem(
        title=title,
        link=link,
        source=source_name,
        published_at=published_at,
        published_text=_format_datetime(published_at),
        summary=summary or "暂无摘要，请打开原文链接查看详情。",
    )


def _iter_feed_entries(root: ET.Element) -> Iterable[ET.Element]:
    """兼容 RSS 的 item 和 Atom 的 entry。"""
    for node in root.iter():
        local_name = _local_name(node.tag)
        if local_name in {"item", "entry"}:
            yield node


def _extract_link(node: ET.Element) -> str:
    """读取原文链接。"""
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", ""}:
            return _clean_text(href)
        if child.text:
            return _clean_text(child.text)
    return ""


def _extract_summary(node: ET.Element) -> str:
    """读取并清洗摘要。"""
    summary = _find_child_text(node, ["description", "summary", "content", "encoded"])
    return _shorten_text(_clean_html(summary), 260)


def _extract_source_name(node: ET.Element) -> str:
    """读取 RSS source 标签里的来源名称。"""
    for child in node:
        if _local_name(child.tag) == "source":
            return _clean_text(child.text or "")
    return ""


def _find_child_text(node: ET.Element, names: List[str]) -> str:
    """按标签名读取直接子节点文本，兼容命名空间。"""
    wanted = {name.split(":")[-1] for name in names}
    for child in node:
        if _local_name(child.tag) in wanted:
            return child.text or ""
    return ""


def _format_source_values(value: Any, lookback_days: int) -> Any:
    """递归替换配置里的 {lookback_days}。"""
    if isinstance(value, str):
        return value.format(lookback_days=lookback_days)
    if isinstance(value, list):
        return [_format_source_values(item, lookback_days) for item in value]
    if isinstance(value, dict):
        return {key: _format_source_values(item, lookback_days) for key, item in value.items()}
    return value


def _looks_like_ai_news(item: NewsItem) -> bool:
    """根据标题、摘要和链接判断是否明显和 AI 有关。"""
    text = f"{item.title} {item.summary} {item.link}".lower()
    has_ai_keyword = any(keyword in text for keyword in AI_KEYWORDS)
    if not has_ai_keyword:
        return False

    has_noise = any(keyword in text for keyword in NOISE_KEYWORDS)
    has_frontier_keyword = any(keyword in text for keyword in FRONTIER_KEYWORDS)
    if has_noise and not has_frontier_keyword:
        return False

    return True


def _frontier_score(item: NewsItem) -> int:
    """给更像 AI 前沿进展的新闻更高排序分。"""
    text = f"{item.title} {item.summary} {item.link}".lower()
    score = 0

    for keyword in AI_KEYWORDS:
        if keyword in text:
            score += 1

    for keyword in FRONTIER_KEYWORDS:
        if keyword in text:
            score += 2

    for domain in TRUSTED_DOMAINS:
        if domain in item.link.lower():
            score += 5

    if any(keyword in text for keyword in NOISE_KEYWORDS):
        score -= 4

    return score


def _deduplicate_news(items: List[NewsItem]) -> List[NewsItem]:
    """按标题和链接去重。"""
    seen_titles = set()
    seen_links = set()
    unique_items: List[NewsItem] = []

    for item in items:
        title_key = _canonical_title(item.title)
        link_key = _canonical_link(item.link)
        if title_key in seen_titles or link_key in seen_links:
            continue
        seen_titles.add(title_key)
        seen_links.add(link_key)
        unique_items.append(item)

    return unique_items


def _diversify_items(items: List[NewsItem], limit: int, max_per_source: int) -> List[NewsItem]:
    """控制单个新闻源的数量，避免日报被一个来源刷屏。"""
    selected: List[NewsItem] = []
    counts: Dict[str, int] = {}
    selected_keys = set()

    for item in items:
        source_key = item.source.lower()
        if counts.get(source_key, 0) >= max_per_source:
            continue
        selected.append(item)
        selected_keys.add(_canonical_link(item.link))
        counts[source_key] = counts.get(source_key, 0) + 1
        if len(selected) >= limit:
            return selected

    for item in items:
        link_key = _canonical_link(item.link)
        if link_key in selected_keys:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break

    return selected


def _canonical_title(title: str) -> str:
    """生成标题去重键。"""
    value = title.lower()
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _canonical_link(link: str) -> str:
    """生成链接去重键。"""
    parsed = urlparse(link)
    return f"{parsed.netloc.lower()}{parsed.path}".rstrip("/")


def _sort_key(item: NewsItem) -> datetime:
    """没有发布时间的新闻排到最后。"""
    return item.published_at or datetime.min.replace(tzinfo=timezone.utc)


def _parse_datetime(value: str) -> Optional[datetime]:
    """把 RSS 或 Atom 时间字符串转换成 datetime。"""
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_datetime(value: Optional[datetime]) -> str:
    """把发布时间格式化成适合日报展示的中文时间。"""
    if value is None:
        return "未知时间"
    local_time = value.astimezone()
    return local_time.strftime("%Y-%m-%d %H:%M")


def _clean_html(value: str) -> str:
    """去掉摘要里的 HTML 标签。"""
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


def _local_name(tag: str) -> str:
    """去掉 XML 命名空间。"""
    return tag.split("}")[-1].split(":")[-1]


def _get_int_env(name: str, default: int) -> int:
    """读取整数环境变量。"""
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return max(value, 1)
