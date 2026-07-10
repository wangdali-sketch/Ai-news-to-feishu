import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List

import requests

from content_schema import build_content_item, clean_html, clean_text, detect_category


LOGGER = logging.getLogger(__name__)
USER_AGENT = "ai-frontier-radar/2.0 (+public RSS reader)"
SHORT_SUMMARY_CHARS = 320
MAX_PAGE_FETCHES_PER_SOURCE = 5


def collect_rss(
    sources: Iterable[Dict[str, Any]],
    lookback_days: int = 2,
    timeout: int = 25,
) -> List[Dict[str, str]]:
    """采集多个公开 RSS/Atom 来源；单个来源失败不会中断全部任务。"""
    items: List[Dict[str, str]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(lookback_days, 1))
    for source in sources:
        if source.get("enabled", True) is False:
            continue
        try:
            items.extend(_collect_one(source, cutoff, timeout))
        except Exception as exc:
            LOGGER.warning("RSS 来源抓取失败：%s；原因：%s", source.get("name", "未知来源"), exc)
    return items


def _collect_one(
    source: Dict[str, Any],
    cutoff: datetime,
    timeout: int,
) -> List[Dict[str, str]]:
    url = str(source.get("url", "")).strip()
    if not url:
        return []
    response = requests.get(
        url,
        params=source.get("params"),
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    result: List[Dict[str, str]] = []
    page_fetches = 0
    for node in _iter_entries(root):
        title = clean_text(_find_text(node, {"title"}))
        link = _extract_link(node)
        if not title or not link:
            continue
        published = _find_text(node, {"pubDate", "published", "updated", "date"})
        parsed = _parse_feed_datetime(published)
        if parsed and parsed < cutoff:
            continue
        feed_text = clean_html(
            _find_text(node, {"description", "summary", "content", "encoded"})
        )
        summary = feed_text[:1200]
        original_url = _extract_original_url(node, link)
        source_name = clean_text(_find_text(node, {"source"})) or str(
            source.get("name", "未知 RSS 来源")
        )
        platform = _source_platform(source, link)
        configured_category = str(source.get("category", "")).strip()
        category = (
            configured_category
            if configured_category not in {"official_blog", "news", ""}
            else detect_category(f"{title} {summary}", platform)
        )
        item = build_content_item(
            title=title,
            source=source_name,
            platform=platform,
            category=category,
            url=link,
            original_url=original_url,
            published_at=parsed or published,
            summary=summary,
            raw_text=feed_text[:6000],
            reason="来自已配置的公开 RSS/Atom 来源",
            body_fetch_attempted=False,
            body_fetch_success=False,
        )
        should_fetch_page = (
            len(summary) < SHORT_SUMMARY_CHARS or "news.google.com" in link.lower()
        )
        if should_fetch_page and page_fetches < MAX_PAGE_FETCHES_PER_SOURCE:
            page_fetches += 1
            item = _enrich_short_item(item, timeout)
        result.append(item)
    LOGGER.info("RSS 来源采集完成：%s，共 %s 条", source.get("name", url), len(result))
    return result


def _source_platform(source: Dict[str, Any], link: str) -> str:
    configured = str(source.get("platform", "")).strip()
    if configured:
        return configured
    category = str(source.get("category", "")).strip()
    name_and_url = f"{source.get('name', '')} {source.get('url', '')} {link}".lower()
    if category == "official_blog":
        return "official_blog"
    if category == "paper" or "arxiv.org" in name_and_url:
        return "paper"
    if "reddit" in name_and_url:
        return "reddit"
    if "hacker news" in name_and_url or "hnrss.org" in name_and_url:
        return "hackernews"
    return "news"


def _iter_entries(root: ET.Element) -> Iterable[ET.Element]:
    for node in root.iter():
        if _local_name(node.tag) in {"item", "entry"}:
            yield node


def _extract_link(node: ET.Element) -> str:
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "")
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", ""}:
            return clean_text(href)
        if child.text:
            return clean_text(child.text)
    guid = _find_text(node, {"guid", "id"})
    return clean_text(guid) if guid.startswith("http") else ""


def _extract_original_url(node: ET.Element, link: str) -> str:
    """提取源站链接；无法确认时完整保留 RSS 条目链接。"""
    candidates: List[str] = []
    for child in node:
        name = _local_name(child.tag).lower()
        if name in {"source", "origlink", "originalurl", "canonical"}:
            candidates.extend(
                [
                    child.attrib.get("url", ""),
                    child.attrib.get("href", ""),
                    child.text or "",
                ]
            )
    for candidate in candidates:
        value = clean_text(candidate)
        if value.startswith(("http://", "https://")):
            return value
    # 某些 RSS 摘要会直接包含源站链接，但不能从普通正文猜测链接。
    if "news.google.com" not in link.lower():
        return link
    return link


def _enrich_short_item(item: Dict[str, str], timeout: int) -> Dict[str, str]:
    """RSS 摘要过短时尝试读取正文；失败只记录状态，不丢弃条目。"""
    try:
        from .web_collector import fetch_public_page

        page = fetch_public_page(
            item["original_url"] or item["url"],
            source=item["source"],
            platform=item["platform"],
            category=item["category"],
            timeout=timeout,
        )
        if len(page.get("raw_text", "")) > len(item.get("raw_text", "")):
            item["raw_text"] = page["raw_text"]
            if page.get("summary"):
                item["summary"] = page["summary"]
            resolved = page.get("original_url") or page.get("url")
            if resolved and "news.google.com" in item["url"].lower():
                item["original_url"] = resolved
        item["body_fetch_attempted"] = True
        item["body_fetch_success"] = bool(page.get("raw_text", ""))
        item["fetch_success"] = True
    except Exception as exc:
        item["fetch_success"] = False
        item["body_fetch_attempted"] = True
        item["body_fetch_success"] = False
        item["reason"] = (
            f"{item.get('reason', '')}；原文抓取失败，仅基于标题和摘要整理"
        ).strip("；")
        LOGGER.info("RSS 原文补充抓取失败，已保留 RSS 链接：%s；%s", item["url"], exc)
    return item


def _find_text(node: ET.Element, names: set[str]) -> str:
    for child in node:
        if _local_name(child.tag) in names:
            return "".join(child.itertext())
    return ""


def _local_name(tag: str) -> str:
    return tag.split("}")[-1].split(":")[-1]


def _parse_feed_datetime(value: str):
    from content_schema import parse_datetime

    return parse_datetime(value)
