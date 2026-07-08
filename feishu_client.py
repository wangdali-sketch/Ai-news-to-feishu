import os
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List

import requests


class FeishuApiError(RuntimeError):
    """飞书接口调用失败时抛出的错误。"""


class FeishuClient:
    """飞书自建应用客户端。"""

    BASE_URL = "https://open.feishu.cn"

    def __init__(self, app_id: str, app_secret: str, document_id: str, timeout: int = 20):
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self.document_id = document_id.strip()
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        """从 .env 或系统环境变量读取飞书配置。"""
        values = {
            "FEISHU_APP_ID": os.getenv("FEISHU_APP_ID", "").strip(),
            "FEISHU_APP_SECRET": os.getenv("FEISHU_APP_SECRET", "").strip(),
            "FEISHU_DOCX_DOCUMENT_ID": os.getenv("FEISHU_DOCX_DOCUMENT_ID", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError("请先在 .env 文件中填写：" + "、".join(missing))

        return cls(
            app_id=values["FEISHU_APP_ID"],
            app_secret=values["FEISHU_APP_SECRET"],
            document_id=values["FEISHU_DOCX_DOCUMENT_ID"],
        )

    def get_tenant_access_token(self) -> str:
        """使用 APP_ID 和 APP_SECRET 获取 tenant_access_token。"""
        url = f"{self.BASE_URL}/open-apis/auth/v3/tenant_access_token/internal"
        response = requests.post(
            url,
            json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            timeout=self.timeout,
        )
        payload = self._parse_response(response)

        token = payload.get("tenant_access_token")
        if not token:
            raise FeishuApiError("飞书返回中没有 tenant_access_token，请检查 APP_ID 和 APP_SECRET。")

        return token

    def append_blocks_to_document(self, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """向指定飞书 Docx 文档末尾追加内容块。"""
        token = self.get_tenant_access_token()

        # 飞书 Docx 文档的根 block_id 通常就是 document_id。
        parent_block_id = self.document_id
        url = (
            f"{self.BASE_URL}/open-apis/docx/v1/documents/"
            f"{self.document_id}/blocks/{parent_block_id}/children"
        )

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            params={
                # -1 表示基于最新文档版本写入。
                "document_revision_id": -1,
                # 避免网络重试时重复创建相同请求。
                "client_token": str(uuid.uuid4()),
            },
            json={
                # -1 表示追加到父块末尾。
                "index": -1,
                "children": blocks,
            },
            timeout=self.timeout,
        )
        return self._parse_response(response)

    def write_test_daily_report(self) -> Dict[str, Any]:
        """生成测试日报内容，并写入飞书 Docx 文档。"""
        today = datetime.now().strftime("%Y-%m-%d")
        blocks = build_test_daily_report_blocks(today)
        return self.append_blocks_to_document(blocks)

    @staticmethod
    def _parse_response(response: requests.Response) -> Dict[str, Any]:
        """解析飞书接口响应，并把错误信息转换成更容易理解的中文。"""
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuApiError(
                f"飞书接口没有返回 JSON。HTTP 状态码：{response.status_code}，响应内容：{response.text}"
            ) from exc

        if response.status_code >= 400:
            raise FeishuApiError(
                f"飞书接口 HTTP 请求失败。HTTP 状态码：{response.status_code}，响应内容：{payload}"
            )

        code = payload.get("code")
        if code != 0:
            raise FeishuApiError(
                f"飞书接口返回错误。code={code}，msg={payload.get('msg')}，完整响应：{payload}"
            )

        return payload


def build_test_daily_report_blocks(today: str) -> List[Dict[str, Any]]:
    """把测试日报转换成飞书 Docx API 需要的块结构。"""
    return [
        build_heading1_block("今日 AI 日报测试"),
        build_text_block(f"日期：{today}"),
        build_text_block("这是一条来自 ai-news-to-feishu 项目的测试内容。"),
        build_text_block("如果你能看到这段话，说明飞书文档写入成功。"),
    ]


def build_ai_news_report_blocks(report_date: str, news_items: Iterable[Any]) -> List[Dict[str, Any]]:
    """把 AI 新闻列表转换成飞书 Docx API 需要的块结构。"""
    blocks = [
        build_heading1_block("每日 AI 新闻日报"),
        build_text_block(f"日期：{report_date}"),
        build_text_block("来源：公开新闻 RSS。内容由程序自动抓取标题、摘要和原文链接生成。"),
        build_text_block("提示：新闻摘要来自新闻源本身，重要信息建议打开链接核对原文。"),
    ]

    for index, item in enumerate(news_items, start=1):
        title = _get_item_value(item, "title")
        source = _get_item_value(item, "source") or "未知来源"
        published = _get_item_value(item, "published_text") or "未知时间"
        summary = _get_item_value(item, "summary") or "暂无摘要。"
        link = _get_item_value(item, "link")

        blocks.extend(
            [
                build_text_block(f"{index}. {title}"),
                build_text_block(f"来源：{source}｜发布时间：{published}"),
                build_text_block(f"摘要：{summary}"),
                build_text_block(f"链接：{link}"),
            ]
        )

    return blocks


def build_heading1_block(content: str) -> Dict[str, Any]:
    """创建一级标题块。"""
    return {
        "block_type": 3,
        "heading1": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {},
        },
    }


def build_text_block(content: str) -> Dict[str, Any]:
    """创建普通文本块。"""
    return {
        "block_type": 2,
        "text": {
            "elements": [
                {
                    "text_run": {
                        "content": content,
                        "text_element_style": {},
                    }
                }
            ],
            "style": {},
        },
    }


def _get_item_value(item: Any, key: str) -> str:
    """兼容对象和字典两种新闻数据格式。"""
    if isinstance(item, dict):
        return str(item.get(key, "")).strip()
    return str(getattr(item, key, "")).strip()
