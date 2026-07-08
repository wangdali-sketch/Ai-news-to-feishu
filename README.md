# Ai-news-to-feishu

这个项目用于每天抓取最新 AI 前沿新闻，并写入飞书 Docx 文档。

当前支持三种运行方式：

- 本地手动运行：在 Windows 终端运行 `python main.py`
- 本地自动运行：Windows 任务计划程序每天运行 `run_daily.bat`
- 云端自动运行：GitHub Actions 每天运行 `.github/workflows/daily.yml`

## 1. 当前是不是固定模板

不是。

正式入口 `main.py` 会调用 `news_fetcher.fetch_ai_news()`，它会通过 `requests` 访问 RSS/Atom 新闻源，读取最新标题、摘要、发布时间和原文链接。

固定模板只保留在 `test_feishu_write.py`，它只用于测试飞书写入权限，不用于每日新闻日报。

## 2. 项目文件说明

```text
main.py                         正式运行脚本：抓取 AI 新闻并写入飞书
feishu_client.py                飞书接口封装和飞书 Docx 内容块生成
news_fetcher.py                 新闻 RSS/Atom 抓取、清洗、去重和排序
news_sources.json               默认 AI 新闻源配置
test_feishu_write.py            最小飞书写入测试
run_daily.bat                   Windows 本地每日自动运行脚本
setup_daily_task.ps1            创建 Windows 每日计划任务
requirements.txt                Python 依赖
.env.example                    本地环境变量示例
.gitignore                      Git 忽略规则，防止上传 .env
.github/workflows/daily.yml     GitHub Actions 云端每日自动运行配置
README.md                       使用说明
```

## 3. 本地 .env 配置

本地运行时使用 `.env` 文件保存飞书配置。

第一次使用时复制示例文件：

```powershell
Copy-Item .env.example .env
```

然后打开 `.env`，填写：

```env
FEISHU_APP_ID=你的飞书自建应用 App ID
FEISHU_APP_SECRET=你的飞书自建应用 App Secret
FEISHU_DOCX_DOCUMENT_ID=你的飞书 Docx 文档 ID
AI_NEWS_LIMIT=8
AI_NEWS_LOOKBACK_DAYS=2
AI_NEWS_MAX_PER_SOURCE=3
AI_NEWS_SOURCES_FILE=news_sources.json
```

说明：

- `AI_NEWS_LIMIT`：每天最多写入几条新闻，默认 8 条。
- `AI_NEWS_LOOKBACK_DAYS`：抓取最近几天的新闻，默认最近 2 天。
- `AI_NEWS_MAX_PER_SOURCE`：单个新闻源优先最多选几条，默认 3 条，避免一个来源刷屏。
- `AI_NEWS_SOURCES_FILE`：新闻源配置文件，默认 `news_sources.json`。

注意：

- `.env` 只用于本地运行。
- 不要把 `.env` 上传到 GitHub。
- `.gitignore` 已经包含 `.env` 和 `.env.txt`。

## 4. 配置 AI 新闻源

默认新闻源在：

```text
news_sources.json
```

默认包含：

- Google News 中文 AI 搜索
- Google News 国际 AI 搜索
- OpenAI News
- Google AI Blog
- Hugging Face Blog
- NVIDIA AI Blog
- Microsoft AI Blog
- AWS Machine Learning Blog
- arXiv cs.AI

如果你想关闭某个新闻源，把它的 `enabled` 改成 `false`：

```json
{
  "name": "arXiv cs.AI",
  "type": "rss",
  "enabled": false,
  "url": "https://export.arxiv.org/rss/cs.AI"
}
```

如果你想新增 RSS 新闻源，在 `sources` 列表里加一项：

```json
{
  "name": "你的新闻源名称",
  "type": "rss",
  "enabled": true,
  "url": "https://example.com/feed.xml"
}
```

如果新闻源需要查询参数，可以这样写：

```json
{
  "name": "自定义搜索源",
  "type": "rss",
  "enabled": true,
  "url": "https://news.google.com/rss/search",
  "params": {
    "q": "AI OR OpenAI when:{lookback_days}d",
    "hl": "zh-CN",
    "gl": "CN",
    "ceid": "CN:zh-Hans"
  }
}
```

`{lookback_days}` 会自动替换成 `.env` 或 GitHub Variables 里的 `AI_NEWS_LOOKBACK_DAYS`。

## 5. 本地安装依赖

进入项目目录：

```powershell
cd D:\Ai-news-to-feishu
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 6. 本地手动运行

只测试飞书写入：

```powershell
python test_feishu_write.py
```

生成真实 AI 新闻日报并写入飞书：

```powershell
python main.py
```

## 7. 本地 Windows 每日自动运行

默认每天早上 08:00 自动运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_daily_task.ps1
```

