import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Set
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "ref",
}


def deduplicate_content(
    items: Iterable[Dict[str, str]],
    history_file: Path | None = None,
) -> List[Dict[str, str]]:
    """按规范化链接和相似标题去重，并可排除历史已写入内容。"""
    seen_history = load_seen_urls(history_file) if history_file else set()
    seen_links: Set[str] = set()
    seen_titles: List[str] = []
    unique: List[Dict[str, str]] = []

    for item in items:
        link_key = canonical_url(item.get("original_url") or item.get("url", ""))
        title_key = canonical_title(item.get("title", ""))
        # 手动收藏链接是用户明确要求跟踪的内容，即使历史出现过也保留在本期候选中。
        if link_key and (
            (link_key in seen_history and not item.get("is_manual"))
            or link_key in seen_links
        ):
            continue
        if title_key and any(_similar(title_key, old) for old in seen_titles):
            continue
        if link_key:
            seen_links.add(link_key)
        if title_key:
            seen_titles.append(title_key)
        unique.append(item)
    return unique


def load_seen_urls(history_file: Path | None) -> Set[str]:
    """读取历史链接；文件损坏时返回空集合，避免主程序崩溃。"""
    if not history_file or not history_file.exists():
        return set()
    try:
        payload = json.loads(history_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    records = payload.get("items", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return set()
    result = set()
    for record in records:
        url = record.get("url", "") if isinstance(record, dict) else str(record)
        key = canonical_url(url)
        if key:
            result.add(key)
    return result


def save_seen_items(
    items: Iterable[Dict[str, str]],
    history_file: Path,
    max_records: int = 2000,
) -> None:
    """飞书写入成功后记录链接，供下次运行过滤。"""
    previous = []
    if history_file.exists():
        try:
            payload = json.loads(history_file.read_text(encoding="utf-8"))
            previous = payload.get("items", []) if isinstance(payload, dict) else []
        except (OSError, json.JSONDecodeError):
            previous = []

    now = datetime.now(timezone.utc).isoformat()
    combined = list(previous) if isinstance(previous, list) else []
    known = {
        canonical_url(record.get("url", ""))
        for record in combined
        if isinstance(record, dict)
    }
    for item in items:
        url = item.get("original_url") or item.get("url", "")
        key = canonical_url(url)
        if not key or key in known:
            continue
        combined.append({"url": url, "title": item.get("title", ""), "seen_at": now})
        known.add(key)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        json.dumps({"items": combined[-max_records:]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def canonical_url(url: str) -> str:
    """移除锚点、常见跟踪参数和末尾斜杠。"""
    if not url:
        return ""
    parsed = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/") or "/",
        query=urlencode(query),
        fragment="",
    )
    return urlunparse(normalized)


def canonical_title(title: str) -> str:
    value = (title or "").lower()
    value = re.sub(r"\s+[-|｜]\s+[^-|｜]{2,80}$", "", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _similar(first: str, second: str) -> bool:
    if first == second:
        return True
    if min(len(first), len(second)) < 12:
        return False
    return SequenceMatcher(None, first, second).ratio() >= 0.92
