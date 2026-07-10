import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, Optional


PLATFORMS = {
    "news",
    "official_blog",
    "paper",
    "github",
    "wechat",
    "douyin",
    "bilibili",
    "xiaohongshu",
    "x",
    "reddit",
    "hackernews",
    "tool",
    "manual",
}

CATEGORIES = {
    "model_release",
    "ai_agent",
    "multimodal",
    "ai_coding",
    "open_source",
    "paper",
    "tool_update",
    "industry_news",
    "tutorial",
    "opinion",
    "business",
    "video",
    "social_discussion",
}


def build_content_item(
    *,
    title: str,
    source: str,
    platform: str,
    category: str,
    url: str,
    original_url: str = "",
    published_at: Any = "",
    summary: str = "",
    raw_text: str = "",
    reason: str = "",
    fetch_success: bool = True,
    body_fetch_attempted: bool = False,
    body_fetch_success: bool = False,
    is_manual: bool = False,
) -> Dict[str, str]:
    """创建字段一致的内容字典。"""
    clean_title = clean_text(title) or "未获取到标题"
    clean_summary = clean_text(summary)
    clean_raw_text = clean_text(raw_text)
    clean_url = clean_url_value(url)
    clean_original_url = clean_url_value(original_url) or clean_url
    normalized_platform = (
        platform if platform in PLATFORMS else detect_platform(clean_original_url or clean_url, platform)
    )
    normalized_category = (
        category
        if category in CATEGORIES
        else detect_category(f"{clean_title} {clean_summary} {clean_raw_text}", normalized_platform)
    )
    return {
        "title": clean_title,
        "source": clean_text(source) or "未知来源",
        "platform": normalized_platform,
        "category": normalized_category,
        # 链接字段不能经过正文截断逻辑，也不能用省略号缩短。
        "url": clean_url,
        "original_url": clean_original_url,
        "published_at": format_datetime(published_at),
        "summary": clean_summary or "暂无摘要，请打开原文查看。",
        "raw_text": clean_raw_text,
        "reason": clean_text(reason),
        "fetch_success": fetch_success,
        "body_fetch_attempted": body_fetch_attempted,
        "body_fetch_success": body_fetch_success,
        "is_manual": is_manual,
    }


def preferred_url(item: Dict[str, Any]) -> str:
    """返回日报应展示的链接；没有链接时使用唯一允许的占位文字。"""
    return (
        clean_url_value(item.get("original_url", ""))
        or clean_url_value(item.get("url", ""))
        or "未获取到"
    )


def clean_url_value(value: Any) -> str:
    """只清理链接两端空白，不截断、不改写链接内容。"""
    text = str(value or "").strip()
    if text.startswith(("http://", "https://")):
        return text
    return ""


def detect_platform(url: str, fallback: str = "manual") -> str:
    """根据公开链接识别平台。"""
    value = (url or "").lower()
    domain_rules = [
        ("mp.weixin.qq.com", "wechat"),
        ("douyin.com", "douyin"),
        ("bilibili.com", "bilibili"),
        ("b23.tv", "bilibili"),
        ("xiaohongshu.com", "xiaohongshu"),
        ("xhslink.com", "xiaohongshu"),
        ("x.com", "x"),
        ("twitter.com", "x"),
        ("reddit.com", "reddit"),
        ("news.ycombinator.com", "hackernews"),
        ("github.com", "github"),
        ("arxiv.org", "paper"),
    ]
    for domain, platform in domain_rules:
        if domain in value:
            return platform
    return fallback if fallback in PLATFORMS else "manual"


def detect_category(text: str, platform: str = "news") -> str:
    """使用简单关键词给内容分类，供没有明确分类的来源使用。"""
    value = (text or "").lower()
    rules = [
        ("paper", ["arxiv", "论文", "paper", "research", "benchmark"]),
        ("ai_agent", ["agent", "智能体", "mcp", "自动化工作流", "workflow"]),
        ("multimodal", ["多模态", "multimodal", "视频生成", "文生图", "语音模型"]),
        (
            "ai_coding",
            ["ai coding", "代码生成", "编程助手", "cursor", "claude code", "codex", "copilot"],
        ),
        ("model_release", ["新模型", "模型发布", "release", "launch", "推出", "开源模型"]),
        ("tool_update", ["新工具", "工具更新", "新功能", "feature", "版本更新"]),
        ("tutorial", ["教程", "入门", "指南", "how to", "tutorial"]),
        ("business", ["融资", "收购", "营收", "商业", "投资"]),
        ("video", ["视频", "video"]),
        ("opinion", ["观点", "评论", "opinion"]),
    ]
    if platform == "github":
        return "open_source"
    if platform == "paper":
        return "paper"
    if platform in {"wechat", "douyin", "bilibili", "xiaohongshu", "x", "reddit", "hackernews"}:
        default = "social_discussion"
    else:
        default = "industry_news"
    for category, keywords in rules:
        if any(keyword in value for keyword in keywords):
            return category
    return default


def parse_datetime(value: Any) -> Optional[datetime]:
    """兼容 RSS 时间、ISO 时间和 datetime 对象。"""
    if isinstance(value, datetime):
        parsed = value
    elif not value:
        return None
    else:
        text = str(value).strip()
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_datetime(value: Any) -> str:
    """把时间统一成可排序、可展示的格式。"""
    parsed = parse_datetime(value)
    if parsed is None:
        return ""
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def clean_html(value: str) -> str:
    """移除脚本、样式和 HTML 标签。"""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value or "", flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def clean_text(value: Any) -> str:
    """清理实体和多余空白。"""
    text = unescape(str(value or ""))
    return re.sub(r"\s+", " ", text).strip()
