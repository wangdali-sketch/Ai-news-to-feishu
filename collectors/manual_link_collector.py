import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

from content_schema import build_content_item, detect_category, detect_platform

from .web_collector import fetch_public_page


LOGGER = logging.getLogger(__name__)
FAILURE_NOTE = "原文抓取失败，仅基于标题和摘要整理"


def collect_manual_links(
    sources: Iterable[Dict[str, Any]],
    project_dir: Path,
    timeout: int = 20,
) -> List[Dict[str, str]]:
    """读取用户手动保存的公开链接；抓取失败时仍保留链接。"""
    items: List[Dict[str, str]] = []
    for source in sources:
        if source.get("enabled", True) is False:
            continue
        file_value = str(source.get("file", "data/manual_links.txt")).strip()
        path = Path(file_value)
        if not path.is_absolute():
            path = project_dir / path
        if not path.exists():
            LOGGER.warning("手动链接文件不存在：%s", path)
            continue
        for url in _read_urls(path):
            platform = detect_platform(url)
            try:
                item = fetch_public_page(
                    url,
                    source=str(source.get("name", "")) or urlparse(url).netloc,
                    platform=platform,
                    category=(
                        ""
                        if str(source.get("category", "")) == "manual"
                        else str(source.get("category", ""))
                    ),
                    timeout=timeout,
                )
                if platform in {"wechat", "douyin", "bilibili", "xiaohongshu", "x"}:
                    item["reason"] = "用户手动提供的公开链接；" + item["reason"]
                # 手动录入的链接必须原样保留，不能被重定向地址替换。
                item["url"] = url
                item["original_url"] = url
                item["is_manual"] = True
                items.append(item)
            except Exception as exc:
                LOGGER.warning("手动链接正文抓取失败：%s；原因：%s", url, exc)
                domain = urlparse(url).netloc
                items.append(
                    build_content_item(
                        title=f"{domain} 上的手动收藏内容",
                        source=str(source.get("name", "")) or domain,
                        platform=platform,
                        category=detect_category(url, platform),
                        url=url,
                        original_url=url,
                        summary=FAILURE_NOTE,
                        raw_text="",
                        reason=FAILURE_NOTE,
                        fetch_success=False,
                        body_fetch_attempted=True,
                        body_fetch_success=False,
                        is_manual=True,
                    )
                )
    LOGGER.info("手动链接采集完成，共 %s 条", len(items))
    return items


def _read_urls(path: Path) -> List[str]:
    result = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith(("http://", "https://")):
            result.append(value)
        else:
            LOGGER.warning("已忽略不是 HTTP/HTTPS 的手动链接：%s", value)
    return result
