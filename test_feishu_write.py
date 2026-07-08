from dotenv import load_dotenv

from feishu_client import FeishuClient


def main():
    """只测试飞书 Docx 写入能力，不抓取新闻。"""
    load_dotenv()

    client = FeishuClient.from_env()
    result = client.write_test_daily_report()

    children = result.get("data", {}).get("children", [])
    block_count = len(children) if isinstance(children, list) else "未知"

    print("飞书文档写入测试成功。")
    print(f"文档 ID：{client.document_id}")
    print(f"新增块数量：{block_count}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("测试写入失败。请根据下面的错误信息检查 .env 和飞书应用权限。")
        print(exc)
        raise
