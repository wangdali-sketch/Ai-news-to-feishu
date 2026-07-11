# AI 前沿信息雷达

这个项目是“AI 前沿信息雷达”，不是普通新闻标题列表。它每天收集公开内容，筛选高价值信息，先逐条深度提炼，再生成可直接阅读的中文日报，最后追加到飞书 Docx 文档。

它不再只抓“新闻”，还支持官方博客、arXiv 论文、GitHub 热门项目、Hacker News、Reddit RSS、公开网页、行业报告、教程，以及用户手动保存的公众号、抖音、B站、小红书和 X 链接。

## 一、运行流程

程序执行 `python main.py` 后会依次完成：

1. 读取 `config/sources.yml`。
2. 采集 RSS、GitHub Trending、arXiv、公开网页和手动链接。
3. 把所有内容转换成统一字段。
4. 按链接和相似标题去重，并过滤历史已写入链接。
5. 按来源可信度、前沿程度、学习价值、行业影响等维度打分。
6. 选出 15～25 条内容，默认 20 条。
7. 有 `AI_API_KEY` 时，先逐条生成结构化深度摘要，再生成全局日报。
8. 自动校验并补回“重点关注”和“深度解读”中的原文链接。
9. 没有 API 密钥或全局生成失败时，自动生成规则版日报。
10. 写入飞书 Docx，并记录 `logs/daily.log`。
11. 写入最后的完成标记，防止同一天重复写入。

## 二、项目结构

```text
collectors/
  rss_collector.py          RSS/Atom 采集
  web_collector.py          无需登录的公开网页采集
  github_collector.py       GitHub Trending AI 项目采集
  arxiv_collector.py        arXiv 官方 RSS 采集
  manual_link_collector.py  用户手动链接采集
  social_collector.py       RSSHub/官方 RSS 社媒来源采集
config/sources.yml          所有来源配置
data/manual_links.txt       用户每天手动收藏的公开链接
ai_summarizer.py            大模型日报生成、重试和降级
content_schema.py           统一内容字段和分类
content_deduper.py          当前批次及历史链接去重
content_ranker.py           内容价值打分和排序
report_generator.py         规则版日报和飞书块转换
feishu_client.py            飞书 Docx API
main.py                     正式入口
run_daily.bat               Windows 每日运行脚本
.github/workflows/daily.yml GitHub Actions 定时运行
```

## 三、来源支持和限制

| 来源 | 接入方式 | 稳定性 | 说明 |
|---|---|---:|---|
| 新闻、官方博客、教程 | RSS/Atom | 较稳定 | 推荐优先使用 |
| arXiv | 官方 RSS | 较稳定 | 当前默认启用 `cs.AI` |
| GitHub Trending | 公开网页 | 较稳定 | 支持 `GITHUB_TOKEN`；页面结构改变时可能需要更新选择器 |
| Hacker News | HNRSS | 较稳定 | 默认启用 AI 查询 |
| Reddit | 公开 RSS | 一般 | 云服务器可能被限流，默认关闭 |
| 行业报告、工具更新页 | 公开网页 | 一般 | 只读取无需登录的可见文本 |
| 公众号 | 手动公开链接、RSSHub | 受限 | 不绕过微信限制 |
| 抖音、小红书、X | 手动公开链接、官方 API、搜索 API、RSSHub | 受限 | 页面经常要求登录或验证码 |
| B站 | 手动公开链接、RSSHub | 一般 | 只能读取页面公开可见信息 |

核心稳定来源是 RSS、AI 公司官方博客、arXiv 官方 RSS 和 GitHub 公开页面。公众号、抖音、小红书、X、B站受平台限制，当前优先通过 `data/manual_links.txt` 的公开分享链接处理，也可以使用合规的官方 API 或 RSSHub。

程序不会绕过登录、付费墙、验证码、反爬限制或平台权限。受限链接抓取失败时，仍会完整保留原链接，并标注“原文抓取失败，仅基于标题和摘要整理”。

Google News 无法解析出源站地址时，会完整保留 Google News 链接；arXiv 会统一为 `https://arxiv.org/abs/...`；GitHub 会保留仓库首页地址。看到“原文链接：未获取到”，表示源数据没有提供链接且程序也无法获取，不代表程序报错。

