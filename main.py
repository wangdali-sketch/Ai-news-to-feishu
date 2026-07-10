import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

from ai_summarizer import generate_ai_report, get_last_ai_run_stats
from collectors import (
    collect_arxiv,
    collect_github,
    collect_manual_links,
    collect_rss,
    collect_social,
    collect_web_sources,
)
from content_deduper import deduplicate_content, save_seen_items
from content_ranker import rank_content
from content_schema import preferred_url
from feishu_client import FeishuClient, build_text_block
from report_generator import (
    constrain_report_length,
    generate_rule_based_report,
    get_last_length_stats,
    markdown_to_feishu_blocks,
    validate_report,
)


PROJECT_DIR = Path(__file__).resolve().parent
LOGGER = logging.getLogger("ai_frontier_radar")
COMPLETION_PREFIX = "AI_RADAR_WRITE_COMPLETED"
REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")
LAST_COLLECTION_STATS: Dict[str, int] = {
    "collected_count": 0,
    "deduplicated_count": 0,
    "ranked_count": 0,
    "body_fetch_success_count": 0,
    "body_fetch_failure_count": 0,
}


def run_once() -> Dict[str, Any]:
    """采集多来源 AI 内容，生成日报并写入飞书 Docx。"""
    load_dotenv(PROJECT_DIR / ".env")
    _setup_logging()

    report_date = _current_report_date()
    completion_marker = f"{COMPLETION_PREFIX}:{report_date}"
    force_write = _get_bool_env("AI_RADAR_FORCE_WRITE", False)
    state_file = PROJECT_DIR / "data" / "last_successful_run.json"

    client = FeishuClient.from_env()
    if not force_write and _local_run_completed(state_file, report_date):
        LOGGER.info("今天的日报已成功写入，跳过重复运行：%s", report_date)
        return {"code": 0, "skipped": True, "reason": "本地状态显示今天已写入"}
    if not force_write:
        try:
            if client.document_contains_text(completion_marker):
                LOGGER.info("飞书文档中已存在今天的完成标记，跳过重复写入：%s", report_date)
                _save_run_state(state_file, report_date)
                return {"code": 0, "skipped": True, "reason": "飞书中今天已写入"}
        except Exception as exc:
            # 某些旧应用只有写权限，没有读取权限。此时继续执行，并依靠本地状态去重。
            LOGGER.warning("无法检查飞书中的完成标记，将继续运行：%s", exc)

    config = load_sources_config()
    lookback_days = _get_int_env("AI_RADAR_LOOKBACK_DAYS", _get_int_env("AI_NEWS_LOOKBACK_DAYS", 2))
    limit = _get_int_env("AI_RADAR_LIMIT", _get_int_env("AI_NEWS_LIMIT", 20))
    history_file = PROJECT_DIR / "data" / "seen_items.json"

    ranked_items = _collect_and_rank_content(config, lookback_days, limit, history_file)

    max_items_for_ai = _target_ai_item_count(limit)
    max_text_per_item = _get_int_env("MAX_TEXT_PER_ITEM", 3000)
    max_report_chars = _get_int_env("MAX_REPORT_CHARS", 12000)
    ai_items = ranked_items[:max_items_for_ai]
    api_configured = bool(os.getenv("AI_API_KEY", "").strip())
    LOGGER.info(
        "运行统计｜进入 AI 的内容数=%s",
        len(ai_items) if api_configured else 0,
    )
    with_url = sum(preferred_url(item) != "未获取到" for item in ranked_items)
    LOGGER.info("运行统计｜有 URL 的内容数=%s", with_url)
    LOGGER.info("运行统计｜缺失 URL 的内容数=%s", len(ranked_items) - with_url)
    for index, item in enumerate(ranked_items, 1):
        LOGGER.info(
            "抓取状态｜第 %s 条｜正文抓取成功=%s｜标题=%s",
            index,
            "是" if item.get("fetch_success", True) else "否",
            item.get("title", ""),
        )

    ai_report = generate_ai_report(
        ranked_items,
        report_date,
        max_items=max_items_for_ai,
        max_text_per_item=max_text_per_item,
        max_report_chars=max_report_chars,
    )
    ai_stats = get_last_ai_run_stats()
    LOGGER.info(
        "运行统计｜是否调用 DeepSeek API=%s；API 请求次数=%s；单条降级数=%s",
        "是" if ai_stats["api_called"] else "否",
        ai_stats["api_calls"],
        ai_stats["single_item_fallbacks"],
    )
    degraded = ai_report is None
    LOGGER.info("运行统计｜是否发生降级=%s", "是" if degraded else "否")
    report_items = ranked_items
    report = ai_report or generate_rule_based_report(report_items, report_date)
    report, validation = validate_report(report, report_items)
    report = constrain_report_length(report, max_chars=max_report_chars)
    report, final_validation = validate_report(report, report_items)
    validation["repaired_links"] += (
        final_validation["repaired_links"] + ai_stats.get("links_repaired", 0)
    )
    validation["truncated_link_found"] = (
        validation["truncated_link_found"]
        or final_validation["truncated_link_found"]
        or ai_stats.get("truncated_link_found", False)
    )
    length_stats = get_last_length_stats()
    LOGGER.info("运行统计｜被修复补回链接的条目数=%s", validation["repaired_links"])
    LOGGER.info(
        "运行统计｜是否发现链接被截断=%s",
        "是" if validation["truncated_link_found"] else "否",
    )
    LOGGER.info(
        "运行统计｜是否发生字数压缩=%s；原因=%s",
        "是" if length_stats["compressed"] else "否",
        length_stats["reason"] or "未超过限制",
    )
    LOGGER.info(
        "运行统计｜最终日报总字符数=%s；中文字符数=%s；中文占比=%.2f%%",
        len(report),
        ai_stats.get("chinese_characters", 0),
        ai_stats.get("chinese_ratio", 0.0) * 100,
    )
    blocks = markdown_to_feishu_blocks(report)
    # 完成标记必须最后写入；只有所有日报块都写完，下一次运行才会跳过。
    blocks.append(build_text_block(completion_marker))

    LOGGER.info("日报已生成，开始向飞书写入 %s 个内容块", len(blocks))
    try:
        result = client.append_blocks_to_document(blocks)
    except Exception:
        LOGGER.exception("运行统计｜飞书写入是否成功=否")
        raise
    save_seen_items(ranked_items, history_file)
    _save_run_state(state_file, report_date)

    children = result.get("data", {}).get("children", [])
    block_count = len(children) if isinstance(children, list) else "未知"
    LOGGER.info(
        "运行统计｜飞书写入是否成功=是；日期=%s；内容=%s 条；飞书块=%s 个",
        report_date,
        len(ranked_items),
        block_count,
    )
    return result


