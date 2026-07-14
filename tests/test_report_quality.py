from datetime import datetime
from pathlib import Path

import pytest
import requests

import ai_summarizer
import main
from ai_summarizer import generate_ai_report
from collectors.manual_link_collector import collect_manual_links
from collectors.rss_collector import collect_rss
from collectors.arxiv_collector import collect_arxiv
from content_ranker import rank_content
from content_schema import build_content_item
from report_generator import (
    constrain_report_length,
    ensure_report_links,
    generate_rule_based_report,
    markdown_to_feishu_blocks,
    plan_report_items,
)


def make_item(url: str, title: str = "测试 AI 工具更新"):
    return build_content_item(
        title=title,
        source="测试来源",
        platform="tool",
        category="tool_update",
        url=url,
        original_url=url,
        published_at="2026-07-09T08:00:00+08:00",
        summary="工具增加了结构化输出能力。开发者可以用它构建更稳定的自动化流程。",
        raw_text="这是用于测试的完整正文。" * 100,
        reason="来自测试用的一手来源",
    )


def block_text(block):
    return " ".join(
        value.get("text_run", {}).get("content", "")
        for section in block.values()
        if isinstance(section, dict)
        for value in section.get("elements", [])
    )


def is_bold_text_block(block):
    if block.get("block_type") != 2:
        return False
    elements = block.get("text", {}).get("elements", [])
    return bool(
        elements
        and elements[0].get("text_run", {}).get("text_element_style", {}).get("bold") is True
    )


def test_rss_link_is_preserved(monkeypatch):
    link = "https://example.com/article?id=123&utm_source=rss&very_long=value"
    xml = f"""
    <rss><channel><item>
      <title>一个完整的 RSS 测试条目</title>
      <link>{link.replace('&', '&amp;')}</link>
      <description>{'足够长的摘要内容。' * 60}</description>
      <pubDate>Thu, 09 Jul 2026 01:00:00 GMT</pubDate>
    </item></channel></rss>
    """.encode()

    class Response:
        content = xml

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr("collectors.rss_collector.requests.get", lambda *args, **kwargs: Response())
    result = collect_rss(
        [{"name": "测试 RSS", "url": "https://example.com/feed.xml"}],
        lookback_days=3650,
    )
    assert result[0]["url"] == link
    assert result[0]["original_url"] == link


def test_manual_link_survives_fetch_failure(tmp_path, monkeypatch):
    link = "https://example.com/manual/path?" + "parameter=" + "x" * 500
    file_path = tmp_path / "manual_links.txt"
    file_path.write_text(link + "\n", encoding="utf-8")

    def fail(*args, **kwargs):
        raise requests.RequestException("模拟抓取失败")

    monkeypatch.setattr("collectors.manual_link_collector.fetch_public_page", fail)
    result = collect_manual_links(
        [{"name": "手动链接", "file": str(file_path)}],
        project_dir=tmp_path,
    )
    assert result[0]["url"] == link
    assert result[0]["original_url"] == link
    assert result[0]["fetch_success"] is False


def test_report_limit_never_truncates_long_url():
    link = "https://example.com/article?" + "&".join(f"key{i}={'x' * 80}" for i in range(30))
    report = generate_rule_based_report([make_item(link)], "2026-07-09")
    constrained = constrain_report_length(report, max_chars=300)
    assert link in constrained
    assert "原文链接：ht" not in constrained
    assert "内容已按字数上限压缩" not in constrained


def test_report_limit_preserves_all_category_headings():
    categories = "\n\n".join(
        f"### {index}. 分类 {index}\n" + "这是分类情报的完整趋势说明。" * 30
        for index in range(1, 8)
    )
    report = f"""# AI 前沿信息雷达｜2026-07-09

## 今日一句话
简短摘要。

## 分类情报

{categories}

## 明日关注方向
继续关注。
"""
    constrained = constrain_report_length(report, max_chars=200)
    for index in range(1, 8):
        assert f"### {index}. 分类 {index}" in constrained