## 四、安装

打开 PowerShell，进入项目目录：

```powershell
cd D:\Ai-news-to-feishu
py -m pip install -r requirements.txt
```

项目不会自动创建真实 `.env`。第一次使用时，你需要自己复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

## 五、配置飞书

在 `.env` 填写：

```env
FEISHU_APP_ID=你的飞书应用ID
FEISHU_APP_SECRET=你的飞书应用密钥
FEISHU_DOCX_DOCUMENT_ID=你的飞书文档ID
# 兼容名称，已有上面一项时不需要填写：
FEISHU_DOCUMENT_ID=

AI_PROVIDER=deepseek
AI_API_KEY=你的DeepSeek API密钥
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat

GITHUB_TOKEN=
RSSHUB_BASE_URL=

MAX_ITEMS_FOR_AI=10
MAX_TEXT_PER_ITEM=3000
MAX_REPORT_CHARS=12000

AI_RADAR_LIMIT=20
AI_RADAR_LOOKBACK_DAYS=2
AI_RADAR_MAX_PER_SOURCE=4
AI_RADAR_SOURCES_FILE=config/sources.yml
AI_RADAR_FORCE_WRITE=false
```

已有飞书配置的用户不需要重新配置飞书应用，也不需要更换文档。请保留原来的：

```env
FEISHU_APP_ID=原来的值
FEISHU_APP_SECRET=原来的值
FEISHU_DOCX_DOCUMENT_ID=原来的值
```

然后只需在现有 `.env` 末尾新增 `AI_API_KEY`、`AI_BASE_URL`、`AI_MODEL` 等大模型配置。

文档 ID 的读取顺序是：

1. 优先读取 `FEISHU_DOCX_DOCUMENT_ID`。
2. 如果它为空，再读取兼容变量 `FEISHU_DOCUMENT_ID`。
3. 两个变量只需填写一个；已有用户建议继续使用原来的 `FEISHU_DOCX_DOCUMENT_ID`。

飞书应用需要能够读取并编辑目标 Docx 文档。读取权限用于检查当天是否已经写入；如果读取检查失败，程序会记录警告并继续依靠本地状态防重复。

不要把真实密钥写进 Python、YAML 或 GitHub 仓库。`.gitignore` 已忽略 `.env`。

### 飞书左侧大纲说明

飞书左侧大纲来自 Docx 文档里的 Heading 标题块。为了避免目录过乱，当前项目只把每日报告的大标题写成真正的 Heading：

```text
AI 前沿信息雷达｜YYYY-MM-DD
```

正文中的小标题，例如“今日一句话”“今日总览”“今日最值得关注的 5 条”“深度解读”“分类情报”“今日学习建议”“今日收藏建议”“明日关注方向”，都会写成普通段落里的加粗文本。深度解读和分类情报里的条目标题也同样使用普通加粗文本，不会进入飞书左侧大纲。

只测试飞书写入：

```powershell
python test_feishu_write.py
```

## 六、配置 DeepSeek 或其他兼容 API

在 `.env` 填写：

```env
AI_PROVIDER=deepseek
AI_API_KEY=你的API密钥
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat
```

接口需要兼容 OpenAI 的 `POST /chat/completions` 格式。

- `AI_API_KEY` 没填：直接生成规则版日报，日志会提示“未配置 AI_API_KEY，已使用规则版摘要”。
- 单条提炼失败：只把这一条降级为规则提炼，其余条目继续使用 AI。
- 全局日报调用失败：自动退回规则版日报，继续写入飞书。
- 模型名称必须是你的服务商实际提供的名称；示例名称不可用时，请按服务商控制台修改。

推荐配置：

```env
MAX_ITEMS_FOR_AI=10
MAX_TEXT_PER_ITEM=3000
MAX_REPORT_CHARS=12000
```

省钱配置：

```env
MAX_ITEMS_FOR_AI=6
MAX_TEXT_PER_ITEM=1500
MAX_REPORT_CHARS=8000
```

深度版配置：

```env
MAX_ITEMS_FOR_AI=12
MAX_TEXT_PER_ITEM=4000
MAX_REPORT_CHARS=15000
```

