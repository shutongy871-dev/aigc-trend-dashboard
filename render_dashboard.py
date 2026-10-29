#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC 趋势看板生成器
===================
读取 aigc_trend_brief.py 产出的结构化 JSON（output/aigc_data_*.json），
生成一个自包含、零外部依赖、可交互的单文件 HTML 趋势看板。

看板特性：
  - 三个视图：前沿项目 / Hugging Face 新模型 / Hacker News 热议
  - 项目卡片：GitHub 图标直链、一句话简介、"粘贴到通用 Agent 即可使用"的命令 + 一键复制
  - 交互：关键词搜索、赛道筛选、热度/star/时间排序、复制成功 Toast、卡片动效

用法：
  python3 render_dashboard.py
  python3 render_dashboard.py --data output/aigc_data_20261006.json
"""
from __future__ import annotations

import argparse
import json
import os
import glob

DATA_TOKEN = '"__AIGC_DASHBOARD_DATA__"'


def find_latest_data(output_dir: str) -> str:
    # 部署口径：固定名 aigc_data.json 优先（每日原地更新，网址稳定）；
    # 兼容本地按日期归档的 aigc_data_*.json
    fixed = os.path.join(output_dir, "aigc_data.json")
    if os.path.exists(fixed):
        return fixed
    files = sorted(glob.glob(os.path.join(output_dir, "aigc_data_*.json")))
    if not files:
        raise FileNotFoundError(
            f"目录 {output_dir} 下未找到 aigc_data.json，请先运行 aigc_trend_brief.py"
        )
    return files[-1]


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>生成式 AI 及其应用生态趋势看板</title>
<script id="github-pages-vercel-redirect">
(function () {
  // 仅 GitHub Pages 跳转；Vercel、自定义域名和本地访问均不受影响。
  if (!window.location.hostname.toLowerCase().endsWith(".github.io")) return;

  // 使用固定生产域名，使两个入口始终访问最新成功部署；与生成模板保持同步。
  var VERCEL_URL = "https://aigc-trend-dashboard-site.vercel.app";
  var target = new URL(VERCEL_URL);
  target.pathname = window.location.pathname;
  target.search = window.location.search;
  target.hash = window.location.hash;

  function showFallback() {
    if (document.getElementById("vercel-redirect-fallback")) return;
    var notice = document.createElement("aside");
    notice.id = "vercel-redirect-fallback";
    notice.setAttribute("role", "status");
    // 样式仅作用于新增提示，不修改网站原有 CSS 或业务元素。
    notice.style.cssText = "position:relative;z-index:2;padding:14px 24px;background:#111729;color:#e8ecf6;border-bottom:1px solid #7c8cff;font:14px/1.6 sans-serif;overflow-wrap:anywhere;";
    notice.appendChild(document.createTextNode("如果页面没有自动跳转，"));
    var link = document.createElement("a");
    link.href = target.href;
    link.textContent = "请点击此处访问 Vercel 网站";
    link.style.cssText = "color:#c4ccff;text-decoration:underline;";
    notice.appendChild(link);
    notice.appendChild(document.createTextNode("。"));
    document.body.prepend(notice);
  }

  // 若自动导航没有离开旧页，在正文可用后显示同一目标的手动链接。
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showFallback, { once: true });
  } else {
    showFallback();
  }
  try {
    window.location.replace(target.href);
  } catch (error) {
    // 导航被浏览器阻止时保留原页面和上面的兜底链接。
  }
})();
</script>
<style>
  :root {
    --bg: #0a0e1a;
    --bg-soft: #111729;
    --card: rgba(255, 255, 255, 0.035);
    --card-hover: rgba(255, 255, 255, 0.06);
    --border: rgba(255, 255, 255, 0.09);
    --border-strong: rgba(255, 255, 255, 0.16);
    --text: #e8ecf6;
    --text-dim: #9aa6c2;
    --text-faint: #6b7794;
    --accent: #7c8cff;
    --accent-2: #b07cff;
    --accent-soft: rgba(124, 140, 255, 0.14);
    --good: #4ade80;
    --warn: #fbbf24;
    --radius: 16px;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
            "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { scroll-behavior: smooth; }
  body {
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }
  /* 氛围背景光 */
  body::before, body::after {
    content: "";
    position: fixed;
    border-radius: 50%;
    filter: blur(120px);
    z-index: 0;
    pointer-events: none;
  }
  body::before {
    width: 560px; height: 560px;
    background: rgba(94, 110, 255, 0.18);
    top: -180px; left: -120px;
  }
  body::after {
    width: 520px; height: 520px;
    background: rgba(176, 124, 255, 0.12);
    bottom: -200px; right: -140px;
  }
  .wrap { position: relative; z-index: 1; max-width: 1240px; margin: 0 auto; padding: 40px 24px 80px; }

  /* 顶部 */
  header.hero { margin-bottom: 32px; }
  .hero-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; flex-wrap: wrap; }
  h1 {
    font-size: 32px; font-weight: 800; letter-spacing: -0.02em;
    background: linear-gradient(120deg, #fff 20%, #aeb9ff 60%, #d3b8ff);
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  }
  .subtitle { color: var(--text-dim); margin-top: 8px; font-size: 14.5px; }
  .hero-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .window-filter {
    display: grid; grid-template-columns: auto auto; align-items: center; gap: 2px 8px;
    background: var(--accent-soft); color: #c4ccff;
    border: 1px solid rgba(124, 140, 255, 0.3);
    padding: 7px 10px 7px 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  }
  .window-filter label { color: var(--text-dim); }
  .window-filter select {
    border: 0; background: transparent; padding: 2px 22px 2px 4px;
    color: #dce1ff; font-size: 13px; font-weight: 700;
  }
  .window-dates { grid-column: 1 / -1; color: var(--text-faint); font-size: 11px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin-top: 26px; }
  .stat {
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 16px 18px;
    transition: transform .25s ease, border-color .25s ease;
  }
  .stat:hover { transform: translateY(-2px); border-color: var(--border-strong); }
  .stat .num { font-size: 26px; font-weight: 800; letter-spacing: -0.02em; }
  .stat .lbl { color: var(--text-dim); font-size: 13px; margin-top: 2px; }
  .stat .num.accent { color: var(--accent); }
  .stat .num.pink { color: var(--accent-2); }
  .stat .num.amber { color: var(--warn); }

  /* 控制条 */
  .toolbar {
    display: flex; flex-direction: column; gap: 14px;
    margin: 30px 0 22px;
    background: var(--bg-soft);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
  }
  .tabs { display: inline-flex; background: rgba(255,255,255,0.05); border-radius: 12px; padding: 4px; gap: 4px; width: fit-content; }
  .tab {
    border: none; background: transparent; color: var(--text-dim);
    padding: 8px 18px; border-radius: 9px; font-size: 14px; font-weight: 600;
    cursor: pointer; font-family: var(--sans); transition: all .2s ease;
  }
  .tab:hover { color: var(--text); }
  .tab.active { background: linear-gradient(120deg, var(--accent), var(--accent-2)); color: #fff; box-shadow: 0 4px 16px rgba(124,140,255,.35); }
  .controls { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .search-box { position: relative; flex: 1; min-width: 220px; }
  .search-box svg { position: absolute; left: 13px; top: 50%; transform: translateY(-50%); color: var(--text-faint); }
  .search-box input {
    width: 100%; background: rgba(255,255,255,0.05);
    border: 1px solid var(--border); color: var(--text);
    padding: 10px 14px 10px 40px; border-radius: 11px; font-size: 14px;
    font-family: var(--sans); transition: border-color .2s ease, box-shadow .2s ease;
  }
  .search-box input::placeholder { color: var(--text-faint); }
  .search-box input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  select {
    background: rgba(255,255,255,0.05); border: 1px solid var(--border);
    color: var(--text); padding: 10px 14px; border-radius: 11px; font-size: 14px;
    font-family: var(--sans); cursor: pointer;
  }
  select:focus { outline: none; border-color: var(--accent); }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip {
    border: 1px solid var(--border); background: rgba(255,255,255,0.04);
    color: var(--text-dim); padding: 5px 13px; border-radius: 999px;
    font-size: 13px; cursor: pointer; transition: all .18s ease; font-family: var(--sans);
  }
  .chip:hover { border-color: var(--border-strong); color: var(--text); }
  .chip.active { background: var(--accent-soft); border-color: rgba(124,140,255,.5); color: #c4ccff; }
  .result-hint { color: var(--text-faint); font-size: 13px; }
  .result-hint:empty { display: none; }
  .summary-nav {
    width: 100%; margin: 0 0 22px; padding: 15px 18px; cursor: pointer;
    display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px;
    text-align: left; color: var(--text); background: rgba(255,255,255,.025);
    border: 1px solid var(--border); border-radius: 12px; font-family: var(--sans);
  }
  .summary-nav:hover, .summary-nav.active { border-color: rgba(251,191,36,.5); background: rgba(251,191,36,.055); }
  .summary-nav-kicker { color: var(--warn); font-size: 12px; font-weight: 700; }
  .summary-nav strong { font-size: 14px; }
  .summary-nav small { color: var(--text-dim); font-size: 12px; }

  /* 卡片网格 */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 18px; align-items: start; }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px;
    display: flex; flex-direction: column; gap: 13px;
    transition: transform .25s cubic-bezier(.2,.8,.2,1), border-color .25s ease, box-shadow .25s ease;
    animation: rise .5s cubic-bezier(.2,.8,.2,1) both;
  }
  .card:hover {
    transform: translateY(-4px); background: var(--card-hover);
    border-color: rgba(124,140,255,.45);
    box-shadow: 0 14px 40px rgba(0,0,0,.4), 0 0 0 1px rgba(124,140,255,.15);
  }
  @keyframes rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }

  .card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .badges { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }
  .badge-cat {
    font-size: 12.5px; font-weight: 600; color: #c4ccff;
    background: var(--accent-soft); border: 1px solid rgba(124,140,255,.28);
    padding: 4px 11px; border-radius: 999px;
  }
  .badge-surge { font-size: 11.5px; font-weight: 700; color: #ffd9a8; background: rgba(251,191,36,.13); border: 1px solid rgba(251,191,36,.35); padding: 3px 9px; border-radius: 999px; }
  .icon-btn {
    width: 36px; height: 36px; display: inline-flex; align-items: center; justify-content: center;
    border-radius: 10px; border: 1px solid var(--border); background: rgba(255,255,255,.05);
    color: var(--text-dim); cursor: pointer; transition: all .2s ease; flex-shrink: 0; text-decoration: none;
  }
  .icon-btn:hover { color: #fff; background: linear-gradient(120deg, var(--accent), var(--accent-2)); border-color: transparent; transform: translateY(-1px); }

  .card-title { font-size: 17px; font-weight: 700; letter-spacing: -0.01em; word-break: break-word; }
  .card-desc {
    color: var(--text-dim); font-size: 13.5px;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  .card-desc-en {
    font-size: 12px; color: var(--text-faint); font-style: italic;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .metrics { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; font-size: 13px; color: var(--text-dim); }
  .metric { display: inline-flex; align-items: center; gap: 5px; }
  .metric svg { color: var(--text-faint); }
  .metric a { color: var(--warn); text-decoration: none; display: inline-flex; align-items: center; gap: 5px; font-weight: 600; }
  .metric a:hover { text-decoration: underline; }
  .lang-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); display: inline-block; }
  .tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { font-size: 11.5px; color: var(--text-faint); background: rgba(255,255,255,.045); border: 1px solid var(--border); padding: 2px 9px; border-radius: 6px; }

  .cmd-box {
    margin-top: auto;
    display: flex; align-items: center; gap: 8px;
    background: rgba(0,0,0,.35); border: 1px solid var(--border);
    border-radius: 11px; padding: 7px 7px 7px 12px;
  }
  .cmd-box .prompt-hint { font-size: 11px; color: var(--text-faint); flex-shrink: 0; }
  .cmd-text {
    font-family: var(--mono); font-size: 12px; color: #b9c4e8;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1;
    user-select: all;
  }
  .copy-btn {
    flex-shrink: 0; border: 1px solid var(--border); background: rgba(255,255,255,.06);
    color: var(--text-dim); padding: 6px 10px; border-radius: 8px; cursor: pointer;
    font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px;
    font-family: var(--sans); transition: all .18s ease;
  }
  .copy-btn:hover { color: #fff; border-color: rgba(124,140,255,.5); background: var(--accent-soft); }
  .copy-btn.done { color: var(--good); border-color: rgba(74,222,128,.4); background: rgba(74,222,128,.1); }

  /* 展开/收起：能力详解 + 效果示意 */
  .expand-toggle {
    display: inline-flex; align-items: center; gap: 7px;
    background: rgba(255,255,255,.04); border: 1px solid var(--border);
    color: var(--text-dim); padding: 7px 13px; border-radius: 10px;
    font-size: 12.5px; font-weight: 600; cursor: pointer; font-family: var(--sans);
    transition: all .18s ease; align-self: flex-start;
  }
  .expand-toggle:hover { color: #fff; border-color: rgba(124,140,255,.5); background: var(--accent-soft); }
  .expand-toggle .chev { transition: transform .3s cubic-bezier(.2,.8,.2,1); display: inline-flex; }
  .expand-toggle.open .chev { transform: rotate(180deg); }
  .detail {
    display: none; flex-direction: column; gap: 14px;
    border-top: 1px dashed var(--border-strong); padding-top: 14px;
  }
  .detail.open { display: flex; animation: expandIn .35s cubic-bezier(.2,.8,.2,1); }
  @keyframes expandIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
  .detail h4 {
    font-size: 12px; font-weight: 700; color: var(--text-faint);
    text-transform: uppercase; letter-spacing: .08em; margin-bottom: 8px;
    display: flex; align-items: center; gap: 6px;
  }
  .ability-list { list-style: none; display: flex; flex-direction: column; gap: 7px; }
  .ability-list li { display: flex; gap: 9px; font-size: 13px; color: var(--text-dim); }
  .ability-list li .tick {
    flex-shrink: 0; width: 18px; height: 18px; border-radius: 6px;
    background: var(--accent-soft); color: var(--accent);
    display: inline-flex; align-items: center; justify-content: center; margin-top: 1px;
  }
  .ability-list li .tick svg { width: 11px; height: 11px; }

  /* 无 LLM 时：单一连贯的项目官方自述（不拼凑无关内容） */
  .self-desc {
    font-size: 13px; color: var(--text-dim); line-height: 1.65;
    background: rgba(255,255,255,.03); border-left: 2px solid rgba(124,140,255,.55);
    border-radius: 0 9px 9px 0; padding: 9px 12px;
  }
  .self-note {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: var(--text-faint); margin-top: 2px;
  }
  .meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .meta-cell {
    background: rgba(255,255,255,.035); border: 1px solid var(--border);
    border-radius: 11px; padding: 10px 12px;
  }
  .meta-cell .k { font-size: 11px; color: var(--text-faint); margin-bottom: 3px; }
  .meta-cell .v { font-size: 12.5px; color: var(--text-dim); }

  /* 效果示意舞台 */
  .demo {
    background: linear-gradient(160deg, rgba(124,140,255,.08), rgba(176,124,255,.05));
    border: 1px solid rgba(124,140,255,.22); border-radius: 14px; padding: 14px;
  }
  .demo-note { font-size: 11px; color: var(--text-faint); margin-top: 9px; display: flex; gap: 6px; align-items: center; }
  .flow { display: flex; flex-direction: column; gap: 9px; }
  .io-chip {
    display: flex; gap: 9px; align-items: flex-start; font-size: 12px;
    background: rgba(0,0,0,.28); border: 1px solid var(--border);
    border-radius: 10px; padding: 9px 11px;
  }
  .io-chip .tag-io {
    flex-shrink: 0; font-size: 10.5px; font-weight: 700; padding: 2px 8px;
    border-radius: 6px; text-transform: uppercase; letter-spacing: .04em;
  }
  .tag-in { background: rgba(124,140,255,.18); color: #aeb9ff; }
  .tag-out { background: rgba(74,222,128,.14); color: #8ff0b0; }
  .io-chip .c { color: var(--text-dim); }

  /* 视频胶片 */
  .film { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin-top: 9px; }
  .frame {
    aspect-ratio: 3/4; border-radius: 7px; position: relative; overflow: hidden;
    border: 1px solid rgba(255,255,255,.12);
  }
  .frame::after {
    content: ""; position: absolute; inset: 0;
    background: linear-gradient(120deg, transparent 30%, rgba(255,255,255,.25) 50%, transparent 70%);
    background-size: 200% 100%; animation: sheen 2.6s infinite;
  }
  @keyframes sheen { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
  .play-badge {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    color: rgba(255,255,255,.85); z-index: 2;
  }
  /* 图像网格 */
  .img-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-top: 9px; }
  .img-tile { aspect-ratio: 1; border-radius: 8px; border: 1px solid rgba(255,255,255,.12); }
  /* 声波 */
  .wave { display: flex; align-items: center; gap: 3px; height: 44px; margin-top: 10px; }
  .wave span {
    width: 4px; border-radius: 3px;
    background: linear-gradient(180deg, var(--accent), var(--accent-2));
    animation: pulse 1.1s ease-in-out infinite;
  }
  @keyframes pulse { 0%,100% { transform: scaleY(.35); } 50% { transform: scaleY(1); } }
  /* Agent 步骤 */
  .steps { display: flex; flex-direction: column; gap: 7px; margin-top: 9px; }
  .step {
    display: flex; align-items: center; gap: 9px; font-size: 12px; color: var(--text-dim);
    background: rgba(0,0,0,.25); border: 1px solid var(--border);
    border-radius: 9px; padding: 7px 10px;
  }
  .step .num {
    width: 18px; height: 18px; border-radius: 50%; flex-shrink: 0;
    background: var(--accent-soft); color: var(--accent);
    font-size: 10.5px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
  }
  .step.done .num { background: rgba(74,222,128,.16); color: var(--good); }
  .step.done { color: var(--text); }
  /* RAG 检索 */
  .doc-chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }
  .doc-chip {
    font-size: 10.5px; color: #ffd9a8; background: rgba(251,191,36,.1);
    border: 1px solid rgba(251,191,36,.3); padding: 3px 9px; border-radius: 7px;
  }
  /* 聊天气泡 */
  .chat-demo { display: flex; flex-direction: column; gap: 7px; margin-top: 9px; }
  .bubble {
    max-width: 85%; font-size: 12px; padding: 8px 11px; border-radius: 12px; line-height: 1.5;
  }
  .bubble.user { align-self: flex-end; background: linear-gradient(120deg, var(--accent), var(--accent-2)); color: #fff; border-bottom-right-radius: 4px; }
  .bubble.bot { align-self: flex-start; background: rgba(255,255,255,.07); color: var(--text-dim); border: 1px solid var(--border); border-bottom-left-radius: 4px; }
  /* 终端 */
  .terminal {
    background: #060912; border: 1px solid var(--border); border-radius: 10px;
    padding: 11px; margin-top: 9px; font-family: var(--mono); font-size: 11.5px; line-height: 1.7;
  }
  .terminal .t-green { color: #7ee2a8; }
  .terminal .t-blue { color: #8fb3ff; }
  .terminal .t-dim { color: var(--text-faint); }
  .caret-blink::after { content: "▋"; animation: blink 1s steps(1) infinite; color: var(--accent); }
  @keyframes blink { 50% { opacity: 0; } }

  /* 三层演示体系：真实素材画廊 / LLM 场景 / 赛道模板（分层叠加，失败自动降级） */
  .demo-layer { display: flex; flex-direction: column; }
  .demo-src {
    align-self: flex-start; font-size: 10px; font-weight: 600; letter-spacing: .03em;
    color: var(--text-faint); background: rgba(255,255,255,.05); border: 1px solid var(--border);
    padding: 2px 8px; border-radius: 6px; margin-bottom: 8px;
  }
  .demo-src.s-real { color: #8ff0b0; background: rgba(74,222,128,.08); border-color: rgba(74,222,128,.28); }
  .demo-src.s-llm { color: #aeb9ff; background: rgba(124,140,255,.08); border-color: rgba(124,140,255,.28); }
  /* 真实素材画廊 */
  .gallery { display: flex; flex-direction: column; gap: 7px; }
  .demo-shot {
    width: 100%; max-height: 240px; object-fit: cover; display: block;
    border-radius: 10px; border: 1px solid rgba(255,255,255,.12); cursor: zoom-in; background: rgba(0,0,0,.2);
  }
  .gal-thumbs { display: flex; gap: 6px; flex-wrap: wrap; }
  .gal-thumb {
    width: 52px; height: 40px; object-fit: cover; border-radius: 7px; cursor: zoom-in;
    border: 1px solid rgba(255,255,255,.14); opacity: .8; background: rgba(0,0,0,.2);
  }
  .gal-thumb:hover { opacity: 1; border-color: var(--accent); }
  /* LLM 场景：功能卡片栅格 */
  .scene-cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin-top: 9px; }
  .scene-card {
    font-size: 11.5px; color: var(--text-dim); line-height: 1.5;
    background: rgba(124,140,255,.07); border: 1px solid rgba(124,140,255,.22);
    border-radius: 9px; padding: 8px 10px;
  }
  /* 灯箱（点击放大） */
  .lightbox {
    position: fixed; inset: 0; z-index: 999; display: none;
    align-items: center; justify-content: center; padding: 40px;
    background: rgba(5,8,16,.86); backdrop-filter: blur(6px); cursor: zoom-out;
  }
  .lightbox.open { display: flex; }
  .lightbox img { max-width: 100%; max-height: 100%; border-radius: 10px; box-shadow: 0 24px 80px rgba(0,0,0,.6); }

  /* 列表视图（HN） */
  .list { display: flex; flex-direction: column; gap: 12px; }
  .row {
    display: flex; align-items: center; gap: 16px;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 14px; padding: 15px 18px; transition: all .22s ease;
    animation: rise .4s both;
  }
  .row:hover { border-color: rgba(124,140,255,.4); background: var(--card-hover); transform: translateX(3px); }
  .row .score { text-align: center; flex-shrink: 0; min-width: 52px; }
  .row .score .pts { font-size: 20px; font-weight: 800; color: var(--warn); }
  .row .score .cap { font-size: 11px; color: var(--text-faint); }
  .row .body { flex: 1; min-width: 0; }
  .row .title { font-size: 15px; font-weight: 600; color: var(--text); text-decoration: none; }
  .row .title:hover { color: var(--accent); }
  .row .meta-line { font-size: 12.5px; color: var(--text-faint); margin-top: 3px; }
  .row .meta-line a { color: var(--text-dim); text-decoration: none; }
  .row .meta-line a:hover { color: var(--accent); text-decoration: underline; }

  .empty { text-align: center; padding: 70px 20px; color: var(--text-faint); }
  .empty svg { margin-bottom: 14px; opacity: .5; }

  /* Toast */
  .toast {
    position: fixed; bottom: 28px; left: 50%; transform: translateX(-50%) translateY(80px);
    background: #161d33; border: 1px solid rgba(74,222,128,.4); color: #d8ffe6;
    padding: 11px 20px; border-radius: 12px; font-size: 14px; font-weight: 600;
    display: inline-flex; align-items: center; gap: 9px;
    box-shadow: 0 12px 36px rgba(0,0,0,.5);
    opacity: 0; transition: all .32s cubic-bezier(.2,.8,.2,1); z-index: 99;
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }

  footer { margin-top: 50px; text-align: center; color: var(--text-faint); font-size: 12.5px; }
  footer code { font-family: var(--mono); color: var(--text-dim); background: rgba(255,255,255,.05); padding: 2px 7px; border-radius: 6px; }

  [hidden] { display: none !important; }
  .tabs { flex-wrap: wrap; max-width: 100%; }
  .tab { padding: 9px 13px; }
  .discovery-intro { margin-bottom: 24px; }
  .discovery-intro h2 { font-size: 25px; letter-spacing: -.025em; margin-bottom: 7px; }
  .discovery-intro p, .scope-note { color: var(--text-dim); font-size: 13px; line-height: 1.8; }
  .analysis-notice { border-left: 3px solid var(--warn); background: #fbbf2408; padding: 12px 16px; margin: 14px 0; font-size: 13px; color: #dac9a4; }
  .discovery-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; }
  .learning-card .card-desc { display: block; overflow: visible; font-size: 15px; color: var(--text); }
  .learning-card .card-desc p + p { margin-top: 10px; }
  .learning-card { min-width: 0; }
  .learning-card p { overflow-wrap: anywhere; }
  .learning-fact { color: var(--text-dim); font-size: 13px; line-height: 1.8; }
  .learning-fact strong { color: #bac5f7; display: block; font-size: 12px; margin-bottom: 3px; }
  .learning-value { border-left: 2px solid var(--accent); padding-left: 12px; }
  .source-link { display: inline; color: #9dacfa; font-size: 11px; text-decoration: none; margin-left: 5px; }
  .source-link:hover { text-decoration: underline; }
  .source-status { font-size: 11px; color: var(--text-faint); }
  .learning-links { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 4px; }
  .learning-links a { color: #c0caff; font-size: 13px; text-decoration: none; border: 1px solid var(--border); border-radius: 8px; padding: 7px 12px; }
  .learning-links a:hover { background: var(--accent-soft); }
  .learning-steps { padding-left: 22px; font-size: 13px; color: var(--text-dim); }
  .learning-steps li { padding: 4px 0 7px; overflow-wrap: anywhere; white-space: pre-wrap; }
  .evidence-list { font-size: 12px; color: var(--text-dim); }
  .evidence-list summary { cursor: pointer; color: #a8b6ed; }
  .evidence-list blockquote { white-space: pre-wrap; overflow-wrap: anywhere; border-left: 2px solid var(--border); margin: 8px 0 15px; padding-left: 12px; max-height: 180px; overflow: auto; }
  .trend-card h3 { font-size: 19px; }
  .trend-card p { font-size: 14px; color: var(--text-dim); }
  .trend-members { list-style: none; font-size: 13px; }
  .trend-members li { padding: 10px 0; border-top: 1px solid var(--border); }
  .trend-members a { color: #bcc7ff; text-decoration: none; overflow-wrap: anywhere; }
  .trend-members p { font-size: 12px; margin-top: 5px; }
  .trend-bars { display: flex; flex-direction: column; gap: 9px; padding: 14px; border-radius: 10px; background: #0003; }
  .trend-bar { display: grid; grid-template-columns: 62px 1fr 28px; gap: 10px; align-items: center; font-size: 12px; color: var(--text-dim); }
  .trend-track { background: #ffffff07; height: 8px; border-radius: 5px; overflow: hidden; }
  .trend-fill { height: 100%; background: var(--accent); border-radius: 5px; }
  .trend-fill.prev { background: #586582; }
  .mini-note { font-size: 11px; color: var(--text-faint); }
  .demo-result { border-left: 2px solid var(--good); padding-left: 12px; }
  .demo-stage-title { display: block; color: #bac5f7; font-size: 12px; margin: 12px 0 4px; }
  .tabs { flex-wrap: wrap; max-width: 100%; }
  .builder-view { display: flex; flex-direction: column; gap: 20px; }
  .builder-intro { padding: 24px; background: var(--bg-soft); border: 1px solid var(--border); border-radius: var(--radius); }
  .builder-kicker { color: var(--good); font: 12px var(--mono); letter-spacing: .08em; margin-bottom: 8px; }
  .builder-intro h2 { font-size: 24px; letter-spacing: -.025em; }
  .builder-intro p { color: var(--text-dim); font-size: 14px; margin-top: 8px; }
  .builder-source { display: flex; gap: 8px 20px; flex-wrap: wrap; margin-top: 18px; color: var(--text-dim); font-size: 12px; }
  .builder-source a, .builder-card a { color: #c4ccff; text-decoration: none; }
  .builder-source a:hover, .builder-card a:hover { text-decoration: underline; }
  .builder-warning { margin-top: 12px; padding: 10px 14px; border-left: 2px solid var(--warn); color: var(--warn); font-size: 13px; }
  .builder-filters { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
  .builder-filters select { max-width: 100%; }
  .builder-filters label { display: flex; align-items: center; gap: 8px; color: var(--text-dim); font-size: 13px; cursor: pointer; }
  .builder-filters input { accent-color: var(--accent); }
  .builder-count { color: var(--text-dim); font-size: 13px; }
  .builder-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; align-items: start; }
  .builder-card { min-width: 0; padding: 22px; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); }
  .builder-author { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .builder-author strong { font-size: 16px; }
  .builder-handle, .builder-time { color: var(--text-dim); font-size: 12px; }
  .builder-bio { color: var(--text-dim); font-size: 12px; margin-top: 8px; white-space: pre-line; overflow-wrap: anywhere; }
  .builder-text { margin: 18px 0; font-size: 15px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
  .builder-text.clamped { display: -webkit-box; -webkit-line-clamp: 7; -webkit-box-orient: vertical; overflow: hidden; }
  .builder-bottom { border-top: 1px solid var(--border); padding-top: 14px; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: center; }
  .builder-metrics { display: flex; flex-wrap: wrap; gap: 12px; color: var(--text-dim); font-size: 12px; }
  .builder-actions { display: flex; align-items: center; gap: 14px; font-size: 13px; }
  .builder-expand { border: none; background: transparent; color: #c4ccff; cursor: pointer; font: inherit; }
  .builder-tag { color: var(--text-dim); border: 1px solid var(--border); border-radius: 5px; padding: 2px 6px; font-size: 11px; }
  @media (max-width: 760px) {
    .builder-grid { grid-template-columns: 1fr; }
    .builder-intro, .builder-card { padding: 18px; }
  }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
  }
  @media (max-width: 560px) {
    .grid { grid-template-columns: 1fr; }
    .discovery-grid { grid-template-columns: 1fr; }
    .tab { padding: 8px 10px; font-size: 12px; }
    .summary-nav { grid-template-columns: 1fr auto; }
    .summary-nav-kicker { grid-column: 1 / -1; }
    h1 { font-size: 26px; }
    .wrap { padding: 28px 16px 60px; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div class="hero-top">
      <div>
        <h1>生成式 AI 及其应用生态趋势看板</h1>
        <div class="subtitle">每天发现值得尝试的 AI：理解它的原理，学会使用，找到下一个灵感。</div>
      </div>
      <div class="hero-actions">
        <div class="window-filter">
          <label for="windowFilter">创建时间</label>
          <select id="windowFilter">
            __AIGC_WINDOW_OPTIONS__
          </select>
          <span class="window-dates" id="windowDates"></span>
        </div>
      </div>
    </div>
    <div class="stats" id="stats"></div>
  </header>

  <div class="toolbar">
    <div class="tabs">
      <button class="tab" data-tab="projects">全部项目</button>
      <button class="tab active" data-tab="skills">Skill / 工具</button>
      <button class="tab" data-tab="apps">软件 / 小程序</button>
      <button class="tab" data-tab="models">HF 新模型</button>
      <button class="tab" data-tab="hn">HN 热议</button>
      <button class="tab" data-tab="builders">Builder 观点</button>
    </div>
    <div class="controls" id="controls">
      <div class="search-box">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input type="text" id="search" aria-label="搜索项目与原理" placeholder="搜索项目、用途、原理或你想解决的问题…">
      </div>
      <select id="sort">
        <option value="heat">按综合热度</option>
        <option value="stars">按 Stars</option>
        <option value="newest">按最新发布</option>
      </select>
    </div>
    <div class="chips" id="chips"></div>
    <div class="result-hint" id="hint"></div>
  </div>

  <button class="summary-nav" id="summaryNav" type="button">
    <span class="summary-nav-kicker">趋势总结</span>
    <strong>机制与爆发观察</strong>
    <small>查看共同原理与近期变化 →</small>
  </button>

  <main id="content"></main>

  <footer>
    资料来自 GitHub README、Hugging Face、Hacker News 与 Follow Builders · AI 解读附来源，Builder 观点保留原文
  </footer>
</div>

<div class="toast" id="toast">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
  <span id="toastText">已复制</span>
</div>

<script>
const DASH_DATA = "__AIGC_DASHBOARD_DATA__";
const projects = DASH_DATA.projects || [];
const hfModels = DASH_DATA.hf_models || [];
const hnStories = DASH_DATA.hn_hot_stories || [];
const discovery = DASH_DATA.discovery || {};
const builderFeed = DASH_DATA.builder_feed || {};
const byRepo = new Map(projects.map(p => [p.full_name, p]));

const state = {
  tab: "skills", query: "", category: "全部", sort: "heat", windowDays: "full",
  builderAuthor: "all", builderSort: "engagement", builderHideShort: true
};

/* ---------- 图标 ---------- */
const ICON = {
  github: '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.69 1.25 3.35.96.1-.75.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.78 0c2.2-1.49 3.16-1.18 3.16-1.18.63 1.59.23 2.76.12 3.05.74.81 1.18 1.83 1.18 3.09 0 4.42-2.69 5.39-5.26 5.68.41.36.78 1.06.78 2.14 0 1.55-.01 2.8-.01 3.18 0 .3.21.67.8.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5Z"/></svg>',
  star: '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="m12 17.27 6.18 3.73-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>',
  fork: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="3" r="2"/><circle cx="18" cy="3" r="2"/><circle cx="12" cy="15" r="2"/><path d="M6 5v6a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V5"/><path d="M12 13v4"/></svg>',
  comment: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  copy: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
  check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
  heart: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>',
  download: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
  external: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
  link: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
  play: '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.14v13.72c0 .8.87 1.3 1.55.88l10.8-6.86a1.04 1.04 0 0 0 0-1.76L9.55 4.26A1.04 1.04 0 0 0 8 5.14Z"/></svg>',
  info: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
  chevron: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  searchDim: '<svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>'
};

/* ---------- 数字格式化 ---------- */
const fmt = n => (Number(n) || 0).toLocaleString("en-US");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function selectedWindow() {
  const configured = DASH_DATA.window || {};
  const end = String(configured.end || "").slice(0, 10);
  if (state.windowDays === "full") {
    return { start: String(configured.start || "").slice(0, 10), end,
      days: Number(configured.days) || 90, full: true };
  }
  const days = Number(state.windowDays);
  const endDate = new Date(end + "T00:00:00Z");
  const startDate = new Date(endDate);
  startDate.setUTCDate(startDate.getUTCDate() - days + 1);
  return { start: startDate.toISOString().slice(0, 10), end, days, full: false };
}
function inSelectedWindow(item) {
  const active = selectedWindow();
  if (active.full) return true;
  const created = String(item?.created_at || "").slice(0, 10);
  return Boolean(created && created >= active.start && created <= active.end);
}
function scopedProjects() {
  return projects.filter(inSelectedWindow);
}

/* ---------- 复制 ---------- */
let toastTimer;
function showToast(text) {
  document.getElementById("toastText").textContent = text;
  const t = document.getElementById("toast");
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}
async function copyText(text, btn) {
  const done = () => {
    if (btn) {
      const old = btn.innerHTML;
      btn.classList.add("done");
      btn.innerHTML = ICON.check + "已复制";
      setTimeout(() => { btn.classList.remove("done"); btn.innerHTML = old; }, 1600);
    }
    showToast("命令已复制，去 Agent 中粘贴即可");
  };
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); document.body.removeChild(ta);
    }
    done();
  } catch (e) { showToast("复制失败，请手动选择文本"); }
}

/* ---------- 顶部信息 ---------- */
function renderHeader() {
  const active = selectedWindow();
  const scoped = scopedProjects();
  document.getElementById("windowFilter").value = String(state.windowDays);
  document.getElementById("windowDates").textContent = active.start + " ~ " + active.end + " UTC";
  const stats = [
    { num: scoped.filter(p => p.discovery_kind === "skill_tool").length,
      cls: "accent", lbl: "Skill / 工具" },
    { num: scoped.filter(p => p.discovery_kind === "application").length,
      cls: "pink", lbl: "软件 / 应用" },
    { num: scoped.filter(p => p.discovery_kind === "research").length,
      cls: "amber", lbl: "研究 / 模型" },
    { num: scoped.length, cls: "", lbl: "当前窗口项目" }
  ];
  document.getElementById("stats").innerHTML = stats.map(s =>
    '<div class="stat"><div class="num ' + s.cls + '">' + fmt(s.num) + '</div><div class="lbl">' + s.lbl + "</div></div>"
  ).join("");
}

/* ---------- 赛道 chips ---------- */
function renderChips() {
  const box = document.getElementById("chips");
  if (state.tab !== "projects") { box.style.display = "none"; return; }
  box.style.display = "flex";
  const cats = ["全部", ...new Set(scopedProjects().map(p => p.category).filter(Boolean))];
  box.innerHTML = cats.map(c =>
    '<button class="chip' + (state.category === c ? " active" : "") + '" data-cat="' + esc(c) + '">' + esc(c) + "</button>"
  ).join("");
  box.querySelectorAll(".chip").forEach(ch =>
    ch.addEventListener("click", () => { state.category = ch.dataset.cat; renderChips(); renderProjects(); })
  );
}

/* ---------- 项目卡片 ---------- */
function hasChineseText(value) {
  return /[\u3400-\u9fff]/.test(String(value || ""));
}
function chineseClaim(...claims) {
  return claims.find(claim => hasChineseText(claim?.text));
}
function zhDesc(p) {
  if (hasChineseText(p.learning?.summary?.text)) return p.learning.summary.text;
  if (p.description_zh && ["source", "bing", "trae-agent"].includes(p.translation_provider)) return p.description_zh;
  if (p.description) return p.description;
  return "项目尚未提供简介，展开查看已收集的 README 资料。";
}
function descriptionHTML(p) {
  const parts = String(zhDesc(p)).trim()
    .replace(/([。！？；])\s+(?=[A-Za-z])/g, "$1\u0000")
    .replace(/([.!?;])\s+(?=[\u3400-\u9fff])/g, "$1\u0000")
    .split("\u0000").map(x => x.trim()).filter(Boolean);
  const refs = hasChineseText(p.learning?.summary?.text)
    ? refsHTML(p, p.learning.summary.sources) : "";
  return parts.map((part, index) => {
    const lang = /[\u3400-\u9fff]/.test(part) ? "zh-CN" : "en";
    return '<p lang="' + lang + '">' + esc(part) + (index === parts.length - 1 ? refs : "") + "</p>";
  }).join("");
}

/* 展开面板：连贯的能力说明 + 真实元信息 + 效果示意 */
function detailPanel(p) {
  const l = p.learning;
  const sources = (p.evidence || []).map(e =>
    '<a class="source-link" href="' + safeURL(e.url) + '" target="_blank" rel="noopener">' +
      esc(e.id + " · " + e.heading) + '</a><blockquote>' + esc(e.text) + "</blockquote>").join("");
  return '<div class="detail"><div><h4>使用演示</h4>' + learningDemo(p) + "</div>" +
    factHTML(p, "适合谁", l?.audience) + factHTML(p, "它为什么能做到", l?.mechanism) +
    factHTML(p, "可以借鉴的想法", l?.inspiration) + factHTML(p, "使用前留意", l?.limitations) +
    '<details class="evidence-list"><summary>查看原始资料 · ' + (p.evidence || []).length +
    ' 段摘录</summary>' + (sources || '<p>本次未能获取 README，请打开仓库查看。</p>') + "</details></div>";
}
function projectCard(p, i, featuredKind="") {
  const tags = (p.topics || []).slice(0, 4).map(t => '<span class="tag">' + esc(t) + "</span>").join("");
  const badge = featuredKind === "skills" ? "🧩 Skill / 工具"
    : featuredKind === "apps" ? "📱 软件 / 应用"
    : (p.category_emoji || "📦") + " " + (p.category || "其他");
  const hn = p.hn_points
    ? '<span class="metric"><a href="' + esc(p.hn_url) + '" target="_blank" rel="noopener">' + ICON.comment + fmt(p.hn_points) + " / " + fmt(p.hn_comments) + " 评论</a></span>"
    : "";
  return (
    '<article class="card learning-card" style="animation-delay:' + Math.min(i * 45, 450) + 'ms">' +
      '<div class="card-head"><div class="badges">' +
        '<span class="badge-cat">' + esc(badge) + "</span>" +
        (p.trend_type === "surge" ? '<span class="badge-surge">社区翻红</span>' : "") +
      "</div>" +
      '<a class="icon-btn" href="' + esc(p.url) + '" target="_blank" rel="noopener" title="在 GitHub 打开" aria-label="GitHub 链接">' + ICON.github + "</a></div>" +
      '<div class="card-title">' + esc(p.full_name) + "</div>" +
      '<div class="card-desc">' + descriptionHTML(p) + "</div>" +
      factHTML(p, "帮你解决什么",
        chineseClaim(p.learning?.value, p.learning?.outcome), "learning-value") +
      '<div class="metrics">' +
        '<span class="metric">' + ICON.star + fmt(p.stars) + "</span>" +
        '<span class="metric">' + ICON.fork + fmt(p.forks) + "</span>" +
        hn +
        (p.language ? '<span class="metric"><span class="lang-dot"></span>' + esc(p.language) + "</span>" : "") +
      "</div>" +
      (tags ? '<div class="tag-row">' + tags + "</div>" : "") +
      '<button class="expand-toggle" aria-expanded="false"><span class="chev">' + ICON.chevron + '</span><span class="expand-label">查看演示</span></button>' +
      detailPanel(p) +
      '<div class="learning-links"><a href="' + safeURL(p.url + "#readme") + '" target="_blank" rel="noopener">官方使用说明 ↗</a>' +
      '<button class="copy-btn" data-cmd="' + esc(downloadPrompt(p)) + '">' + ICON.copy + "复制给 Agent 下载</button></div>" +
    "</article>"
  );
}
function safeURL(value) {
  try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) ? esc(u.href) : "#"; }
  catch (_) { return "#"; }
}
function refsHTML(p, ids) {
  return (ids || []).map(id => {
    const e = (p.evidence || []).find(e => e.id === id);
    return e ? '<a class="source-link" href="' + safeURL(e.url) + '" title="' + esc(e.heading + " · " + e.text.slice(0, 240)) +
      '" target="_blank" rel="noopener">[' + esc(id) + "]</a>" : "";
  }).join("");
}
function claimHTML(p, claim) {
  return hasChineseText(claim?.text) ? esc(claim.text) + refsHTML(p, claim.sources) : "";
}
function factHTML(p, label, claim, cls="") {
  return hasChineseText(claim?.text)
    ? '<div class="learning-fact ' + cls + '"><strong>' + esc(label) + "</strong><p>" +
    claimHTML(p, claim) + "</p></div>" : "";
}
function downloadPrompt(p) {
  return "请帮我下载并安装这个 GitHub 项目：" + p.url + "\n" +
    "先阅读官方 README，确认运行环境和安全风险，再按项目官方步骤下载、安装并完成最小可运行验证。" +
    "不要使用仓库未推荐的第三方安装包；如果需要 API Key、付费服务或高风险系统权限，请先询问我。";
}
function learningDemo(p) {
  const d = p.learning?.demo;
  if (!d) return '<p class="learning-fact">暂缺可核实的使用演示，请查看官方使用说明。</p>';
  const input = chineseClaim(d.input);
  const output = chineseClaim(d.output);
  const steps = (d.steps || []).filter(step => hasChineseText(step?.text));
  if (!input && !output && !steps.length) {
    return '<p class="learning-fact">暂缺中文使用演示，请查看官方使用说明。</p>';
  }
  return '<div class="demo-box">' +
    (input ? '<p class="learning-fact">' + claimHTML(p, input) + "</p>" : "") +
    '<div class="demo-result">' +
    '<strong class="demo-stage-title">处理过程</strong>' +
    (steps.length ? '<ol class="learning-steps">' +
      steps.map(c => '<li>' + claimHTML(p, c) + "</li>").join("") + "</ol>" : "") +
    factHTML(p, "预期产物", output) + "</div></div>";
}
function matchesQuery(p) {
  const q = state.query.trim().toLowerCase();
  return !q || [p.full_name, p.description, p.language, (p.topics || []).join(" "),
    JSON.stringify(p.learning || {})].join(" ").toLowerCase().includes(q);
}
function renderFeatured(kind) {
  const skills = kind === "skills";
  const targetKind = skills ? "skill_tool" : "application";
  const list = scopedProjects()
    .filter(p => p.discovery_kind === targetKind && matchesQuery(p))
    .sort((a, b) => b.heat_score - a.heat_score);
  document.getElementById("hint").textContent = "共 " + list.length + " 个" +
    (skills ? " Skill / 工具" : " 软件 / 应用");
  const el = document.getElementById("content");
  el.className = "";
  el.innerHTML = '<div class="discovery-grid">' + (list.length ? list.map((p, i) => projectCard(p, i, kind)).join("") :
      '<div class="empty">暂无匹配项目，试试其他关键词或查看全部项目。</div>') + "</div>" +
    '<p class="scope-note" style="margin-top:22px">' + esc(discovery.scope || "") +
    " Skill / 工具分类优先采用 AI 学习卡，其余项目按仓库名称、简介与 topics 规则初筛。</p>";
  bindCopy(el); bindExpand(el);
}
function metricBars(m) {
  if (!m.comparable) return '<div class="analysis-notice">采集窗口不足两个完整 7 日，暂不判断增长。</div>';
  const max = Math.max(m.recent, m.previous, 1);
  const bar = (label, n, cls) => '<div class="trend-bar"><span>' + label + '</span><div class="trend-track"><div class="trend-fill ' +
    cls + '" style="width:' + (n / max * 100) + '%"></div></div><strong>' + fmt(n) + "</strong></div>";
  return '<div class="trend-bars">' + bar("前 7 日", m.previous, "prev") + bar("近 7 日", m.recent, "") +
    '<span class="mini-note">新建仓库数 · ' + esc(m.previous_start) + " 至 " + esc(m.end_exclusive) + "（不含末日）</span>" +
    '<span class="mini-note">' + (m.change_pct === null ? "前期为 0，不计算增长百分比" :
      "样本内环比 " + (m.change_pct > 0 ? "+" : "") + m.change_pct + "%") + "</span></div>";
}
function scopedMetricBars(m) {
  return state.windowDays === "full" ? metricBars(m)
    : '<div class="analysis-notice">当前仅筛选项目范围；双周趋势需切回“本期”窗口查看。</div>';
}
function renderTrends() {
  const el = document.getElementById("content");
  const q = state.query.trim().toLowerCase();
  const clusters = (discovery.clusters || []).map(c => ({
    ...c, members: c.members.filter(m => inSelectedWindow(byRepo.get(m.repo)))
  })).filter(c => c.members.length >= 3)
    .filter(c => !q || JSON.stringify(c).toLowerCase().includes(q));
  const candidates = (discovery.candidates || []).map(c => ({
    ...c, members: c.members.filter(repo => inSelectedWindow(byRepo.get(repo)))
  })).filter(c => c.members.length >= 3)
    .filter(c => !q || JSON.stringify(c).toLowerCase().includes(q));
  document.getElementById("hint").textContent = "至少 3 个项目支持同一机制 · 原理由 AI 归纳 · 数量按创建日期计算";
  el.className = "";
  let body = "";
  if (clusters.length) {
    body = clusters.map(c => '<article class="card trend-card"><div class="badges"><span class="badge-cat">' +
      esc(c.metrics.signal) + '</span><span class="mini-note">' + c.members.length + ' 个项目 · AI 机制分析</span></div><h3>' +
      esc(c.title) + '</h3><p>' + esc(c.mechanism) + "</p>" + scopedMetricBars(c.metrics) +
      (c.inspiration ? '<div class="learning-fact learning-value"><strong>值得尝试的想法</strong><p>' + esc(c.inspiration) + "</p></div>" : "") +
      '<ul class="trend-members">' + c.members.map(m => {
        const p = byRepo.get(m.repo);
        return p ? '<li><a href="' + safeURL(p.url) + '" target="_blank" rel="noopener">' + esc(m.repo) +
          ' ↗</a><p>' + esc(m.why) + refsHTML(p, m.sources) + "</p></li>" : "";
      }).join("") + "</ul></article>").join("");
  } else {
    body = candidates.map(c =>
      '<article class="card trend-card"><span class="source-status">标签初筛 · 尚未验证共同机制</span><h3>' + esc(c.title) +
      '</h3><p>' + c.members.length + " 个候选项目。属于同一赛道，是否使用相同底层原理仍需逐项阅读。</p>" +
      scopedMetricBars(c.metrics) + '<ul class="trend-members">' + c.members.slice(0, 4).map(n => {
        const p = byRepo.get(n); return p ? '<li><a href="' + safeURL(p.url) + '" target="_blank" rel="noopener">' + esc(n) + " ↗</a></li>" : "";
      }).join("") + "</ul></article>").join("");
  }
  el.innerHTML = '<div class="discovery-intro"><h2>趋势总结 / 机制与爆发观察</h2><p>跨项目阅读共同原理，并用两个完整 7 日的样本观察近期变化。</p></div>' +
    (!clusters.length ? '<p class="scope-note">当前窗口尚未形成至少 3 个项目支撑的机制分组。以下只作为继续研究的候选方向。</p><br>' : "") +
    '<div class="discovery-grid">' + (body || '<div class="empty">暂无符合条件的机制观察。</div>') +
    '</div><p class="scope-note" style="margin-top:22px">' + esc(discovery.scope || "") +
    ' “样本内加速”要求近 7 日至少 3 个、前 7 日至少 2 个，且数量至少翻倍。</p>';
}
function renderProjects() {
  const q = state.query.trim().toLowerCase();
  let list = scopedProjects().filter(p => {
    if (state.category !== "全部" && p.category !== state.category) return false;
    return matchesQuery(p);
  });
  const sorters = {
    heat: (a, b) => b.heat_score - a.heat_score,
    stars: (a, b) => b.stars - a.stars,
    newest: (a, b) => String(b.created_at).localeCompare(String(a.created_at))
  };
  list.sort(sorters[state.sort]);
  const hint = "共 " + list.length + " 个项目" + (state.category !== "全部" ? "（赛道：" + state.category + "）" : "");
  document.getElementById("hint").textContent = hint;
  const el = document.getElementById("content");
  el.className = "grid";
  el.innerHTML = list.length
    ? list.map(projectCard).join("")
    : '<div class="empty" style="grid-column:1/-1">' + ICON.searchDim + "<div>没有符合条件的项目，换个关键词试试</div></div>";
  bindCopy(el);
  bindExpand(el);
}

/* ---------- HF 模型 ---------- */
function modelCard(m, i) {
  const cmdLabel = "粘贴到 Agent 中安装模型";
  const cmd = "huggingface-cli download " + m.id;
  const tags = (m.tags || []).slice(0, 4).map(t => '<span class="tag">' + esc(t) + "</span>").join("");
  return (
    '<article class="card" style="animation-delay:' + Math.min(i * 45, 450) + 'ms">' +
      '<div class="card-head"><div class="badges"><span class="badge-cat">🧪 ' + esc(m.task_cn || m.task || "模型") + "</span></div>" +
      '<a class="icon-btn" href="' + esc(m.url) + '" target="_blank" rel="noopener" title="在 Hugging Face 打开" aria-label="HF 链接">' + ICON.external + "</a></div>" +
      '<div class="card-title">' + esc(m.id) + "</div>" +
      '<div class="metrics"><span class="metric">' + ICON.heart + fmt(m.likes) + " likes</span>" +
        '<span class="metric">' + ICON.download + fmt(m.downloads) + " 下载</span>" +
        '<span class="metric">📅 ' + esc(m.created_at) + "</span></div>" +
      (tags ? '<div class="tag-row">' + tags + "</div>" : "") +
      '<div class="cmd-box"><span class="prompt-hint">' + cmdLabel + "</span>" +
        '<span class="cmd-text" title="' + esc(cmd) + '">' + esc(cmd) + "</span>" +
        '<button class="copy-btn" data-cmd="' + esc(cmd) + '">' + ICON.copy + "复制</button></div>" +
    "</article>"
  );
}
function renderModels() {
  const q = state.query.trim().toLowerCase();
  const list = hfModels.filter(inSelectedWindow)
    .filter(m => !q || [m.id, m.task_cn, (m.tags || []).join(" ")].join(" ").toLowerCase().includes(q));
  document.getElementById("hint").textContent = "共 " + list.length + " 个热门新模型";
  const el = document.getElementById("content");
  el.className = "grid";
  el.innerHTML = list.length
    ? list.map(modelCard).join("")
    : '<div class="empty" style="grid-column:1/-1">' + ICON.searchDim + "<div>没有符合条件的模型</div></div>";
  bindCopy(el);
}

/* ---------- HN 热议 ---------- */
function renderHN() {
  const q = state.query.trim().toLowerCase();
  const list = hnStories.filter(inSelectedWindow)
    .filter(s => !q || [s.title, s.url].join(" ").toLowerCase().includes(q));
  document.getElementById("hint").textContent = "共 " + list.length + " 条社区热议";
  const el = document.getElementById("content");
  el.className = "list";
  el.innerHTML = list.length ? list.map((s, i) =>
    '<div class="row" style="animation-delay:' + Math.min(i * 40, 400) + 'ms">' +
      '<div class="score"><div class="pts">' + fmt(s.points) + '</div><div class="cap">points</div></div>' +
      '<div class="body"><a class="title" href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.title) + "</a>" +
        '<div class="meta-line">' + fmt(s.num_comments) + " 条讨论 · " +
        '<a href="' + esc(s.hn_url) + '" target="_blank" rel="noopener">HN 讨论页</a> · ' +
        '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">原文链接</a></div></div>' +
      '<a class="icon-btn" href="' + esc(s.hn_url) + '" target="_blank" rel="noopener" title="打开讨论">' + ICON.comment + "</a>" +
    "</div>"
  ).join("") : '<div class="empty">' + ICON.searchDim + "<div>没有符合条件的热议</div></div>";
}

/* ---------- Builder 观点：只展示来源原文，不生成观点或翻译 ---------- */
function builderTime(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false
  }).format(date) + " 北京时间";
}
function selectBuilderPosts(posts, options) {
  // SQL 等效：WHERE author/query/context filters; ORDER BY interactions DESC, created_at DESC.
  const q = options.query.trim().toLowerCase();
  const interactions = p => [p.likes, p.retweets, p.replies].reduce((sum, n) => sum + (n || 0), 0);
  return posts.filter(p => options.builderAuthor === "all" || p.handle === options.builderAuthor)
    .filter(p => !options.builderHideShort || !p.short_context)
    .filter(p => !q || [p.name, p.handle, p.bio, p.text].join(" ").toLowerCase().includes(q))
    .sort((a, b) => (options.builderSort === "engagement" ? interactions(b) - interactions(a) : 0)
      || b.created_at.localeCompare(a.created_at));
}
function builderCard(p) {
  const metric = n => n == null ? "—" : fmt(n);
  return '<article class="builder-card">' +
    '<div class="builder-author"><div><strong>' + esc(p.name) + '</strong>' +
    '<div class="builder-handle">@' + esc(p.handle) + '</div></div>' +
    '<time class="builder-time" datetime="' + esc(p.created_at) + '">' + esc(builderTime(p.created_at)) + '</time></div>' +
    '<p class="builder-bio">' + esc(p.bio) + '</p>' +
    '<p class="builder-text clamped" lang="en">' + esc(p.text) + '</p>' +
    '<div class="builder-bottom"><div class="builder-metrics">' +
    '<span>赞 ' + metric(p.likes) + '</span><span>转发 ' + metric(p.retweets) + '</span><span>回复 ' + metric(p.replies) + '</span>' +
    (p.is_quote ? '<span class="builder-tag">引用推文 · 语境见原帖</span>' : '') +
    (p.short_context ? '<span class="builder-tag">短帖 / 链接</span>' : '') +
    '</div><div class="builder-actions">' +
    '<button class="builder-expand" type="button" aria-expanded="false"><span class="builder-expand-label">展开原文</span></button>' +
    '<a href="' + esc(p.url) + '" target="_blank" rel="noopener noreferrer">查看原帖 ↗</a></div></div></article>';
}
function renderBuilders() {
  const posts = builderFeed.posts || [];
  const list = selectBuilderPosts(posts, state);
  const authors = [...new Map(posts.map(p => [p.handle, p.name])).entries()]
    .sort((a, b) => a[1].localeCompare(b[1]));
  const generated = new Date(builderFeed.generated_at);
  const stale = builderFeed.generated_at && !Number.isNaN(generated.getTime())
    && Date.now() - generated.getTime() > 36 * 3600000;
  const warning = [builderFeed.warning, stale ? "来源已超过 36 小时未更新，以下为最近一次快照。" : ""].filter(Boolean).join(" ");
  const el = document.getElementById("content");
  el.className = "builder-view";
  document.getElementById("hint").textContent = "最新每日推文快照 · 可搜索作者、原文和产品名称";
  el.innerHTML = '<section class="builder-intro"><div class="builder-kicker">FOLLOW BUILDERS / DAILY VOICES</div>' +
    '<h2>听听正在做产品的人怎么说</h2>' +
    '<p>来自 Zara Zhang 的 Follow Builders 来源名单。保留英文原文，关注一线产品、技术与行业观点。</p>' +
    '<p>名单精选，推文未经逐条精选；互动量帮助浏览，不代表观点质量。引用内容和图片请到原帖查看。</p>' +
    '<div class="builder-source"><span>来源更新：' + esc(builderTime(builderFeed.generated_at)) + '</span>' +
    '<span>看板获取：' + esc(builderTime(builderFeed.fetched_at)) + '</span>' +
    (builderFeed.lookback_hours != null ? '<span>来源回溯：' + fmt(builderFeed.lookback_hours) + ' 小时</span>' : '') +
    '<a href="https://github.com/zarazhangrui/follow-builders" target="_blank" rel="noopener noreferrer">来源与项目 ↗</a></div>' +
    (warning ? '<div class="builder-warning" role="status">' + esc(warning) + '</div>' : '') +
    '</section><div class="builder-filters"><select id="builderAuthor" aria-label="筛选 Builder">' +
    '<option value="all">全部 Builder（' + authors.length + '）</option>' +
    authors.map(([handle, name]) => '<option value="' + esc(handle) + '"' +
      (state.builderAuthor === handle ? ' selected' : '') + '>' + esc(name) + '</option>').join('') +
    '</select><select id="builderSort" aria-label="观点排序">' +
    '<option value="engagement"' + (state.builderSort === "engagement" ? ' selected' : '') + '>按互动量</option>' +
    '<option value="newest"' + (state.builderSort === "newest" ? ' selected' : '') + '>按最新发布</option></select>' +
    '<label><input id="builderHideShort" type="checkbox"' + (state.builderHideShort ? ' checked' : '') +
    '>隐藏短帖 / 纯链接（正文不足 60 字符）</label></div>' +
    '<div class="builder-count">显示 ' + list.length + ' / ' + posts.length + ' 条 · ' + authors.length + ' 位 Builder' +
    ' · 互动量 = 赞 + 转发 + 回复（来源采集时）</div>' +
    '<div class="builder-grid">' +
    (list.length ? list.map(builderCard).join('') : '<div class="empty" style="grid-column:1/-1">' +
      (posts.length ? '没有符合条件的推文，试试清空搜索或显示短帖。' : '当前没有可展示的推文，请稍后查看。') + '</div>') + '</div>';
}
// 绑定在稳定容器上；筛选和搜索重新渲染后仍然只展开被点击的卡片。
document.getElementById("content").addEventListener("click", e => {
  const button = e.target.closest(".builder-expand");
  if (!button) return;
  const text = button.closest(".builder-card").querySelector(".builder-text");
  const expanded = button.getAttribute("aria-expanded") !== "true";
  text.classList.toggle("clamped", !expanded);
  button.setAttribute("aria-expanded", String(expanded));
  button.querySelector(".builder-expand-label").textContent = expanded ? "收起原文" : "展开原文";
});
document.getElementById("content").addEventListener("change", e => {
  if (e.target.id === "builderAuthor") state.builderAuthor = e.target.value;
  else if (e.target.id === "builderSort") state.builderSort = e.target.value;
  else if (e.target.id === "builderHideShort") state.builderHideShort = e.target.checked;
  else return;
  renderBuilders();
});

/* ---------- 复制绑定 ---------- */
function bindCopy(root) {
  root.querySelectorAll(".copy-btn[data-cmd]").forEach(btn =>
    btn.addEventListener("click", () => copyText(btn.dataset.cmd, btn))
  );
}

/* 展开/收起：事件委托。在持久容器上只绑定一次，
   即使搜索/筛选/排序导致 innerHTML 重渲染，也不会重复绑定或失效。 */
let _expandBound = false;
function bindExpand(root) {
  if (_expandBound) return;
  _expandBound = true;
  root.addEventListener("click", (e) => {
    const t = e.target;
    if (!t || !t.closest) return;
    const btn = t.closest(".expand-toggle");
    if (!btn || !root.contains(btn)) return;
    const card = btn.closest(".card");
    const detail = card && card.querySelector(".detail");
    if (!detail) return;
    const isOpen = detail.classList.toggle("open");
    btn.classList.toggle("open", isOpen);
    const label = btn.querySelector(".expand-label");
    btn.setAttribute("aria-expanded", String(isOpen));
    if (label) label.textContent = isOpen ? "收起演示" : "查看演示";
  });
}

/* ---------- 视图切换 ---------- */
function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
  document.getElementById("summaryNav").classList.toggle("active", tab === "trends");
  const controls = document.getElementById("controls");
  const sortSel = document.getElementById("sort");
  controls.style.display = "flex";
  sortSel.style.display = tab === "projects" ? "" : "none";
  document.getElementById("search").placeholder = tab === "builders"
    ? "搜索 Builder、英文观点或产品名称…" : "搜索项目、用途、原理或你想解决的问题…";
  document.getElementById("search").setAttribute("aria-label", tab === "builders" ? "搜索 Builder 与推文" : "搜索项目与原理");
  document.querySelector(".window-filter").style.display = tab === "builders" ? "none" : "";
  renderChips();
  renderCurrent();
}
function renderCurrent() {
  const tab = state.tab;
  if (tab === "skills" || tab === "apps") renderFeatured(tab);
  if (tab === "trends") renderTrends();
  if (tab === "projects") renderProjects();
  if (tab === "models") renderModels();
  if (tab === "hn") renderHN();
  if (tab === "builders") renderBuilders();
}

document.querySelectorAll(".tab").forEach(t =>
  t.addEventListener("click", () => switchTab(t.dataset.tab))
);
document.getElementById("summaryNav").addEventListener("click", () => switchTab("trends"));
document.getElementById("search").addEventListener("input", e => {
  state.query = e.target.value;
  renderCurrent();
});
document.getElementById("sort").addEventListener("change", e => { state.sort = e.target.value; renderProjects(); });
document.getElementById("windowFilter").addEventListener("change", e => {
  state.windowDays = e.target.value === "full" ? "full" : Number(e.target.value);
  renderHeader();
  renderChips();
  renderCurrent();
});

renderHeader();
switchTab(location.hash === "#builders" ? "builders" : "skills");
</script>
</body>
</html>
"""