def test_missing_ai_link_is_repaired():
    link = "https://example.com/full/article/path?token=abcdef1234567890"
    item = make_item(link)
    report = """# AI 前沿信息雷达｜2026-07-09

## 今日最值得关注的 5 条

### 1. 测试 AI 工具更新
- 来源：测试来源
- 原文链接：ht

## 深度解读

### 1. 测试 AI 工具更新
核心内容：模型输出漏掉了链接。
"""
    repaired, count = ensure_report_links(report, [item])
    assert repaired.count(link) == 2
    assert "原文链接：ht" not in repaired
    assert count == 2


def test_unmatched_translated_title_never_uses_positional_wrong_link():
    first = make_item("https://example.com/first", "First English Title")
    second = make_item("https://example.com/second", "Second English Title")
    report = """# AI 前沿信息雷达｜2026-07-09

## 今日最值得关注的 5 条

### 1. 与原始英文标题无法匹配的中文翻译标题
原文链接：
https://example.com/first
"""
    repaired, _ = ensure_report_links(report, [first, second])
    assert "https://example.com/first" in repaired
    assert "https://example.com/second" not in repaired


def test_bold_markdown_link_is_normalized_without_a_second_link():
    first = make_item("https://example.com/first", "第一个测试标题")
    second = make_item("https://example.com/second", "第二个测试标题")
    report = """# AI 前沿信息雷达｜2026-07-09

## 今日最值得关注的 5 条

### 1. 第一个测试标题
- **原文链接**：
  https://example.com/first

### 2. 第二个测试标题
- **原文链接**：
  https://example.com/second
"""
    repaired, count = ensure_report_links(report, [first, second])
    assert repaired.count("https://example.com/first") == 1
    assert repaired.count("https://example.com/second") == 1
    assert "**原文链接**" not in repaired
    assert count == 0


def test_feishu_uses_one_complete_url_block():
    link = "https://example.com/article?" + "query=" + "a" * 2500
    markdown = f"# 测试\n\n原文链接：\n{link}\n\n后续正文"
    blocks = markdown_to_feishu_blocks(markdown)
    texts = [block_text(block) for block in blocks]
    assert link in texts
    assert texts.count(link) == 1
    assert "ht" not in texts


def test_feishu_outline_only_uses_daily_title_heading():
    link = "https://example.com/gpt-live"
    markdown = f"""# AI 前沿信息雷达｜2026-07-09

## 今日一句话
今天最重要的是语音模型更新。

## 深度解读

### 1. OpenAI 推出 GPT-Live：新一代全双工语音模型
原文链接：
{link}

## 明日关注方向
继续关注实际使用反馈。
"""
    blocks = markdown_to_feishu_blocks(markdown)
    outline_blocks = [block for block in blocks if block.get("block_type") in {3, 4, 5}]

    assert len(outline_blocks) == 1
    assert outline_blocks[0]["block_type"] == 3
    assert block_text(outline_blocks[0]) == "AI 前沿信息雷达｜2026-07-09"
    assert not any(block.get("block_type") in {4, 5} for block in blocks)
    assert any(block_text(block) == "今日一句话" and is_bold_text_block(block) for block in blocks)
    assert any(block_text(block) == "深度解读" and is_bold_text_block(block) for block in blocks)
    assert any(
        block_text(block) == "1. OpenAI 推出 GPT-Live：新一代全双工语音模型"
        and is_bold_text_block(block)
        for block in blocks
    )
    assert link in [block_text(block) for block in blocks]


