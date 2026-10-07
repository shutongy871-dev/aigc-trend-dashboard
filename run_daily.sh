#!/usr/bin/env bash
# 每日流水线：采集三源数据（GitHub/HN/HF）→ 渲染自包含看板
# 被 GitHub Actions 与本地手动运行共用，保证口径一致。
# 用法：./run_daily.sh [回溯天数，默认 30]
set -euo pipefail

# 始终以本脚本所在目录为工作目录，避免相对路径/产物落点错误
cd "$(dirname "$0")"

DAYS="${1:-30}"
PY="${PYTHON:-python3}"

echo "==> [1/2] 采集近 ${DAYS} 天 AIGC 趋势数据"
"$PY" aigc_trend_brief.py --days "${DAYS}" --output-dir output

echo "==> [2/2] 渲染看板 → site/index.html"
mkdir -p site
"$PY" render_dashboard.py --data output/aigc_data.json --out site/index.html

echo "==> 流水线完成"