如果日报太短，优先调大 `MAX_REPORT_CHARS` 和 `MAX_TEXT_PER_ITEM`。长度控制只会精简分类情报等非核心说明；“今日一句话”“今日总览”“今日最值得关注”“深度解读”“今日学习建议”和完整链接不会被硬截断。必要时最终字符数可以略高于配置上限，原因会写入日志，不会在日报正文显示“内容已按字数上限压缩”。

日志会记录总内容数、去重后数量、进入 AI 的数量、URL 完整性、逐条抓取状态、API 调用与降级、链接修复、字数压缩，以及飞书写入结果。

## 七、添加 RSS 来源

编辑 `config/sources.yml`，在 `rss_sources` 下增加：

```yaml
rss_sources:
  - name: 我的 AI 来源
    url: https://example.com/feed.xml
    category: official_blog
```

常用 `category`：

```text
model_release, ai_agent, multimodal, ai_coding, open_source,
paper, tool_update, industry_news, tutorial, opinion,
business, video, social_discussion
```

`official_blog` 可以作为 RSS 来源提示使用，程序会把平台标记成官方博客并自动判断内容分类。

## 八、添加公众号、抖音、B站、小红书和 X 链接

打开 `data/manual_links.txt`，每行粘贴一个公开链接：

```text
https://mp.weixin.qq.com/真实文章地址
https://www.douyin.com/video/真实视频地址
https://www.bilibili.com/video/真实视频地址
https://x.com/账号/status/真实状态地址
https://www.xiaohongshu.com/explore/真实内容地址
https://example.com/公开网页地址
```

注意：

- 不要在链接前后添加说明文字。
- `#` 开头的行是注释，不会被采集。
- 页面必须是公开可访问的；程序不会尝试登录。
- 手动链接会原样保存，即使正文抓取失败也会进入候选内容；历史过滤不会静默丢弃用户明确加入的手动链接。

如果有 RSSHub 地址，可以在 `social_sources` 中启用：

```yaml
social_sources:
  - name: 我的 B站关注源
    type: bilibili
    enabled: true
    rss_url: https://你的-rsshub-地址/bilibili/user/video/用户ID
```

也可以在 `.env` 填写 `RSSHUB_BASE_URL`，然后在配置中使用相对路径：

```env
RSSHUB_BASE_URL=https://你的-rsshub-地址
```

```yaml
rss_url: /bilibili/user/video/用户ID
```

## 九、添加行业报告、教程或工具页面

在 `config/sources.yml` 的 `web_sources` 中添加无需登录的公开页面：

```yaml
web_sources:
  - name: 某 AI 工具更新页
    url: https://example.com/ai/changelog
    platform: tool
    category: tool_update
```

## 十、手动运行和日志

运行一次正式日报：

```powershell
py main.py
```

持续日志位于：

```text
logs/daily.log
```

Windows 任务脚本还会生成带运行时间的日志：

```text
logs/daily_YYYY-MM-DD_HH-mm-ss.log
```

查看最近 80 行：

```powershell
Get-Content .\logs\daily.log -Tail 80 -Encoding UTF8
```

## 十一、GitHub Actions 和 Secrets

打开 GitHub 仓库的 `Settings` → `Secrets and variables` → `Actions`。

