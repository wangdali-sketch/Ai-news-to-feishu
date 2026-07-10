import logging
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from content_schema import preferred_url
from feishu_client import (
    build_bold_text_block,
    build_heading1_block,
    build_text_block,
)


LOGGER = logging.getLogger(__name__)
CATEGORY_SECTIONS = [
    ("1. 模型与大厂动态", {"model_release", "industry_news", "business"}),
    ("2. Agent 与自动化", {"ai_agent"}),
    ("3. AI 编程与开发者工具", {"ai_coding", "tool_update", "tutorial"}),
    ("4. 多模态与视频生成", {"multimodal", "video"}),
    ("5. 开源项目与 GitHub", {"open_source"}),
    ("6. 论文与研究", {"paper"}),
    ("7. 公众号 / 社媒 / 视频平台观察", {"social_discussion", "opinion"}),
]
SOCIAL_PLATFORMS = {
    "wechat",
    "douyin",
    "bilibili",
    "xiaohongshu",
    "x",
    "reddit",
    "hackernews",
}
PROTECTED_SECTIONS = {
    "今日 AI 总览",
    "今日一句话",
    "今日总览",
    "今日最重要的 5 条 AI 新闻",
    "今日最值得关注的 5 条",
    "普通重要动态",
    "论文精选",
    "深度解读",
    "今日学习建议",
}
LAST_LENGTH_STATS = {"compressed": False, "reason": ""}
URL_PATTERN = re.compile(r"https?://[^\s<>\]\u3002\uff0c\uff1b\uff1a\u3001]+")
DAILY_TITLE_PATTERN = re.compile(r"^AI 前沿信息雷达｜\d{4}-\d{2}-\d{2}$")