def test_without_api_key_stops_instead_of_degrading(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    item = make_item("https://example.com/no-api")
    with pytest.raises(RuntimeError, match="本次日报已终止"):
        generate_ai_report([item], "2026-07-09")


def test_api_failure_stops_instead_of_degrading(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_summarizer.time, "sleep", lambda *_: None)

    def fail(*args, **kwargs):
        raise requests.RequestException("模拟 API 故障")

    monkeypatch.setattr(ai_summarizer.requests, "post", fail)
    item = make_item("https://example.com/api-failure")
    with pytest.raises(RuntimeError, match="AI 翻译总结失败"):
        generate_ai_report([item], "2026-07-09")


def test_json_parser_accepts_unescaped_control_characters():
    parsed = ai_summarizer._parse_json_object('{"内容":"第一行\n第二行\t结束"}')
    assert parsed["内容"] == "第一行\n第二行\t结束"


def test_single_item_retries_when_model_format_is_invalid(monkeypatch):
    valid = {
        "中文标题": "测试工具发布结构化输出能力",
        "原始标题": "Test Tool Structured Output",
        "来源": "测试来源",
        "平台": "tool",
        "发布时间": "2026-07-09",
        "原文链接": "https://example.com/retry",
        "一句话总结": "这项更新增强了结构化输出能力，让自动化流程更容易获得稳定且可校验的结果。",
        "核心内容": [
            "工具新增了结构化输出能力，可以按照预先定义的字段返回结果。",
            "开发者可以减少手工解析文本的步骤，并更早发现缺失字段。",
            "实际使用时仍需检查接口限制、错误处理方式以及返回结果质量。",
        ],
        "为什么重要": "它能降低自动化流程因为输出格式变化而失败的概率。",
        "我可以怎么用": "先用一个小型测试任务定义字段，再验证异常输入和重试逻辑。",
        "适合谁关注": "需要构建 AI 自动化流程的初学者、开发者和产品人员。",
        "学习价值": "可以学习如何校验模型输出并为失败情况设计安全的处理方式。",
        "关键词": ["结构化输出", "自动化", "可靠性"],
    }
    responses = iter([
        '{"中文标题":"字段不完整"}',
        ai_summarizer.json.dumps(valid, ensure_ascii=False),
    ])
    monkeypatch.setattr(
        ai_summarizer,
        "_chat_completion",
        lambda *args, **kwargs: next(responses),
    )

    result = ai_summarizer._summarize_single_item(
        ai_summarizer._compact_item(make_item("https://example.com/retry"), 3000),
        {"model": "test"},
    )

    assert result["中文标题"] == valid["中文标题"]


def test_compact_item_only_truncates_body_not_urls():
    link = "https://example.com/very-long?" + "q=" + "z" * 2000
    item = make_item(link)
    compact = ai_summarizer._compact_item(item, 20)
    assert len(compact["raw_text"]) == 20
    assert compact["url"] == link
    assert compact["original_url"] == link


def test_arxiv_link_is_normalized_to_abs(monkeypatch):
    source_item = make_item("https://arxiv.org/pdf/2607.12345.pdf", "论文测试")
    monkeypatch.setattr(
        "collectors.arxiv_collector.collect_rss",
        lambda *args, **kwargs: [source_item],
    )
    result = collect_arxiv([{"url": "https://export.arxiv.org/rss/cs.AI"}])
    assert result[0]["url"] == "https://arxiv.org/abs/2607.12345"
    assert result[0]["original_url"] == "https://arxiv.org/abs/2607.12345"


def test_manual_item_is_prioritized_and_unknown_ai_url_is_removed():
    normal_items = [
        make_item(f"https://example.com/{index}", f"普通内容 {index}")
        for index in range(20)
    ]
    manual = make_item("https://example.com/manual", "手动收藏")
    manual["is_manual"] = True
    ranked = rank_content(normal_items + [manual], limit=15)
    assert ranked[0]["url"] == manual["url"]

    report = """# AI 前沿信息雷达｜2026-07-09
## 今日最值得关注的 5 条
### 1. 手动收藏
原文链接：
https://model-invented.example/hallucination
## 深度解读
### 1. 手动收藏
没有链接。
"""
    repaired, _ = ensure_report_links(report, [manual])
    assert "https://model-invented.example/hallucination" not in repaired
    assert repaired.count("https://example.com/manual") == 2


def test_ai_report_success_writes_to_feishu(tmp_path, monkeypatch):
    item = make_item("https://example.com/full-pipeline")

    class FakeClient:
        written_blocks = []

        @staticmethod
        def document_contains_text(_target):
            return False

        def append_blocks_to_document(self, blocks):
            self.written_blocks = blocks
            return {"code": 0, "data": {"children": blocks}}

    client = FakeClient()
    monkeypatch.setattr(main, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(main.FeishuClient, "from_env", lambda: client)
    monkeypatch.setattr(main, "load_sources_config", lambda: {"rss_sources": [{}]})
    monkeypatch.setattr(main, "collect_rss", lambda *args, **kwargs: [item])
    monkeypatch.setattr(main, "collect_github", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "collect_arxiv", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "collect_manual_links", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "collect_social", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "collect_web_sources", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        main,
        "generate_ai_report",
        lambda *args, **kwargs: (
            "# AI 前沿信息雷达｜2026-07-09\n\n"
            "## 今日 AI 总览\n\n中文总览。\n\n"
            "## 今日最重要的 5 条 AI 新闻\n\n"
            "### 中文标题\n\n原文链接：\nhttps://example.com/full-pipeline\n\n"
            "## 普通重要动态\n\n暂无。\n\n## 论文精选\n\n暂无。"
        ),
    )
    monkeypatch.setenv("AI_API_KEY", "模拟已配置")
    monkeypatch.setenv("AI_RADAR_FORCE_WRITE", "true")

    result = main.run_once()
    assert result["code"] == 0
    assert client.written_blocks
    assert any("https://example.com/full-pipeline" == block_text(block) for block in client.written_blocks)


def test_ai_failure_never_writes_to_feishu(tmp_path, monkeypatch):
    item = make_item("https://example.com/ai-failure")

    class FakeClient:
        write_calls = 0

        @staticmethod
        def document_contains_text(_target):
            return False

        def append_blocks_to_document(self, _blocks):
            self.write_calls += 1
            return {"code": 0}

    client = FakeClient()
    monkeypatch.setattr(main, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(main.FeishuClient, "from_env", lambda: client)
    monkeypatch.setattr(main, "load_sources_config", lambda: {})
    monkeypatch.setattr(main, "_collect_and_rank_content", lambda *args: [item])
    monkeypatch.setattr(
        main,
        "generate_ai_report",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("模拟 AI 翻译总结失败")
        ),
    )
    monkeypatch.setenv("AI_API_KEY", "模拟已配置")
    monkeypatch.setenv("AI_RADAR_FORCE_WRITE", "true")

    with pytest.raises(RuntimeError, match="AI 翻译总结失败"):
        main.run_once()

    assert client.write_calls == 0


def test_local_test_mode_only_writes_a_local_report(tmp_path, monkeypatch):
    item = make_item("https://example.com/local-test")
    monkeypatch.setattr(main, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(main, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(main, "_setup_logging", lambda: None)
    monkeypatch.setattr(main, "load_sources_config", lambda: {})
    monkeypatch.setattr(main, "_collect_and_rank_content", lambda *args: [item])
    monkeypatch.setattr(
        main,
        "generate_ai_report",
        lambda *args, **kwargs: (
            "# AI 前沿信息雷达｜2026-07-09\n\n"
            "## 今日 AI 总览\n\n中文总览。\n\n"
            "## 今日最重要的 5 条 AI 新闻\n\n"
            "### 中文标题\n\n原文链接：\nhttps://example.com/local-test\n\n"
            "## 普通重要动态\n\n暂无。\n\n## 论文精选\n\n暂无。"
        ),
    )
    monkeypatch.setattr(
        main.FeishuClient,
        "from_env",
        lambda: (_ for _ in ()).throw(AssertionError("本地测试不应初始化飞书客户端")),
    )
    monkeypatch.setenv("AI_RADAR_LIMIT", "1")

    result = main.run_local_test()

    assert result["local_test"] is True
    assert Path(result["output_path"]).exists()
    assert "https://example.com/local-test" in Path(result["output_path"]).read_text(encoding="utf-8")


def test_report_date_uses_asia_shanghai_timezone(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz == main.REPORT_TIMEZONE
            return cls(2026, 7, 10, 0, 5, tzinfo=tz)

    monkeypatch.setattr(main, "datetime", FixedDateTime)
    assert main._current_report_date() == "2026-07-10"


def test_report_plan_has_enough_featured_ordinary_and_papers():
    items = []
    for index in range(20):
        item = make_item(f"https://example.com/plan-{index}", f"计划内容 {index}")
        item["category"] = "paper" if 5 <= index < 9 else "industry_news"
        items.append(item)

    plan = plan_report_items(items)

    assert len(plan["featured"]) == 5
    assert 8 <= len(plan["ordinary"]) <= 12
    assert 3 <= len(plan["papers"]) <= 5
    assert not {id(item) for item in plan["ordinary"]} & {id(item) for item in plan["papers"]}