改成每天 09:30 自动运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_daily_task.ps1 -Time 09:30
```

查看任务：

```powershell
schtasks /Query /TN "AiNewsToFeishuDaily"
```

手动触发一次：

```powershell
schtasks /Run /TN "AiNewsToFeishuDaily"
```

本地自动运行日志在：

```text
D:\Ai-news-to-feishu\logs
```

## 8. GitHub Actions 云端每日自动运行

云端运行不需要你的电脑开机。

GitHub Actions 会读取 GitHub Secrets，不会读取本地 `.env` 文件。

当前 workflow 文件是：

```text
.github/workflows/daily.yml
```

它包含这些步骤：

- checkout 代码
- setup-python
- `pip install -r requirements.txt`
- `python main.py`

## 9. 在 GitHub 仓库里添加 Secrets

打开仓库页面：

```text
https://github.com/wangdali-sketch/Ai-news-to-feishu
```

然后按下面步骤操作：

1. 点击 `Settings`
2. 点击左侧 `Secrets and variables`
3. 点击 `Actions`
4. 点击 `New repository secret`
5. 分别添加下面 3 个 Secret

需要添加的 Secret 名称和值：

```text
Name: FEISHU_APP_ID
Secret: 你的飞书自建应用 App ID
```

```text
Name: FEISHU_APP_SECRET
Secret: 你的飞书自建应用 App Secret
```

```text
Name: FEISHU_DOCX_DOCUMENT_ID
Secret: 你的飞书 Docx 文档 ID
```

## 10. 在 GitHub 仓库里添加可选 Variables

这一步不是必须的。

如果你想在 GitHub 网页上修改抓取条数或时间范围，可以添加 Variables：

1. 点击 `Settings`
2. 点击左侧 `Secrets and variables`
3. 点击 `Actions`
4. 点击 `Variables`
5. 点击 `New repository variable`

可选变量：

```text
Name: AI_NEWS_LIMIT
Value: 8
```

```text
Name: AI_NEWS_LOOKBACK_DAYS
Value: 2
```

```text
Name: AI_NEWS_MAX_PER_SOURCE
Value: 3
```

如果你想完全用 GitHub Variables 覆盖新闻源，可以添加：

```text
Name: AI_NEWS_SOURCES_JSON
Value: 一整段 JSON 新闻源配置
```

一般新手不需要设置 `AI_NEWS_SOURCES_JSON`，直接修改 `news_sources.json` 更简单。

## 11. 设置每天几点运行

GitHub Actions 的定时任务使用 UTC 时间，不是中国时间。

中国时间是 UTC+8。

换算方法：

```text
UTC 时间 = 中国时间 - 8 小时
```

例子：

```text
中国时间 08:00 = UTC 00:00
中国时间 09:00 = UTC 01:00
中国时间 18:30 = UTC 10:30
中国时间 00:30 = 前一天 UTC 16:30
```

当前配置是北京时间每天早上 08:00 运行：

```yaml
schedule:
  - cron: "0 0 * * *"
```

如果你想改成北京时间每天 09:30，改成：

```yaml
schedule:
  - cron: "30 1 * * *"
```

修改位置：

```text
.github/workflows/daily.yml
```

## 12. 手动触发一次 GitHub Actions 测试

步骤：

1. 打开 GitHub 仓库页面
2. 点击 `Actions`
3. 点击左侧 `每日 AI 新闻写入飞书`
4. 点击右侧 `Run workflow`
5. 选择 `main` 分支
6. 再点击绿色的 `Run workflow`

手动触发成功后，GitHub Actions 会执行 `python main.py`，并写入一次飞书文档。

注意：手动触发会真的写入飞书文档。

## 13. 如果 GitHub Actions 运行失败，在哪里看日志

查看日志步骤：

1. 打开 GitHub 仓库页面
2. 点击 `Actions`
3. 点击失败的运行记录，通常会显示红色叉号
4. 点击任务 `写入每日 AI 新闻日报`
5. 展开失败的步骤，看错误信息

常见失败位置：

- `安装依赖` 失败：检查 `requirements.txt`
- `运行 AI 新闻日报脚本` 失败：检查 GitHub Secrets、飞书权限、文档 ID、新闻源网络

如果看到类似：

```text
请先在 .env 文件中填写：FEISHU_APP_ID、FEISHU_APP_SECRET、FEISHU_DOCX_DOCUMENT_ID
```

说明 GitHub Secrets 没有配置好，或者 Secret 名称写错了。

如果看到类似：

```text
没有抓取到可用的 AI 新闻
```

说明所有新闻源都暂时不可用，或者 GitHub Actions 环境访问新闻源失败。

## 14. 成功后飞书文档里会看到什么

飞书文档里会新增一篇日报：

```text
每日 AI 前沿新闻日报
日期：自动获取今天日期
来源：已配置的公开 RSS/Atom 新闻源。程序会自动抓取标题、摘要和原文链接。
处理方式：按发布时间排序，过滤最近新闻，并按标题和链接去重。
提示：摘要来自原始新闻源，重要信息建议打开原文链接核对。
```

下面会有多条 AI 新闻，每条包含：

```text
标题
来源
发布时间
摘要
原文链接
```
