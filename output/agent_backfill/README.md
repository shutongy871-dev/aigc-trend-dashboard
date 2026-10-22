# TRAE 存量回填

当前 `output/aigc_data.json` 的 982 个积压项目已由 TRAE 会话助手逐项阅读 README 证据并编写中文解读，未调用外部模型 API。

- 1,014 个项目，1,013 个有效解读（原有 31 个保持不变，新增 982 个）。
- 1,009 条中文简介；另 5 个项目没有原始简介，不补造译文。
- 218 条简介由会话助手翻译或修正；全部原始 `description` 保留。
- `jev-chat/jev-chat-jarvis` 缺少 README 证据，保留 `insufficient_evidence`。

在项目根目录运行以下命令，直接从回填数据库生成部署入口：

```sh
python3 render_dashboard.py --data output/aigc_data.json --out site/index.html
```

这一步不重新采集，不调用翻译或模型，也不会把当前 90 天样本改成默认 30 天窗口。随后沿用现有部署方式发布。

让 GitHub 后续自动任务复用这些结果，需要把 `output/aigc_data.json`、`project_discovery.py`、`aigc_trend_brief.py` 和 `render_dashboard.py` 的本次改动同步到仓库。只在本机回填不会自动改变 GitHub 的数据库。本次没有提交、推送或部署。

缓存规则：

- 原简介未变且有有效翻译缓存：直接复用。
- README 证据、解读提示版本未变且学习卡通过校验：直接复用，切换执行模型不会重做。
- 原简介、证据或提示版本改变，或结果无效：重新进入对应待处理流程。
- 每次最多尝试 90 个项目，不代表保证成功 90 个。重试、资料更新和超过上限的新增仍可能排队。
- 跨项目机制聚类有自己的缓存和模型调用，区别于逐项目解读额度。

`batch-001.json` 至 `batch-082.json` 保存逐项证据关联解读，`translations.json` 保存原文匹配的译文修正，`progress.json` 保存完成数量。`agent_backfill.py` 只负责校验和合并，不会生成语义内容。

验证：35 个 Python 测试通过；完整数据重新走逐项目解读和翻译流程时，两类 API 调用均为 0；看板可从全部 1,014 个项目生成。