添加以下 Repository secrets。除飞书密钥和 `AI_API_KEY` 外，其余项目也按本项目工作流要求放在 Secrets 中：

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_DOCX_DOCUMENT_ID
FEISHU_DOCUMENT_ID
AI_PROVIDER
AI_API_KEY
AI_BASE_URL
AI_MODEL
GITHUB_TOKEN
RSSHUB_BASE_URL
MAX_ITEMS_FOR_AI
MAX_TEXT_PER_ITEM
MAX_REPORT_CHARS
```

`AI_API_KEY` 可以不添加，此时云端使用规则版日报。

飞书文档 ID 的两个 Secret 也是兼容关系。已有仓库继续保留 `FEISHU_DOCX_DOCUMENT_ID` 即可，不需要新增 `FEISHU_DOCUMENT_ID`；只有原来使用兼容名称时才配置后者。

建议值：

```text
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat
MAX_ITEMS_FOR_AI=10
MAX_TEXT_PER_ITEM=3000
MAX_REPORT_CHARS=12000
```

GitHub Actions 自带 `GITHUB_TOKEN`，工作流会直接使用；通常不需要另外创建同名 Token。只有使用其他 GitHub 令牌时才需要调整配置。

下面这些运行参数仍使用可选 Repository variables：

```text
AI_RADAR_LIMIT=20
AI_RADAR_LOOKBACK_DAYS=2
AI_RADAR_MAX_PER_SOURCE=4
```

工作流保留了 `workflow_dispatch`，可以在仓库 `Actions` 页面手动点 `Run workflow` 测试。

项目只保留 GitHub Actions 的每日自动写入。工作流在 `09:05 UTC` 运行，即北京时间每天 17:05。中国时间等于 UTC 时间加 8 小时，例如：

```text
UTC 09:05 = 中国时间 17:05
```

## 十二、调整日报分类

有两种方法：

1. 在 `config/sources.yml` 为来源设置 `category`。
2. 修改 `content_schema.py` 中 `detect_category()` 的关键词规则。

飞书日报的七个分类栏目定义在 `report_generator.py` 的 `CATEGORY_SECTIONS`。

## 十四、去重和同一天防重复

程序有三层保护：

1. 当前采集批次：按规范化链接和相似标题去重。
2. 跨天内容：成功写入后把链接记录到 `data/seen_items.json`。
3. 同一天日报：本地记录 `data/last_successful_run.json`，同时在飞书文档末尾写入 `AI_RADAR_WRITE_COMPLETED:日期`。

GitHub Actions 每次使用新机器，本地历史文件不会保留，因此云端主要依靠飞书文档中的完成标记防止同一天重复写入。

如果你明确需要同一天再次写入，在 `.env` 临时设置：

```env
AI_RADAR_FORCE_WRITE=true
```

写完后应改回 `false`。

## 十五、抓取失败排查

按这个顺序检查：

1. 运行 `Get-Content .\logs\daily.log -Tail 80 -Encoding UTF8` 查看具体来源和错误。
2. 把失败 URL 粘贴到浏览器，确认它无需登录就能打开。
3. 检查 `config/sources.yml` 缩进；YAML 必须使用空格，不能使用 Tab。
4. 如果返回 `403`、验证码或登录页，不要尝试绕过；改用官方 API、RSSHub、搜索 API 或手动链接。
5. GitHub Trending 没有结果时，可能是当天热门 Python 项目没有命中 AI 关键词。
6. Reddit 或社媒在 GitHub Actions 中失败时，改用可靠的 RSSHub 实例或官方 API。
7. 大模型失败不会阻止写入；检查 `AI_BASE_URL`、`AI_MODEL` 和 API 余额。
8. 飞书失败时，检查应用权限、文档 ID，以及文档是否已授权给该应用。

如果飞书中的日报仍然主要是标题和链接，先在 `logs/daily.log` 搜索“是否调用 DeepSeek API”和“是否发生降级”，然后检查：

```text
AI_API_KEY
AI_BASE_URL
AI_MODEL
```

如果飞书写入失败，优先检查飞书应用是否有目标文档的读取、编辑权限，以及 `FEISHU_DOCX_DOCUMENT_ID` 是否正确。

## 十六、测试和链接排查

安装依赖后运行全部本地测试：

```powershell
py -m pytest -q
```

确认飞书链接完整的方法：

1. 在 `data/manual_links.txt` 放入一条较长的测试链接。
2. 临时设置 `AI_RADAR_FORCE_WRITE=true`，运行 `py main.py`。
3. 在飞书中确认“原文链接：”下一行显示完整 URL，并且可以点击或复制。
4. 完成后把 `AI_RADAR_FORCE_WRITE` 改回 `false`。

如果仍看到“内容已按字数上限压缩”，说明正在运行旧代码；当前实现不会把这句话写入日报。请检查实际运行目录、GitHub Actions 使用的提交，并搜索 `report_generator.py` 中是否还有旧的硬截断逻辑。

如果仍有链接缺失，请在 `logs/daily.log` 中重点查看：

- `有 URL 的内容数` 和 `缺失 URL 的内容数`
- `被修复补回链接的条目数`
- `是否发现链接被截断`
- 每条 `抓取状态`
- `飞书写入是否成功`