def generate_rule_based_report(items: Iterable[Dict[str, Any]], report_date: str) -> str:
    """没有大模型时生成字段完整、链接可追溯的规则版日报。"""
    content = list(items)
    top_five = content[:5]
    deep_items = content[: min(8, len(content))]
    lines = [f"# AI 前沿信息雷达｜{report_date}", "", "## 今日一句话"]
    if top_five:
        lines.append(
            f"今天的 AI 动态以“{top_five[0].get('title', '未获取到标题')}”为首要线索，"
            f"重点集中在{'、'.join(_unique_categories(content)[:3])}。"
        )
    else:
        lines.append("今日没有采集到可用内容，请检查来源配置和采集日志。")

    lines.extend(["", "## 今日总览"])
    if content:
        sources = list(dict.fromkeys(item.get("source", "未知来源") for item in content))[:5]
        categories = _unique_categories(content)[:5]
        lines.extend(
            [
                (
                    f"本期从 {len(set(item.get('source', '') for item in content))} 个来源筛选出 "
                    f"{len(content)} 条内容，主要来源包括{'、'.join(sources)}。"
                ),
                (
                    f"今天的信息主要集中在{'、'.join(categories)}。排名靠前的内容是"
                    f"“{'”“'.join(item.get('title', '') for item in top_five[:3])}”。"
                ),
                (
                    "对普通学习者而言，最有效的做法不是追逐所有标题，而是选择一个与自身工作相关的"
                    "工具、模型或研究方向，先核对一手来源，再完成一次小规模实践。"
                ),
            ]
        )
    else:
        lines.append("没有足够内容生成总览。")

    lines.extend(["", "## 今日最值得关注的 5 条"])
    if not top_five:
        lines.append("今日暂无可推荐内容。")
    for index, item in enumerate(top_five, 1):
        lines.extend(
            [
                "",
                f"### {index}. {item.get('title', '未获取到标题')}",
                f"- 来源：{item.get('source') or '未知来源'}",
                f"- 平台：{item.get('platform') or '未知平台'}",
                f"- 一句话总结：{_plain_summary(item)[:320]}",
                f"- 为什么值得关注：{item.get('reason') or _plain_summary(item)[:300]}",
                f"- 适合谁看：关注 {_category_name(item.get('category', ''))} 的学习者和从业者",
                "- 原文链接：",
                preferred_url(item),
            ]
        )

    lines.extend(["", "## 深度解读"])
    if not deep_items:
        lines.append("今日暂无可深度解读的内容。")
    for index, item in enumerate(deep_items, 1):
        lines.extend(_detail_lines(item, index))

    lines.extend(["", "## 分类情报"])
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in content:
        grouped[item.get("category", "")].append(item)
    for title, categories in CATEGORY_SECTIONS:
        lines.extend(["", f"### {title}"])
        matched = [item for category in categories for item in grouped[category]][:5]
        if title.startswith("7.") and not any(
            item.get("platform") in SOCIAL_PLATFORMS for item in content
        ):
            lines.append("今日未配置相关来源。")
        elif not matched:
            lines.append("今日未发现相关内容。")
        else:
            names = "、".join(f"“{item.get('title', '')}”" for item in matched[:3])
            directions = "、".join(
                dict.fromkeys(_category_name(item.get("category", "")) for item in matched)
            )
            lines.append(
                f"今天这一方向涉及{names}，共同反映出{directions}正在从概念讨论转向"
                "更具体的能力、工具和应用验证。判断价值时应优先核对原始发布和实际限制。"
            )

    lines.extend(["", "## 今日学习建议"])
    learning = _learning_topics(content)
    for index, (topic, reason) in enumerate(learning, 1):
        lines.extend(
            [
                f"### {index}. {topic}",
                f"- 是什么：{reason}",
                "- 为什么现在值得学：本期已有相关前沿内容，理解它有助于判断真实价值。",
                "- 入门可以怎么做：先阅读本期对应原文，再找一个最小示例亲手实践。",
            ]
        )

    articles = [item for item in content if item.get("platform") not in {"github", "tool"}][:3]
    tools = [item for item in content if item.get("platform") in {"github", "tool"}][:3]
    keywords = [topic for topic, _ in learning][:3]
    lines.extend(["", "## 今日收藏建议", "### 3 个值得收藏的文章 / 网页"])
    lines.extend(_link_lines(articles) or ["- 今日没有足够的网页或文章。"])
    lines.extend(["### 3 个值得关注的工具 / 项目"])
    lines.extend(_link_lines(tools) or ["- 今日没有足够的工具或项目。"])
    lines.extend(["### 3 个关键词", *(f"- {word}" for word in keywords)])
    lines.extend(["", "## 明日关注方向"])
    for index, word in enumerate((keywords + ["AI 模型更新", "开源项目"])[:3], 1):
        lines.append(f"{index}. 继续跟踪“{word}”的新发布、实测反馈和一手来源。")
    report = "\n".join(lines).strip()
    repaired, _ = ensure_report_links(report, content)
    return repaired


