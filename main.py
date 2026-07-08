import os
from datetime import datetime

from dotenv import load_dotenv

from feishu_client import FeishuClient, build_ai_news_report_blocks
from news_fetcher import fetch_ai_news


def run_once():
    """本地运行一次：抓取 AI 新闻日报并写入飞书 Docx 文档。"""
    load_dotenv()

    news_limit = _get_int_env("AI_NEWS_LIMIT", 8)
    lookback_days = _get_int_env("AI_NEWS_LOOKBACK_DAYS", 2)

    print(f"正在抓取最近 {lookback_days} 天的 AI 前沿新闻...")
    news_items = fetch_ai_news(limit=news_limit, lookback_days=lookback_days)

    report_date = datetime.now().strftime("%Y-%m-%d")
    blocks = build_ai_news_report_blocks(report_date, news_items)

    print(f"已生成 {len(news_items)} 条新闻，正在写入飞书文档...")
    client = FeishuClient.from_env()
    result = client.append_blocks_to_document(blocks)

    children = result.get("data", {}).get("children", [])
    block_count = len(children) if isinstance(children, list) else "未知"

    print("AI 新闻日报写入成功。")
    print(f"文档 ID：{client.document_id}")
    print(f"新闻数量：{len(news_items)}")
    print(f"新增块数量：{block_count}")
    return result


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


if __name__ == "__main__":
    run_once()
