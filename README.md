# Ai-news-to-feishu

这个项目用于每天抓取 AI 新闻，并写入飞书 Docx 文档。

当前支持三种运行方式：

- 本地手动运行：你在 Windows 终端运行 `python main.py`
- 本地自动运行：Windows 任务计划程序每天运行 `run_daily.bat`
- 云端自动运行：GitHub Actions 每天运行 `.github/workflows/daily.yml`

## 1. 项目文件说明

```text
main.py                         正式运行脚本：抓取 AI 新闻并写入飞书
feishu_client.py                飞书接口封装
news_fetcher.py                 新闻 RSS 抓取和清洗
test_feishu_write.py            最小飞书写入测试
run_daily.bat                   Windows 本地每日自动运行脚本
setup_daily_task.ps1            创建 Windows 每日计划任务
requirements.txt                Python 依赖
.env.example                    本地环境变量示例
.gitignore                      Git 忽略规则，防止上传 .env
.github/workflows/daily.yml     GitHub Actions 云端每日自动运行配置
README.md                       使用说明
```

## 2. 本地 .env 配置

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
```

注意：

- `.env` 只用于本地运行。
- 不要把 `.env` 上传到 GitHub。
- `.gitignore` 已经包含 `.env` 和 `.env.txt`。

## 3. 本地安装依赖

进入项目目录：

```powershell
cd D:\Ai-news-to-feishu
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 4. 本地手动运行

只测试飞书写入：

```powershell
python test_feishu_write.py
```

生成真实 AI 新闻日报并写入飞书：

```powershell
python main.py
```

## 5. 本地 Windows 每日自动运行

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

## 6. GitHub Actions 云端每日自动运行

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

## 7. 把项目上传到 GitHub

先在 GitHub 网页创建一个新仓库，例如：

```text
Ai-news-to-feishu
```

然后在本地 Windows 终端运行下面命令。

如果当前目录还不是 Git 仓库：

```powershell
cd D:\Ai-news-to-feishu
git init
git branch -M main
```

检查 `.env` 不会被提交：

```powershell
git status --ignored
```

你应该看到 `.env` 在 ignored files 里面。

添加并提交代码：

```powershell
git add .
git commit -m "添加飞书 AI 新闻日报自动运行"
```

绑定你的 GitHub 仓库地址。把下面地址换成你自己的仓库地址：

```powershell
git remote add origin https://github.com/你的用户名/Ai-news-to-feishu.git
```

推送到 GitHub：

```powershell
git push -u origin main
```

如果你已经有 Git 仓库，只需要执行：

```powershell
git add .
git commit -m "添加 GitHub Actions 每日自动运行"
git push
```

## 8. 在 GitHub 仓库里添加 Secrets

打开你的 GitHub 仓库页面，然后按下面步骤操作：

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

注意：

- Secret 名称必须完全一致。
- 不要多写空格。
- 不需要把 `.env` 上传到 GitHub。

## 9. 设置每天几点运行

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

改完后提交并推送：

```powershell
git add .github/workflows/daily.yml README.md
git commit -m "修改 GitHub Actions 运行时间"
git push
```

说明：

- GitHub Actions 定时任务可能会有几分钟延迟。
- 如果 GitHub 当时很忙，运行时间不一定精确到分钟。

## 10. 手动触发一次 GitHub Actions 测试

上传代码并添加 Secrets 后，可以手动运行一次测试。

步骤：

1. 打开 GitHub 仓库页面
2. 点击 `Actions`
3. 点击左侧 `每日 AI 新闻写入飞书`
4. 点击右侧 `Run workflow`
5. 选择 `main` 分支
6. 再点击绿色的 `Run workflow`

手动触发成功后，GitHub Actions 会执行 `python main.py`，并写入一次飞书文档。

注意：手动触发会真的写入飞书文档。

## 11. 如果 GitHub Actions 运行失败，在哪里看日志

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
飞书接口返回错误
permission
forbidden
access denied
```

说明飞书应用可能没有文档权限，或者目标文档没有授权给应用。

如果看到类似：

```text
没有抓取到可用的 AI 新闻
```

说明新闻源暂时不可用，或者 GitHub Actions 环境访问新闻源失败。

## 12. 成功后飞书文档里会看到什么

飞书文档里会新增一篇日报：

```text
每日 AI 新闻日报
日期：自动获取今天日期
来源：公开新闻 RSS。内容由程序自动抓取标题、摘要和原文链接生成。
提示：新闻摘要来自新闻源本身，重要信息建议打开链接核对原文。
```

下面会有多条 AI 新闻，每条包含：

```text
标题
来源
发布时间
摘要
链接
```