def run_local_test() -> Dict[str, Any]:
    """生成本地测试日报，不写飞书，也不改动去重历史或完成标记。"""
    load_dotenv(PROJECT_DIR / ".env")
    _setup_logging()

    report_date = _current_report_date()
    config = load_sources_config()
    lookback_days = _get_int_env("AI_RADAR_LOOKBACK_DAYS", _get_int_env("AI_NEWS_LOOKBACK_DAYS", 2))
    limit = _get_int_env("AI_RADAR_LIMIT", _get_int_env("AI_NEWS_LIMIT", 20))
    history_file = PROJECT_DIR / "data" / "seen_items.json"
    ranked_items = _collect_and_rank_content(config, lookback_days, limit, history_file)

    max_items_for_ai = _target_ai_item_count(limit)
    max_text_per_item = _get_int_env("MAX_TEXT_PER_ITEM", 3000)
    max_report_chars = _get_int_env("MAX_REPORT_CHARS", 12000)
    ai_items = ranked_items[:max_items_for_ai]
    ai_report = generate_ai_report(
        ranked_items,
        report_date,
        max_items=max_items_for_ai,
        max_text_per_item=max_text_per_item,
        max_report_chars=max_report_chars,
    )
    ai_stats = get_last_ai_run_stats()
    report_items = ranked_items
    report = ai_report or generate_rule_based_report(report_items, report_date)
    report, validation = validate_report(report, report_items)
    report = constrain_report_length(report, max_chars=max_report_chars)
    report, final_validation = validate_report(report, report_items)

    output_dir = PROJECT_DIR / "data" / "test_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ai_frontier_radar_{report_date}-v2.md"
    output_path.write_text(report + "\n", encoding="utf-8")
    result = {
        "code": 0,
        "local_test": True,
        "output_path": str(output_path),
        "total_collected": LAST_COLLECTION_STATS["collected_count"],
        "deduplicated_count": LAST_COLLECTION_STATS["deduplicated_count"],
        "ranked_count": len(ranked_items),
        "featured_count": ai_stats.get("featured_count", 0),
        "ordinary_count": ai_stats.get("ordinary_count", 0),
        "paper_count": ai_stats.get("paper_count", 0),
        "report_items": ai_stats.get("total_report_items", len(report_items)),
        "items_with_url": validation["items_with_url"],
        "body_fetch_success_count": LAST_COLLECTION_STATS["body_fetch_success_count"],
        "body_fetch_failure_count": LAST_COLLECTION_STATS["body_fetch_failure_count"],
        "deduplicated": True,
        "repaired_links": validation["repaired_links"] + final_validation["repaired_links"],
        "ai_used": ai_report is not None,
        "report_characters": len(report),
        "chinese_characters": ai_stats.get("chinese_characters", 0),
        "chinese_ratio": ai_stats.get("chinese_ratio", 0.0),
    }
    LOGGER.info(
        "本地测试日报已生成｜路径=%s｜日报内容=%s 条｜字符数=%s｜不会写入飞书",
        output_path,
        result["report_items"],
        result["report_characters"],
    )
    return result