def plan_report_items(items: Iterable[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """为重点、普通动态和论文精选分配互不重复的优先条目。"""
    candidates = list(items)
    featured = candidates[:5]
    featured_ids = {id(item) for item in featured}
    remaining = [item for item in candidates if id(item) not in featured_ids]

    papers = [item for item in remaining if item.get("category") == "paper"][:5]
    # 候选中论文不足时，允许把重点论文列入论文精选，但仍优先保持普通新闻不重复。
    if len(papers) < 3:
        for item in featured:
            if item.get("category") == "paper" and item not in papers:
                papers.append(item)
                if len(papers) >= 3:
                    break
    paper_ids = {id(item) for item in papers}

    ordinary = [
        item
        for item in remaining
        if id(item) not in paper_ids and item.get("category") != "paper"
    ][:12]
    # 目标是至少 8 条普通动态；来源不足时才用未入选的论文补足，并保留其论文身份。
    if len(ordinary) < 8:
        for item in remaining:
            if id(item) not in paper_ids and item not in ordinary:
                ordinary.append(item)
                if len(ordinary) >= 8:
                    break

    return {"featured": featured, "ordinary": ordinary, "papers": papers}


def ensure_report_links(
    markdown: str,
    items: Iterable[Dict[str, Any]],
    *,
    summaries: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, int]:
    """校验重点栏目，删除模型生成的可疑链接并补回程序保存的完整链接。"""
    records = _link_records(list(items), summaries or [])
    repaired_count = 0
    section_pattern = re.compile(r"(?m)^## (.+)$")
    matches = list(section_pattern.finditer(markdown))
    if not matches:
        return markdown, 0

    preamble = markdown[: matches[0].start()]
    rebuilt = [preamble.rstrip()]
    for section_index, match in enumerate(matches):
        end = matches[section_index + 1].start() if section_index + 1 < len(matches) else len(markdown)
        title = match.group(1).strip()
        body = markdown[match.end() : end].strip()
        if title in {
            "今日最重要的 5 条 AI 新闻",
            "普通重要动态",
            "论文精选",
            "今日最值得关注的 5 条",
            "深度解读",
        }:
            body, count = _repair_section_links(body, records)
            repaired_count += count
        rebuilt.append(f"## {title}\n\n{body}".rstrip())
    result = "\n\n".join(part for part in rebuilt if part).strip()
    allowed_urls = {record["url"] for record in records if record["url"] != "未获取到"}

    def remove_unknown_url(match: re.Match) -> str:
        nonlocal repaired_count
        value = match.group(0)
        if value in allowed_urls:
            return value
        repaired_count += 1
        return "未获取到"

    # 不接受模型自行生成的链接，只允许程序采集到的完整地址。
    result = URL_PATTERN.sub(remove_unknown_url, result)
    return result, repaired_count


def validate_report(
    markdown: str,
    items: Iterable[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """执行生成后校验，并返回可写入飞书的日报和统计信息。"""
    content = list(items)
    truncated_patterns = re.findall(
        r"(?m)^-?\s*原文链接[：:]\s*(?:\n\s*)?(ht|https|无|见上)\s*$",
        markdown,
    )
    repaired, repaired_count = ensure_report_links(markdown, content)
    known_urls = {
        preferred_url(item)
        for item in content
        if preferred_url(item) != "未获取到"
    }
    missing_count = sum(preferred_url(item) == "未获取到" for item in content)
    return repaired, {
        "report_items": len(content),
        "items_with_url": len(content) - missing_count,
        "items_missing_url": missing_count,
        "repaired_links": repaired_count,
        "truncated_link_found": bool(truncated_patterns),
        "known_urls_in_report": sum(url in repaired for url in known_urls),
    }


def constrain_report_length(markdown: str, max_chars: int = 12000) -> str:
    """只压缩非核心说明文字；核心栏目和链接不参与硬截断。"""
    LAST_LENGTH_STATS.update({"compressed": False, "reason": ""})
    text = markdown.strip()
    if len(text) <= max_chars:
        return text

    matches = list(re.finditer(r"(?m)^## (.+)$", text))
    if not matches:
        LAST_LENGTH_STATS["reason"] = "报告没有可识别栏目，为避免截断链接而保留原文"
        return text

    preamble = text[: matches[0].start()].strip()
    sections = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((match.group(1).strip(), text[match.end() : end].strip()))

    protected_size = len(preamble) + sum(
        len(title) + len(body) + 8
        for title, body in sections
        if title in PROTECTED_SECTIONS
    )
    compressible = [(title, body) for title, body in sections if title not in PROTECTED_SECTIONS]
    available = max(max_chars - protected_size, 0)
    total = sum(len(body) for _, body in compressible) or 1
    output = [preamble]
    for title, body in sections:
        if title in PROTECTED_SECTIONS:
            new_body = body
        else:
            budget = max(int(available * len(body) / total), 80)
            new_body = _compact_explanation(body, budget)
            if new_body != body:
                LAST_LENGTH_STATS["compressed"] = True
        output.append(f"## {title}\n\n{new_body}".rstrip())

    result = "\n\n".join(part for part in output if part).strip()
    if len(result) > max_chars:
        LAST_LENGTH_STATS["reason"] = (
            f"核心栏目及完整链接共 {len(result)} 字，超过上限 {max_chars}；"
            "为避免破坏重点内容和链接，未执行硬截断"
        )
        LOGGER.warning("日报长度控制：%s", LAST_LENGTH_STATS["reason"])
    elif LAST_LENGTH_STATS["compressed"]:
        LAST_LENGTH_STATS["reason"] = "已优先精简分类情报、收藏建议和明日方向"
        LOGGER.info("日报长度控制：%s", LAST_LENGTH_STATS["reason"])
    return result


def get_last_length_stats() -> Dict[str, Any]:
    return dict(LAST_LENGTH_STATS)


def markdown_to_feishu_blocks(markdown: str) -> List[Dict[str, Any]]:
    """转换飞书块；只有每日报告大标题进入飞书大纲，完整 URL 使用独立文本块。"""
    blocks: List[Dict[str, Any]] = []
    paragraph: List[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = "\n".join(paragraph).strip()
        paragraph.clear()
        _append_text_with_urls(blocks, text)

    # Markdown 链接在 Docx 纯文本块中不稳定，转换为“文字 + 完整 URL”。
    markdown = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1\n\2", markdown)
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            flush()
            level_marks, title = heading_match.groups()
            title = re.sub(r"\*\*(.*?)\*\*", r"\1", title).strip()
            if level_marks == "#" and DAILY_TITLE_PATTERN.fullmatch(title):
                blocks.append(build_heading1_block(title))
            else:
                blocks.append(build_bold_text_block(title))
        elif URL_PATTERN.fullmatch(line.strip()):
            flush()
            blocks.append(build_text_block(line.strip()))
        elif re.match(r"^\s*-?\s*原文链接[：:]\s*$", line):
            flush()
            blocks.append(build_text_block("原文链接："))
        else:
            paragraph.append(re.sub(r"\*\*(.*?)\*\*", r"\1", line))
    flush()
    return blocks


def _detail_lines(item: Dict[str, Any], index: int) -> List[str]:
    summary = _plain_summary(item)
    points = _summary_points(summary)
    return [
        "",
        f"### {index}. {item.get('title', '未获取到标题')}",
        f"来源：{item.get('source') or '未知来源'}",
        f"平台：{item.get('platform') or '未知平台'}",
        f"发布时间：{item.get('published_at') or '未知时间'}",
        f"原始标题：{item.get('title') or '未获取到标题'}",
        "原文链接：",
        preferred_url(item),
        "",
        f"一句话总结：{summary[:360]}",
        "",
        "核心内容：",
        *(f"- {point}" for point in points),
        "",
        f"为什么重要：{item.get('reason') or '这条内容反映了当前 AI 领域的实际变化。'}",
        "",
        "我可以怎么用：先阅读原文核对能力和限制，再选择一个与自己工作相关的点做小实验。",
        "",
        f"适合谁关注：关注 {_category_name(item.get('category', ''))} 的普通学习者、开发者和从业者",
        "",
        f"学习价值：可以练习如何从一手信息中判断 {_category_name(item.get('category', ''))} 的实际价值。",
    ]


def _repair_section_links(
    body: str,
    records: List[Dict[str, Any]],
) -> Tuple[str, int]:
    chunks = re.split(r"(?m)(?=^### )", body)
    output: List[str] = []
    repaired = 0
    for chunk in chunks:
        if not chunk.strip() or not chunk.lstrip().startswith("### "):
            output.append(chunk.strip())
            continue
        heading = chunk.strip().splitlines()[0]
        record = _match_link_record(heading, records)
        if record is None:
            # 中文标题可能来自模型翻译。没有明确标题映射时，绝不能按条目顺序
            # 猜测链接，否则会把另一条新闻的真实 URL 错配到当前新闻。
            output.append(chunk.strip())
            continue
        expected = record["url"]
        old_urls = URL_PATTERN.findall(chunk)
        has_exact = (
            expected in chunk if expected == "未获取到" else expected in old_urls
        )
        cleaned = _replace_link_field(chunk, expected)
        if not has_exact:
            repaired += 1
        output.append(cleaned.strip())
    return "\n\n".join(part for part in output if part).strip(), repaired


def _replace_link_field(chunk: str, expected: str) -> str:
    """在原字段位置替换链接；字段缺失时放到原始标题后或条目末尾。"""
    lines = chunk.splitlines()
    output: List[str] = []
    skip_next = False
    replaced = False
    for line in lines:
        if skip_next:
            if URL_PATTERN.fullmatch(line.strip()) or line.strip() in {"ht", "https", "无", "见上", "未获取到"}:
                skip_next = False
                continue
            skip_next = False
        # 模型偶尔会把字段输出成“**原文链接**：”。先接受这种 Markdown 写法，
        # 再统一为普通字段，避免误判为缺少链接并额外插入错位的地址。
        match = re.match(r"^\s*-?\s*(?:\*\*)?原文链接(?:\*\*)?[：:](.*)$", line)
        if match:
            output.extend(["原文链接：", expected])
            replaced = True
            skip_next = not match.group(1).strip()
            continue
        output.append(line)
    if not replaced:
        insert_at = len(output)
        for index, line in enumerate(output):
            if line.strip().startswith("原始标题："):
                insert_at = index + 1
                break
        output[insert_at:insert_at] = ["原文链接：", expected, ""]
    return "\n".join(output)


def _link_records(
    items: List[Dict[str, Any]],
    summaries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    records = []
    for index, item in enumerate(items):
        aliases = [str(item.get("title", ""))]
        if index < len(summaries):
            aliases.extend(
                [
                    str(summaries[index].get("中文标题", "")),
                    str(summaries[index].get("原始标题", "")),
                ]
            )
        records.append(
            {
                "url": preferred_url(item),
                "aliases": {_normalize_title(alias) for alias in aliases if alias},
            }
        )
    return records


def _match_link_record(heading: str, records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    title = re.sub(r"^###\s*(?:\d+[.、]\s*)?", "", heading).strip()
    normalized = _normalize_title(title)
    for record in records:
        for alias in record["aliases"]:
            if normalized == alias or (len(alias) >= 8 and (alias in normalized or normalized in alias)):
                return record
    return None


def _normalize_title(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value).lower()


def _append_text_with_urls(blocks: List[Dict[str, Any]], text: str) -> None:
    position = 0
    for match in URL_PATTERN.finditer(text):
        prefix = text[position : match.start()].strip()
        if prefix:
            for chunk in _split_plain_text(prefix, 1800):
                blocks.append(build_text_block(chunk))
        blocks.append(build_text_block(match.group(0)))
        position = match.end()
    suffix = text[position:].strip()
    if suffix:
        for chunk in _split_plain_text(suffix, 1800):
            blocks.append(build_text_block(chunk))


def _split_plain_text(text: str, length: int) -> Iterable[str]:
    value = text
    while len(value) > length:
        split_at = max(value.rfind("\n", 0, length), value.rfind("。", 0, length))
        if split_at < length // 2:
            split_at = length
        else:
            split_at += 1
        yield value[:split_at]
        value = value[split_at:].lstrip()
    if value:
        yield value


def _compact_explanation(body: str, budget: int) -> str:
    """压缩普通说明，任何包含 URL 的行均原样保留。"""
    if len(body) <= budget:
        return body
    if re.search(r"(?m)^### ", body):
        return _compact_subsections(body, budget)
    lines = [line for line in body.splitlines() if line.strip()]
    protected = [line for line in lines if URL_PATTERN.search(line)]
    ordinary = [line for line in lines if not URL_PATTERN.search(line)]
    reserved = sum(len(line) + 1 for line in protected)
    remaining = max(budget - reserved, 0)
    kept: List[str] = []
    for line in ordinary:
        if remaining <= 0:
            break
        if len(line) <= remaining:
            kept.append(line)
            remaining -= len(line) + 1
        elif remaining >= 20:
            kept.append(line[:remaining].rstrip("，,；; ") + "。")
            remaining = 0
    return "\n".join(kept + protected)


def _compact_subsections(body: str, budget: int) -> str:
    """压缩含三级小标题的栏目，同时保留每个分类和链接的上下文。"""
    chunks = [chunk.strip() for chunk in re.split(r"(?m)(?=^### )", body) if chunk.strip()]
    if not chunks:
        return body
    # 即使整体预算很小，也必须保留所有分类标题；否则日报会变成只剩第一类的残缺排版。
    each_budget = max(90, budget // len(chunks))
    compacted: List[str] = []
    for chunk in chunks:
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        kept = [lines[0]]
        used = len(lines[0]) + 1
        for index, line in enumerate(lines[1:], 1):
            contains_url = bool(URL_PATTERN.search(line))
            previous_is_context = (
                contains_url
                and len(kept) == 1
                and index > 1
                and not URL_PATTERN.search(lines[index - 1])
            )
            if previous_is_context:
                context = lines[index - 1]
                if context not in kept:
                    kept.append(context)
                    used += len(context) + 1
            if contains_url:
                kept.append(line)
                used += len(line) + 1
            elif used + len(line) + 1 <= each_budget:
                kept.append(line)
                used += len(line) + 1
        compacted.append("\n".join(kept))
    return "\n\n".join(compacted)


def _summary_points(summary: str) -> List[str]:
    parts = [
        value.strip(" -。")
        for value in re.split(r"[。；;]\s*", summary)
        if value.strip()
    ][:5]
    fallbacks = [
        "信息来自公开可见页面，关键事实应以原始来源为准",
        "需要重点核对具体能力、适用场景和限制",
        "可以结合自己的工作或学习目标判断是否值得实践",
    ]
    for fallback in fallbacks:
        if len(parts) >= 3:
            break
        parts.append(fallback)
    return parts


def _plain_summary(item: Dict[str, Any]) -> str:
    value = str(item.get("summary") or "暂无摘要，请打开原文查看。")
    if item.get("fetch_success") is False and "原文抓取失败" not in value:
        return f"{value}；原文抓取失败，仅基于标题和摘要整理。"
    return value


def _learning_topics(items: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    mapping = {
        "model_release": ("模型能力评估", "比较模型能力、成本、速度和适用边界的方法"),
        "ai_agent": ("AI Agent 与 MCP", "让模型调用工具并完成多步骤任务的技术"),
        "multimodal": ("多模态 AI", "统一理解和生成文本、图片、语音或视频的技术"),
        "ai_coding": ("AI 编程工作流", "用 AI 辅助理解、生成、测试和审查代码的方法"),
        "open_source": ("开源 AI 项目", "可以查看源码、复现并二次开发的 AI 工具或模型"),
        "paper": ("AI 论文阅读", "从问题、方法、实验和限制四部分理解研究成果"),
    }
    result: List[Tuple[str, str]] = []
    for item in items:
        value = mapping.get(item.get("category", ""))
        if value and value not in result:
            result.append(value)
    defaults = [
        ("信息源验证", "优先核对官方博客、论文和项目仓库，避免只看二手标题"),
        ("提示词与结构化输出", "让模型按固定字段输出可复用结果的方法"),
        ("AI 安全与隐私", "在使用模型和第三方工具时保护数据的方法"),
    ]
    for value in defaults:
        if value not in result:
            result.append(value)
    return result[:5]


def _link_lines(items: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for item in items:
        lines.extend([f"- {item.get('title', '未获取到标题')}", preferred_url(item)])
    return lines


def _unique_categories(items: List[Dict[str, Any]]) -> List[str]:
    return list(
        dict.fromkeys(_category_name(item.get("category", "")) for item in items)
    )


def _category_name(category: str) -> str:
    names = {
        "model_release": "模型发布",
        "ai_agent": "Agent 与自动化",
        "multimodal": "多模态",
        "ai_coding": "AI 编程",
        "open_source": "开源项目",
        "paper": "论文研究",
        "tool_update": "工具更新",
        "industry_news": "行业动态",
        "tutorial": "教程",
        "opinion": "观点",
        "business": "商业",
        "video": "视频生成",
        "social_discussion": "社媒讨论",
    }
    return names.get(category, category or "AI 综合动态")
