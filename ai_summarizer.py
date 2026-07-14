import json
import logging
import os
import re
import time
from typing import Any, Dict, Iterable, List, Optional

import requests

from content_schema import preferred_url
from report_generator import plan_report_items


LOGGER = logging.getLogger(__name__)
REQUIRED_HEADINGS = [
    "## 今日 AI 总览",
    "## 今日最重要的 5 条 AI 新闻",
    "## 普通重要动态",
    "## 论文精选",
]

LAST_AI_RUN_STATS: Dict[str, Any] = {
    "api_called": False,
    "api_calls": 0,
    "single_item_fallbacks": 0,
    "global_failed": False,
    "links_repaired": 0,
    "truncated_link_found": False,
    "featured_count": 0,
    "ordinary_count": 0,
    "paper_count": 0,
    "total_report_items": 0,
    "chinese_characters": 0,
    "chinese_ratio": 0.0,
    "expansion_calls": 0,
}


def generate_ai_report(
    items: Iterable[Dict[str, Any]],
    report_date: str,
    timeout: int = 90,
    max_items: Optional[int] = None,
    max_text_per_item: Optional[int] = None,
    max_report_chars: Optional[int] = None,
    min_chinese_chars: int = 10000,
) -> str:
    """先逐条深度提炼，再让大模型生成日报；任何 AI 失败都禁止规则降级。"""
    _reset_stats()
    api_key = os.getenv("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 AI_API_KEY：为避免写入未翻译内容，本次日报已终止")

    max_items = max_items or _get_positive_int_env("MAX_ITEMS_FOR_AI", 10)
    max_text_per_item = max_text_per_item or _get_positive_int_env("MAX_TEXT_PER_ITEM", 3000)
    max_report_chars = max_report_chars or _get_positive_int_env("MAX_REPORT_CHARS", 12000)
    selected_items = list(items)[:max_items]
    if not selected_items:
        raise RuntimeError("没有可交给大模型的内容，本次日报已终止")

    settings = _api_settings(api_key, timeout)
    summaries: List[Dict[str, Any]] = []
    for index, item in enumerate(selected_items, 1):
        compact = _compact_item(item, max_text_per_item)
        try:
            summary = _summarize_single_item(compact, settings)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            LAST_AI_RUN_STATS["global_failed"] = True
            raise RuntimeError(
                f"第 {index} 条内容的 AI 翻译总结失败：为避免降级，本次日报已终止"
            ) from exc
        # 链接属于程序数据，不信任也不采用模型生成的链接。
        summary["原文链接"] = preferred_url(item)
        summary["原始标题"] = item.get("title") or "未获取到标题"
        summary["来源"] = item.get("source") or "未知来源"
        summary["平台"] = item.get("platform") or "未知平台"
        summary["发布时间"] = item.get("published_at") or "未知时间"
        summary["内容编号"] = index
        summaries.append(summary)

    report_plan = plan_report_items(selected_items)
    summaries_by_item = {
        id(item): summaries[index] for index, item in enumerate(selected_items)
    }
    planned_summaries = {
        name: [summaries_by_item[id(item)] for item in values if id(item) in summaries_by_item]
        for name, values in report_plan.items()
    }
    LAST_AI_RUN_STATS.update(
        {
            "featured_count": len(report_plan["featured"]),
            "ordinary_count": len(report_plan["ordinary"]),
            "paper_count": len(report_plan["papers"]),
            "total_report_items": len(
                {id(item) for values in report_plan.values() for item in values}
            ),
        }
    )

    try:
        report = _generate_global_report(
            planned_summaries,
            report_date,
            max_report_chars,
            settings,
        )
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        LAST_AI_RUN_STATS["global_failed"] = True
        raise RuntimeError("AI 全局日报生成失败：为避免降级，本次日报已终止") from exc

    # 模型遗漏或缩短链接时，由程序根据原始内容强制补回。
    from report_generator import ensure_report_links

    LAST_AI_RUN_STATS["truncated_link_found"] = bool(
        re.search(r"(?m)^-?\s*原文链接[：:]\s*(?:\n\s*)?(?:ht|https|无|见上)\s*$", report)
    )
    repaired, repaired_count = ensure_report_links(report, selected_items, summaries=summaries)
    LAST_AI_RUN_STATS["links_repaired"] = repaired_count
    chinese_characters, chinese_ratio = _chinese_metrics(repaired)
    LAST_AI_RUN_STATS["chinese_characters"] = chinese_characters
    LAST_AI_RUN_STATS["chinese_ratio"] = chinese_ratio
    if not _has_required_structure(repaired, report_date):
        LAST_AI_RUN_STATS["global_failed"] = True
        raise RuntimeError("AI 日报缺少固定栏目：为避免写入残缺内容，本次日报已终止")
    if chinese_characters < min_chinese_chars:
        LOGGER.warning(
            "大模型日报中文字符数不足：%s，开始基于同一批来源进行受约束扩写",
            chinese_characters,
        )
        try:
            expanded = _expand_global_report(
                repaired,
                planned_summaries,
                report_date,
                settings,
            )
            repaired, extra_repairs = ensure_report_links(
                expanded,
                selected_items,
                summaries=summaries,
            )
            LAST_AI_RUN_STATS["links_repaired"] += extra_repairs
            if not _has_required_structure(repaired, report_date):
                raise ValueError("扩写结果缺少固定栏目")
            chinese_characters, chinese_ratio = _chinese_metrics(repaired)
            LAST_AI_RUN_STATS["chinese_characters"] = chinese_characters
            LAST_AI_RUN_STATS["chinese_ratio"] = chinese_ratio
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            LOGGER.warning("日报扩写失败，将保留扩写前的 AI 中文版：%s", exc)
    if chinese_characters < min_chinese_chars:
        LOGGER.warning(
            "AI 日报中文字符数为 %s，低于建议值 %s；保留 AI 中文版，不执行规则降级",
            chinese_characters,
            min_chinese_chars,
        )
    LOGGER.info(
        "两阶段 AI 日报生成完成：逐条提炼 %s 条，规则降级 %s 条",
        len(summaries),
        LAST_AI_RUN_STATS["single_item_fallbacks"],
    )
    return repaired