def _collect_and_rank_content(
    config: Dict[str, Any],
    lookback_days: int,
    limit: int,
    history_file: Path,
) -> List[Dict[str, str]]:
    """执行采集、去重、排序；供正式写入和本地测试共用。"""
    rss_sources = list(config.get("rss_sources", []))
    arxiv_sources = [
        source
        for source in rss_sources
        if source.get("category") == "paper" or "arxiv.org" in str(source.get("url", ""))
    ]
    normal_rss_sources = [source for source in rss_sources if source not in arxiv_sources]

    LOGGER.info("开始采集 AI 前沿公开内容，回看最近 %s 天", lookback_days)
    content_items: List[Dict[str, str]] = []
    content_items.extend(_safe_collect("RSS", collect_rss, normal_rss_sources, lookback_days))
    content_items.extend(_safe_collect("GitHub", collect_github, config.get("github_sources", [])))
    content_items.extend(_safe_collect("arXiv", collect_arxiv, arxiv_sources, lookback_days))
    content_items.extend(
        _safe_collect("手动链接", collect_manual_links, config.get("manual_links", []), PROJECT_DIR)
    )
    content_items.extend(
        _safe_collect("社媒公开源", collect_social, config.get("social_sources", []), lookback_days)
    )
    content_items.extend(_safe_collect("公开网页", collect_web_sources, config.get("web_sources", [])))

    LAST_COLLECTION_STATS["collected_count"] = len(content_items)
    LAST_COLLECTION_STATS["body_fetch_success_count"] = sum(
        bool(item.get("body_fetch_success")) for item in content_items
    )
    LAST_COLLECTION_STATS["body_fetch_failure_count"] = sum(
        bool(item.get("body_fetch_attempted")) and not bool(item.get("body_fetch_success"))
        for item in content_items
    )
    LOGGER.info("运行统计｜总内容数=%s", len(content_items))
    unique_items = deduplicate_content(content_items, history_file=history_file)
    LAST_COLLECTION_STATS["deduplicated_count"] = len(content_items) - len(unique_items)
    LOGGER.info("运行统计｜去重后内容数=%s", len(unique_items))
    ranked_items = rank_content(
        unique_items,
        limit=limit,
        max_per_source=_get_int_env("AI_RADAR_MAX_PER_SOURCE", _get_int_env("AI_NEWS_MAX_PER_SOURCE", 4)),
    )
    LOGGER.info("去重和排序后选出 %s 条内容", len(ranked_items))
    LAST_COLLECTION_STATS["ranked_count"] = len(ranked_items)
    return ranked_items


def _target_ai_item_count(limit: int) -> int:
    """保证深度日报具备 5 条重点、8 条动态和 3 篇论文所需的候选覆盖面。"""
    configured = _get_int_env("MAX_ITEMS_FOR_AI", 20)
    target = max(configured, 20)
    return min(target, limit)


def load_sources_config() -> Dict[str, Any]:
    """读取 YAML 来源配置。"""
    configured = os.getenv("AI_RADAR_SOURCES_FILE", "config/sources.yml").strip()
    path = Path(configured)
    if not path.is_absolute():
        path = PROJECT_DIR / path
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise RuntimeError(f"来源配置文件不存在：{path}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"来源配置文件格式错误：{path}；{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("sources.yml 顶层必须是键值结构。")
    return payload


def _safe_collect(
    name: str,
    function: Callable[..., List[Dict[str, str]]],
    *args: Any,
) -> List[Dict[str, str]]:
    """隔离采集器错误，避免一个平台失败导致整次日报中断。"""
    try:
        items = function(*args)
        LOGGER.info("%s 采集器返回 %s 条", name, len(items))
        return items
    except Exception as exc:
        LOGGER.exception("%s 采集器运行失败，已跳过：%s", name, exc)
        return []


def _setup_logging() -> None:
    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    file_handler = logging.FileHandler(log_dir / "daily.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(console)
    root.addHandler(file_handler)


def _local_run_completed(path: Path, report_date: str) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return payload.get("report_date") == report_date and payload.get("completed") is True


def _save_run_state(path: Path, report_date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "report_date": report_date,
                "completed": True,
                "completed_at": datetime.now(REPORT_TIMEZONE).isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _current_report_date() -> str:
    """统一使用北京时间/新加坡时间确定日报日期，避免 GitHub UTC 运行器跨日。"""
    return datetime.now(REPORT_TIMEZONE).strftime("%Y-%m-%d")


def _get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return max(int(raw_value), 1)
    except ValueError:
        LOGGER.warning("环境变量 %s 不是整数，已使用默认值 %s", name, default)
        return default


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(description="AI 前沿信息雷达")
        parser.add_argument(
            "--test-local",
            action="store_true",
            help="只生成 data/test_reports 中的本地测试日报，不写飞书",
        )
        args = parser.parse_args()
        if args.test_local:
            run_local_test()
        else:
            run_once()
    except Exception:
        LOGGER.exception("AI 前沿信息雷达运行失败")
        raise
