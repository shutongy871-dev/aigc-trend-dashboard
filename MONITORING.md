每日采集仍由 `.github/workflows/deploy.yml` 在北京时间 09:05 定时触发，默认采集近 90 天。
`.github/workflows/monitor.yml` 单独监测，不调用采集、翻译或模型服务。

Builder 观点另由 `.github/workflows/builders.yml` 在北京时间 15:17 定时刷新，
比 Follow Builders 上游计划更新时间（14:17）晚一小时。该任务复用部署工作流，
仅下载公开 `feed-x.json` 并重新渲染页面，不重新采集项目、不调用翻译或大模型。
上午完整流程也会读取这份内容源。两条发布共用 `pages` 并发组与归档冲突保护。
GitHub 调度可能延迟，15:17 不保证上游已经更新，实际来源更新时间记录在
`output/builder_feed.json` 的 `generated_at` 字段，旧快照会在页面提示。

本地预览：

```bash
python3 builder_feed.py
python3 render_dashboard.py --data output/aigc_data.json --out site/index.html
python3 -m http.server 8000 --directory site
# 打开 http://localhost:8000/#builders
```

快照保存在 `output/builder_feed.json`，包含原文、作者自述、原帖链接、发帖时间、
来源更新时间、成功获取时间与互动量。页面以“项目发现 / HN 热议 / Builder 观点”
作为独立内容入口，项目分类仅在项目发现中显示；Builder 不再展示顶部介绍大卡片。
日期筛选按**北京时间发帖日期**，与每条推文时间一致；下拉仅列出当前快照已有日期，
可与作者、搜索、短帖过滤组合，不提供尚未保存的历史数据。
链接必须匹配来源作者与推文 ID；重复 ID 去重。
只保留最新快照，不积累历史；“隐藏短帖”仅按移除链接与 @提及后的正文不足 60 字符判断，
不是 AI 相关性或观点质量筛选。默认按赞 + 转发 + 回复排序，数字为上游采集时快照。
展示来源名单归属于 Zara Zhang / Follow Builders，原文属于各自作者，
引用推文、图片和外链语境通过原帖查看；本版不生成摘要或中文翻译。

上游下载或校验失败时保留上次成功快照，页面显示更新异常，Actions 给出 warning；
首次失败显示空态。合法的空内容源会清空旧推文，超过 36 小时未更新会显示旧快照提示。
当前每日 Issue 监测仍只覆盖上午完整流程，**不覆盖下午 Builder 专项任务**；
专项任务查看 Actions → 每日刷新 Builder 观点，失败/部分内容也请检查日志与页面提示。
手动刷新可运行专项工作流，或在原部署工作流勾选 `builders_only`。

- 每小时北京时间 :35 巡检；定时采集任务创建、开始、结束时也触发监测。
- 北京时间 09:35 仍无定时任务，或已创建但 build 仍在排队，标记异常。
- 从 build 实际开始算起超过 2 小时未完成，标记超时；不会终止采集。
- 失败、取消或整个流程为绿色但 Pages 部署被跳过，都标记异常。
- build 和 deploy 都成功才标记成功。页面数据完整性与 Vercel 发布状态不在此监测范围内。

在仓库 Issues 查找标题 `[每日任务监测]`：每天一条，记录创建时间、
实际启动时间、延迟、结果和任务链接。运行中或异常时保持打开，成功后自动关闭，
可在 Closed Issues 查看成功历史。重复巡检只更新同一条，不新增重复告警。
晚启动但之后成功的记录会保留延迟分钟数。

监测 Actions 的 Summary 同时展示当天和前一天的状态；检查前一天是为了覆盖跨午夜的执行。
从 2026-10-23 开始记录，启用前不补发告警。手动和 push 部署不代替当天 schedule 的成功。
重新运行当天失败的定时任务，成功后可以关闭该日期的异常记录。
若历史异常超过一天仍未解决，旧 Issue 保留，需人工处理。

异常会让监测 Actions 失败，采集任务继续独立运行。通知通过 GitHub 自身的 Actions
通知设置以及仓库 Watch / Issues 订阅管理；这里没有配置额外的邮件或飞书推送。
GitHub 原生调度可能延迟或丢弃任务，监测自身也可能延迟或失败，
因此这是状态监测，不能保证每天 09:35 准时报警。

手动检查：Actions → 每日任务启动与成功监测 → Run workflow。
本地只读检查（需已登录 gh）：

```bash
GITHUB_REPOSITORY=shutongy871-dev/aigc-trend-dashboard \
MONITOR_SINCE=2026-10-23 python3 monitor_daily.py --dry-run
```

返回码 0 表示所检查日期没有异常；1 表示检测到异常。
API 或权限错误也会使命令失败，具体原因在 Actions 日志中。