def get_last_ai_run_stats() -> Dict[str, Any]:
    """返回本次 AI 调用统计，供 daily.log 记录。"""
    return dict(LAST_AI_RUN_STATS)


def _summarize_single_item(
    item: Dict[str, Any],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = f"""
请深度阅读下面这一条 AI 前沿内容，并只返回一个 JSON 对象，不要返回 Markdown。

字段必须完整：
{{
  "中文标题": "",
  "原始标题": "",
  "来源": "",
  "平台": "",
  "发布时间": "",
  "原文链接": "",
  "一句话总结": "",
  "核心内容": ["", "", "", ""],
  "为什么重要": "",
  "我可以怎么用": "",
  "适合谁关注": "",
  "学习价值": "",
  "关键词": ["", "", ""]
}}

写作要求：
1. 使用简体中文，核心内容写 3～5 个具体要点，不要照搬英文摘要。
2. 工具或模型更新要说明新增能力；论文要说明问题、方法、结论和意义；
   产品动态要说明实际影响；安全内容要说明风险、受影响者和注意事项。
3. “为什么重要”不能只写“值得关注”，要说明对行业、开发者或普通学习者的影响。
4. “我可以怎么用”必须给出可以执行的建议。
5. 原文链接只能原样复制输入中的 original_url（优先）或 url。
   不得删除、改写、缩短、补全或猜测链接；没有链接只能写“未获取到”。

输入内容：
{json.dumps(item, ensure_ascii=False)}
""".strip()
    content = _chat_completion(
        settings,
        system=(
            "你是严谨的 AI 前沿情报编辑。只能依据输入材料提炼，不编造事实，"
            "不生成输入中不存在的链接。"
        ),
        user=prompt,
        max_tokens=1800,
        attempts=2,
    )
    parsed = _parse_json_object(content)
    required = {
        "中文标题",
        "原始标题",
        "来源",
        "平台",
        "发布时间",
        "一句话总结",
        "核心内容",
        "为什么重要",
        "我可以怎么用",
        "适合谁关注",
        "学习价值",
        "关键词",
    }
    if not required.issubset(parsed):
        raise ValueError("单条提炼结果缺少必要字段")
    if not isinstance(parsed["核心内容"], list) or len(parsed["核心内容"]) < 3:
        raise ValueError("单条提炼的核心内容不足 3 条")
    return parsed


def _generate_global_report(
    plan: Dict[str, List[Dict[str, Any]]],
    report_date: str,
    max_report_chars: int,
    settings: Dict[str, Any],
) -> str:
    prompt = f"""
请根据下方已经逐条深度提炼的结构化内容，生成一份可直接阅读的 Markdown 日报。

标题和栏目必须严格按以下顺序，不得改名或省略：
# AI 前沿信息雷达｜{report_date}
## 今日 AI 总览
## 今日最重要的 5 条 AI 新闻
## 普通重要动态
## 论文精选

具体要求：
1. 全文必须以简体中文表达。英文只可用于模型名、产品名、公司名、必要技术名词和“原始标题”字段；不得出现成段英文。
2. 今日 AI 总览写 400～600 个中文字符，直接解释当天最重要的 2～4 个变化、它们之间的关系和实际意义，不能罗列标题。
3. 今日最重要的 5 条 AI 新闻必须恰好 5 条，每条写 800～1200 个中文字符，使用三级标题。每条依次包含：中文标题、原始标题（仅一次）、一句话结论、发生背景、具体发布或变化、3～6 个核心信息点、与此前版本或行业现状的变化、对普通用户影响、对开发者和企业影响、限制/风险/尚未确认的信息、为什么值得关注、信息可信度、来源与原文链接。
4. 普通重要动态保留 8～12 条，每条写 350～600 个中文字符，使用三级标题。每条必须说明发生了什么、为什么重要、会影响谁、限制或待确认点、来源与原文链接。不要与重点新闻重复。
5. 论文精选保留 3～5 篇，每篇写 400～700 个中文字符，使用三级标题。用普通人能理解的中文解释研究问题、采用方法、得到的结果、实际用途和目前局限。不要粘贴英文 Abstract，也不要与前两栏重复。
6. 只依据输入的结构化内容写作；输入没有提供的事实必须标为“尚未确认”或不写，禁止编造。
7. 所有“原文链接”必须使用两行格式：
   原文链接：
   https://example.com/完整地址
8. 只能原样使用输入 JSON 的“原文链接”。不得删除、改写、缩短、猜测链接。
   链接为“未获取到”时必须原样显示“未获取到”。
9. 目标为 10000～15000 个中文字符。不要用重复句子、套话、标题扩写凑字数；每段都必须增加可核对的信息或明确综合分析。

已分配的结构化内容 JSON（重点、普通、论文三个列表中的条目不得跨栏重复）：
{json.dumps(plan, ensure_ascii=False)}
""".strip()
    content = _chat_completion(
        settings,
        system=(
            "你是 AI 前沿信息雷达的主编。输出简体中文 Markdown，事实仅来自输入，"
            "链接必须逐字保留，禁止自行生成链接。"
        ),
        user=prompt,
        max_tokens=max(9000, min(max_report_chars + 2000, 16000)),
        attempts=3,
    )
    return _remove_code_fence(content)


def _expand_global_report(
    draft: str,
    plan: Dict[str, List[Dict[str, Any]]],
    report_date: str,
    settings: Dict[str, Any],
) -> str:
    """在不引入新事实的前提下扩展篇幅不足的日报初稿。"""
    prompt = f"""
下面是一份结构正确但中文内容偏短的 AI 日报初稿。请返回完整重写后的 Markdown 日报，不要只返回补丁。

必须保留且只使用以下栏目：
# AI 前沿信息雷达｜{report_date}
## 今日 AI 总览
## 今日最重要的 5 条 AI 新闻
## 普通重要动态
## 论文精选

扩写规则：
1. 全文达到 10000～15000 个中文字符，正文以简体中文为主；不要重复原句、不要堆砌空泛形容词。
2. 只能使用下方“可靠结构化资料”中的事实。资料不足时明确写“尚未确认”或“原始资料未说明”，不得补造背景、数据、功能或风险。
3. 重点新闻每条补足发生背景、具体变化、行业对比、普通用户影响、开发者/企业影响和限制；普通动态补足影响对象与待确认点；论文补足研究问题、方法、结果、用途和局限。
4. 英文只保留产品名、公司名、技术名词和原始标题；原始标题每条只出现一次。
5. 必须保留初稿中每个条目的原文链接，且每条只出现一次，格式为“原文链接：”下一行完整 URL。

初稿：
{draft}

可靠结构化资料：
{json.dumps(plan, ensure_ascii=False)}
""".strip()
    LAST_AI_RUN_STATS["expansion_calls"] += 1
    content = _chat_completion(
        settings,
        system="你是严谨的中文 AI 情报编辑。仅基于给定资料扩写，绝不编造。",
        user=prompt,
        max_tokens=16000,
        attempts=2,
    )
    return _remove_code_fence(content)


def _chat_completion(
    settings: Dict[str, Any],
    *,
    system: str,
    user: str,
    max_tokens: int,
    attempts: int,
) -> str:
    payload = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        LAST_AI_RUN_STATS["api_called"] = True
        LAST_AI_RUN_STATS["api_calls"] += 1
        try:
            response = requests.post(
                settings["endpoint"],
                headers={
                    "Authorization": f"Bearer {settings['api_key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=settings["timeout"],
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            if not str(content).strip():
                raise ValueError("大模型返回了空内容")
            return str(content).strip()
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                LOGGER.warning("大模型 API 调用失败，将重试：%s", exc)
                time.sleep(2**attempt)
    if last_error:
        raise last_error
    raise ValueError("大模型 API 调用失败")


def _compact_item(item: Dict[str, Any], max_text_per_item: int) -> Dict[str, Any]:
    """仅截断正文和摘要，链接字段永远完整保留。"""
    return {
        "title": item.get("title", ""),
        "source": item.get("source", ""),
        "platform": item.get("platform", ""),
        "category": item.get("category", ""),
        "url": item.get("url", ""),
        "original_url": item.get("original_url") or item.get("url", ""),
        "published_at": item.get("published_at", ""),
        "summary": str(item.get("summary", ""))[:800],
        "raw_text": str(item.get("raw_text", ""))[:max_text_per_item],
        "reason": item.get("reason", ""),
        "fetch_success": item.get("fetch_success", True),
    }


def _rule_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    summary = str(item.get("summary") or "暂无可用摘要")
    points = [
        point.strip(" -。")
        for point in re.split(r"[。；;]\s*", summary)
        if point.strip()
    ][:5]
    while len(points) < 3:
        points.append(
            [
                "当前可见信息有限，关键结论需要结合原文核对",
                "可先判断内容与自己的学习或工作场景是否相关",
                "建议优先关注一手来源中的功能、方法和限制",
            ][len(points)]
        )
    return {
        "中文标题": item.get("title") or "未获取到标题",
        "原始标题": item.get("title") or "未获取到标题",
        "来源": item.get("source") or "未知来源",
        "平台": item.get("platform") or "未知平台",
        "发布时间": item.get("published_at") or "未知时间",
        "原文链接": preferred_url(item),
        "一句话总结": summary[:300],
        "核心内容": points,
        "为什么重要": item.get("reason") or "这条内容反映了当前 AI 领域的实际变化。",
        "我可以怎么用": "先阅读原文核对细节，再选取一个与自身场景相关的要点实践。",
        "适合谁关注": "普通 AI 学习者、开发者、产品经理和相关从业者",
        "学习价值": "练习从一手信息中识别能力、应用场景和限制。",
        "关键词": [item.get("category") or "AI", item.get("platform") or "信息源", "实践"],
    }


def _parse_json_object(value: str) -> Dict[str, Any]:
    text = _remove_code_fence(value)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("大模型没有返回 JSON 对象")
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("大模型返回结果不是 JSON 对象")
    return payload


def _remove_code_fence(value: str) -> str:
    text = str(value).strip()
    text = re.sub(r"^```(?:json|markdown|md)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _has_required_structure(content: str, report_date: str) -> bool:
    if f"# AI 前沿信息雷达｜{report_date}" not in content:
        return False
    if any(heading not in content for heading in REQUIRED_HEADINGS):
        return False
    return True


def _chinese_metrics(content: str) -> tuple[int, float]:
    """统计中文字符占中英文正文字符的比例，链接不参与分母。"""
    without_urls = re.sub(r"https?://\S+", "", content)
    chinese = sum("\u4e00" <= char <= "\u9fff" for char in without_urls)
    english = sum(char.isascii() and char.isalpha() for char in without_urls)
    return chinese, chinese / max(chinese + english, 1)


def _api_settings(api_key: str, timeout: int) -> Dict[str, Any]:
    base_url = (os.getenv("AI_BASE_URL", "").strip() or "https://api.deepseek.com").rstrip("/")
    return {
        "api_key": api_key,
        "endpoint": (
            base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        ),
        "model": os.getenv("AI_MODEL", "").strip() or "deepseek-chat",
        "timeout": timeout,
    }


def _reset_stats() -> None:
    LAST_AI_RUN_STATS.update(
        {
            "api_called": False,
            "api_calls": 0,
            "single_item_fallbacks": 0,
            "global_failed": False,
            "links_repaired": 0,
            "truncated_link_found": False,
            "featured_count": 0,
            "ordinary_count": 0,
            "paper_count": 0,
            "total_report_items": 0,
            "chinese_characters": 0,
            "chinese_ratio": 0.0,
            "expansion_calls": 0,
        }
    )


def _get_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return max(int(value), 1)
    except ValueError:
        LOGGER.warning("环境变量 %s 不是正整数，已使用默认值 %s", name, default)
        return default