def build_payload(data: dict) -> dict:
    return {
        "window": data.get("window", {}),
        "projects": data.get("github_projects", []),
        "hf_models": data.get("hf_models", []),
        "hn_hot_stories": data.get("hn_hot_stories", []),
        "discovery": data.get("discovery", {}),
        "builder_feed": data.get("builder_feed", {}),
    }


def build_html(data: dict) -> str:
    # 外部原文可能包含 HTML 示例；转义 < 也防止 <!-- / <script> 改变 HTML 解析状态。
    payload_json = json.dumps(build_payload(data), ensure_ascii=False).replace("<", "\\u003c")
    configured_days = int(data.get("window", {}).get("days") or 90)
    # 完整采集窗口只出现一次；子窗口必须小于实际数据范围。
    options = [f'<option value="full" id="fullWindowOption">近 {configured_days} 天</option>']
    options.extend(f'<option value="{days}">近 {days} 天</option>'
                   for days in (30, 7) if days < configured_days)
    return (HTML_TEMPLATE.replace("__AIGC_WINDOW_OPTIONS__", "\n            ".join(options))
            .replace(DATA_TOKEN, payload_json))


def main():
    parser = argparse.ArgumentParser(description="AIGC 趋势看板生成器")
    parser.add_argument("--data", help="指定数据 JSON；缺省优先取固定名 aigc_data.json")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--out", help="显式指定输出文件路径（部署时可直接产出 index.html）")
    parser.add_argument("--builders", help="Builder 快照；缺省读取数据 JSON 同目录的 builder_feed.json")
    args = parser.parse_args()

    data_path = args.data or find_latest_data(args.output_dir)
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    builder_path = args.builders or os.path.join(os.path.dirname(data_path), "builder_feed.json")
    if os.path.exists(builder_path):
        with open(builder_path, "r", encoding="utf-8") as f:
            data["builder_feed"] = json.load(f)

    html = build_html(data)

    if args.out:
        out_path = args.out
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    else:
        os.makedirs(args.output_dir, exist_ok=True)
        out_path = os.path.join(args.output_dir, "aigc_dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    n_p = len(data.get("github_projects", []))
    print(f"✅ 数据源: {data_path}")
    print(f"✅ 看板已生成: {out_path}（{n_p} 个项目）")


if __name__ == "__main__":
    main()
