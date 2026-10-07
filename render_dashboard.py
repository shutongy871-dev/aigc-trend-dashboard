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
import sys
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
<title>AIGC 前沿趋势看板</title>
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
  .window-pill {
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--accent-soft); color: #c4ccff;
    border: 1px solid rgba(124, 140, 255, 0.3);
    padding: 7px 14px; border-radius: 999px; font-size: 13px; font-weight: 600;
  }
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

  @media (max-width: 560px) {
    .grid { grid-template-columns: 1fr; }
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
        <h1>AIGC 前沿趋势看板</h1>
        <div class="subtitle">GitHub 开源项目 · Hugging Face 新模型 · Hacker News 社区热议</div>
      </div>
      <div class="window-pill" id="windowPill"></div>
    </div>
    <div class="stats" id="stats"></div>
  </header>

  <div class="toolbar">
    <div class="tabs">
      <button class="tab active" data-tab="projects">前沿项目</button>
      <button class="tab" data-tab="models">HF 新模型</button>
      <button class="tab" data-tab="hn">HN 热议</button>
    </div>
    <div class="controls" id="controls">
      <div class="search-box">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input type="text" id="search" placeholder="搜索项目名 / 简介 / 话题…">
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

  <main id="content"></main>

  <footer>
    由 <code>render_dashboard.py</code> 基于 <code>aigc_trend_brief.py</code> 采集的数据生成 · 数据均来自官方公开 API
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

const state = { tab: "projects", query: "", category: "全部", sort: "heat" };

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
  const w = DASH_DATA.window || {};
  document.getElementById("windowPill").textContent = (w.start || "?") + " ~ " + (w.end || "?");
  const surgeN = projects.filter(p => p.trend_type === "surge").length;
  const stats = [
    { num: projects.length, cls: "accent", lbl: "GitHub 前沿项目" },
    { num: hfModels.length, cls: "pink", lbl: "HF 热门新模型" },
    { num: hnStories.length, cls: "amber", lbl: "HN 社区热议" },
    { num: surgeN, cls: "", lbl: "老项目翻红" }
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
  const cats = ["全部", ...new Set(projects.map(p => p.category).filter(Boolean))];
  box.innerHTML = cats.map(c =>
    '<button class="chip' + (state.category === c ? " active" : "") + '" data-cat="' + esc(c) + '">' + esc(c) + "</button>"
  ).join("");
  box.querySelectorAll(".chip").forEach(ch =>
    ch.addEventListener("click", () => { state.category = ch.dataset.cat; renderProjects(); })
  );
}

/* ---------- 项目卡片 ---------- */
function agentCommand(p) {
  // 通用 Agent（编码/终端型）可直接执行：克隆仓库并进入目录
  return "git clone " + p.url + ".git && cd " + p.name;
}

/* 基于真实字段生成中文解释（赛道用途 + 语言 + 新旧 + stars，不臆测未证实的功能） */
const CAT_PURPOSE = {
  "视频生成": "用于文本或图像生成视频、动画等创作场景",
  "图像生成": "用于文生图、图像编辑与扩散模型相关创作",
  "语音/音乐": "用于语音合成、语音识别或音乐生成",
  "Agent/智能体": "用于构建可自主执行任务的 AI 智能体与工作流",
  "RAG/知识库": "用于检索增强生成与知识库问答",
  "多模态/视觉": "用于图文等多模态理解与视觉任务",
  "模型/推理/微调": "聚焦大语言模型的训练、推理、量化与微调",
  "AI应用/产品": "面向终端用户的 AI 应用与产品",
  "开发工具/框架": "为 AI 开发提供框架、SDK 与工具链支持",
  "其他AIGC": "属于 AIGC 相关的开源项目"
};
function zhDesc(p) {
  // 优先 LLM 逐项目中文简介；无 key 时用真实英文 description（逐项目不同）；再退回赛道口径
  if (p.summary_zh) return p.summary_zh;
  if (p.description) return p.description;
  const purpose = CAT_PURPOSE[p.category] || CAT_PURPOSE["其他AIGC"];
  return purpose + "，目前已获得 " + fmt(p.stars) + " 个 stars。";
}

/* 赛道级能力详解（典型能力，非逐项目实测；具体能力以各项目 README 为准） */
const CATEGORY_DETAIL = {
  "视频生成": {
    abilities: ["输入一段文字描述，直接生成对应画面的视频", "支持图片转视频、首尾帧控制运镜", "可生成数字人、口播、动画等多种形态", "支持多分辨率与时长，便于二次剪辑"],
    scene: "短视频创作、广告片/宣传片、课程与口播内容批量生产",
    audience: "内容创作者、营销团队、影视/动画工作室",
    demo: "video"
  },
  "图像生成": {
    abilities: ["文字生成插画、照片、海报、Logo 等图像", "支持图生图、局部重绘、风格迁移", "可挂载 LoRA 等微调模型控制画风", "批量出图，便于挑选与后期处理"],
    scene: "电商素材、营销海报、游戏原画、设计灵感探索",
    audience: "设计师、电商运营、游戏/插画从业者",
    demo: "image"
  },
  "语音/音乐": {
    abilities: ["文字转自然语音，支持多音色与情感", "语音转文字，用于会议纪要与字幕", "声音克隆与多角色配音", "根据描述生成背景音乐与音效"],
    scene: "有声书/播客制作、视频配音、智能客服、会议记录",
    audience: "音视频创作者、教育机构、客服与办公场景",
    demo: "audio"
  },
  "Agent/智能体": {
    abilities: ["用自然语言下达目标，Agent 自主拆解任务", "自动调用工具、浏览网页、读写文件并执行", "支持多步规划、记忆与失败重试", "多 Agent 可分工协作完成复杂流程"],
    scene: "自动化办公、数据分析、代码开发、研究调研",
    audience: "研发团队、运营/分析岗位、自动化爱好者",
    demo: "agent"
  },
  "RAG/知识库": {
    abilities: ["接入企业文档构建专属知识库", "提问时先检索相关资料再生成答案", "答案可标注来源，降低模型幻觉", "支持向量检索与多种文档格式解析"],
    scene: "企业问答机器人、客服知识库、制度/合同查询",
    audience: "企业 IT、知识管理与客服团队",
    demo: "rag"
  },
  "多模态/视觉": {
    abilities: ["同时理解图像与文本输入", "支持图像描述、视觉问答、OCR 识别", "可识别图表、文档、截图内容", "适用于图文混合的自动化任务"],
    scene: "票据/文档识别、图像审核、图表理解、无障碍辅助",
    audience: "企业办公、金融/政务、内容审核团队",
    demo: "vision"
  },
  "模型/推理/微调": {
    abilities: ["提供大模型的推理部署与加速能力", "支持量化、压缩以降低显存占用", "可用私有数据微调/对齐模型", "提供训练框架与评测工具链"],
    scene: "私有化部署大模型、领域模型训练、高性能推理服务",
    audience: "算法工程师、后端/基础设施团队",
    demo: "model"
  },
  "AI应用/产品": {
    abilities: ["开箱即用的对话助手或垂直场景产品", "提供网页/桌面端界面，无需写代码", "集成常用 AI 能力与工作流", "支持二次配置与团队协作"],
    scene: "日常写作问答、垂直业务助手、团队效率工具",
    audience: "终端业务用户、非技术团队",
    demo: "app"
  },
  "开发工具/框架": {
    abilities: ["封装模型调用、数据处理等通用能力", "提供 SDK / API / 脚手架快速接入 AI", "支持评测、部署、监控等工程环节", "可嵌入现有研发流程与技术栈"],
    scene: "AI 应用开发底座、模型服务网关、研发效能建设",
    audience: "研发工程师、平台与架构团队",
    demo: "tool"
  },
  "其他AIGC": {
    abilities: ["属于 AIGC 相关的开源项目", "具体能力请查看项目 README 与文档", "可克隆到本地按官方说明运行", "社区活跃，值得持续关注"],
    scene: "以项目官方介绍为准",
    audience: "对 AIGC 感兴趣的开发者",
    demo: "generic"
  }
};

/* 效果示意渲染（赛道典型输入→输出的可视化示意，非该项目真实产物） */
const GRADIENTS = [
  "linear-gradient(135deg,#ff9a6c,#ff5e8a)", "linear-gradient(135deg,#6c8eff,#9b6cff)",
  "linear-gradient(135deg,#43e97b,#38c6f9)", "linear-gradient(135deg,#fbbf24,#fb7185)",
  "linear-gradient(135deg,#0ea5e9,#22d3ee)", "linear-gradient(135deg,#a78bfa,#f0abfc)"
];
function ioBlock(tag, tagCls, content) {
  return '<div class="io-chip"><span class="tag-io ' + tagCls + '">' + tag + '</span><span class="c">' + content + "</span></div>";
}
const DEMO_RENDERERS = {
  video: () =>
    ioBlock("输入", "tag-in", "“夕阳下，一只猫走过海边沙滩，电影感运镜”") +
    '<div class="film">' + GRADIENTS.slice(0, 4).map((g, i) =>
      '<div class="frame" style="background:' + g + '">' + (i === 0
        ? '<span class="play-badge">' + ICON.play + "</span>" : "") + "</div>").join("") + "</div>" +
    ioBlock("输出", "tag-out", "约 10 秒、1080p 带运镜的视频片段"),
  image: () =>
    ioBlock("输入", "tag-in", "“赛博朋克风格的城市夜景，霓虹灯光，高清”") +
    '<div class="img-grid">' + GRADIENTS.slice(1, 5).map(g =>
      '<div class="img-tile" style="background:' + g + '"></div>').join("") + "</div>" +
    ioBlock("输出", "tag-out", "4 张候选概念图，可挑选后精修"),
  audio: () =>
    ioBlock("输入", "tag-in", "“欢迎使用本产品，今天为您介绍……”") +
    '<div class="wave">' + Array.from({ length: 22 }, (_, i) =>
      '<span style="height:' + (30 + (i * 13) % 70) + '%;animation-delay:' + (i * 0.06) + 's"></span>').join("") + "</div>" +
    ioBlock("输出", "tag-out", "自然流畅的多情感人声 / 可下载音频"),
  agent: () =>
    ioBlock("任务", "tag-in", "“帮我调研近一个月热门的开源 Agent 并汇总成表”") +
    '<div class="steps">' + ["理解目标并拆解子任务", "检索网页与开源仓库", "提取关键字段并去重", "生成结构化汇总表格"].map((s, i) =>
      '<div class="step done"><span class="num">' + (i < 3 ? ICON.check : (i + 1)) + "</span>" + s + "</div>").join("") + "</div>" +
    ioBlock("结果", "tag-out", "无需人工干预，自动产出可交付结果"),
  rag: () =>
    ioBlock("提问", "tag-in", "“公司的年假可以跨年使用吗？”") +
    '<div class="doc-chips"><span class="doc-chip">📄 考勤制度.pdf</span><span class="doc-chip">📄 休假管理办法.docx</span><span class="doc-chip">📄 HR 常见问答</span></div>' +
    ioBlock("回答", "tag-out", "根据制度第 5 条：年假可申请顺延至次年 Q1……（附来源）"),
  vision: () =>
    ioBlock("输入", "tag-in", "一张含表格的发票 / 截图 + “提取金额与日期”") +
    '<div class="doc-chips"><span class="doc-chip">🔍 图像文字识别</span><span class="doc-chip">🏷️ 内容理解</span></div>' +
    ioBlock("输出", "tag-out", "结构化字段：金额、日期、商户、类别"),
  model: () =>
    ioBlock("输入", "tag-in", "“请用三句话解释什么是向量检索”") +
    '<div class="terminal"><span class="t-green">▶</span> 加载量化模型 · 显存占用 ↓ 60%<br><span class="t-blue">▶</span> 推理中… 首 token 32ms<br><span class="t-dim">向量检索是把内容转为向量……</span><span class="caret-blink"></span></div>' +
    ioBlock("输出", "tag-out", "低延迟、低成本的模型推理结果"),
  app: () =>
    '<div class="chat-demo">' +
      '<div class="bubble user">帮我写一份产品发布通知</div>' +
      '<div class="bubble bot">好的，以下是一版发布通知草稿，你可以补充时间与亮点……</div>' +
    "</div>" +
    ioBlock("价值", "tag-out", "打开即用，无需任何代码与部署"),
  tool: () =>
    '<div class="terminal"><span class="t-blue">$ npm install</span> &amp;&amp; <span class="t-blue">deploy</span><br>' +
      '<span class="t-green">✓ 模型网关已就绪</span><br><span class="t-green">✓ 评测 / 监控已接入</span><br>' +
      '<span class="t-dim">AI 能力已嵌入你的应用</span><span class="caret-blink"></span></div>' +
    ioBlock("作用", "tag-out", "把复杂 AI 能力封装为简单的接口调用"),
  generic: () =>
    ioBlock("说明", "tag-in", "该项目的具体输入输出请参考官方 README") +
    ioBlock("建议", "tag-out", "克隆后按文档步骤运行即可体验")
};

/* ---------- 三层演示体系：真实素材 → LLM 场景 → 赛道模板 ---------- */
let _demoUid = 0;

/* 第 1 层：仓库 README 真实截图 / GIF（主图 + 缩略图，点击灯箱放大） */
function galleryHTML(imgs, uid) {
  let h = '<span class="demo-src s-real">项目 README 真实演示素材</span><div class="gallery">' +
    '<img class="demo-shot" src="' + esc(imgs[0]) + '" alt="项目演示" loading="lazy" ' +
    'onerror="onDemoImgErr(this,' + uid + ')">';
  if (imgs.length > 1) {
    h += '<div class="gal-thumbs">' + imgs.slice(1).map(u =>
      '<img class="gal-thumb" src="' + esc(u) + '" alt="演示缩略图" loading="lazy" ' +
      'onerror="onDemoImgErr(this,' + uid + ')">').join("") + "</div>";
  }
  return h + "</div>";
}

/* 第 2 层：LLM 依据真实描述还原的具体使用过程（逐项目差异化文字驱动结构渲染） */
function sceneHTML(s) {
  const head = '<span class="demo-src s-llm">AI 依据项目描述还原的使用场景（示意）</span>';
  const hl = (s.highlights && s.highlights.length)
    ? '<div class="doc-chips">' + s.highlights.map(x =>
        '<span class="doc-chip">' + esc(x) + "</span>").join("") + "</div>" : "";
  if (s.kind === "flow") {
    let b = head;
    if (s.input) b += ioBlock("输入", "tag-in", esc(s.input));
    if (s.steps && s.steps.length)
      b += '<div class="steps">' + s.steps.map((x, i) =>
        '<div class="step"><span class="num">' + (i + 1) + "</span>" + esc(x) + "</div>").join("") + "</div>";
    if (s.output) b += ioBlock("输出", "tag-out", esc(s.output));
    return b + hl;
  }
  if (s.kind === "chat") {
    let b = head + '<div class="chat-demo">';
    if (s.input) b += '<div class="bubble user">' + esc(s.input) + "</div>";
    if (s.output) b += '<div class="bubble bot">' + esc(s.output) + "</div>";
    return b + "</div>" + hl;
  }
  if (s.kind === "terminal") {
    let b = head + '<div class="terminal">';
    if (s.input) b += '<span class="t-blue">$</span> ' + esc(s.input) + "<br>";
    (s.steps || []).forEach(x => { b += '<span class="t-dim">▸</span> ' + esc(x) + "<br>"; });
    if (s.output) b += '<span class="t-green">✓</span> ' + esc(s.output);
    return b + '<span class="caret-blink"></span></div>' + hl;
  }
  // cards
  let b = head + '<div class="scene-cards">';
  if (s.input) b += '<div class="scene-card">' + esc(s.input) + "</div>";
  (s.highlights || []).forEach(x => { b += '<div class="scene-card">' + esc(x) + "</div>"; });
  if (s.output) b += '<div class="scene-card">' + esc(s.output) + "</div>";
  return b + "</div>";
}

/* 第 3 层：赛道固定模板（诚实标注非真实产物） */
function tplHTML(demoKey) {
  return '<span class="demo-src">赛道通用示意（非该项目真实产物）</span>' +
    (DEMO_RENDERERS[demoKey] || DEMO_RENDERERS.generic)();
}

/* 组装分层 demo：三层 DOM 均构建，初始只显示应得层；
   真实图全部加载失败时由 onDemoImgErr 自动降级，无需重渲染。 */
function demoBox(p) {
  const uid = ++_demoUid;
  const d = CATEGORY_DETAIL[p.category] || CATEGORY_DETAIL["其他AIGC"];
  const imgs = (p.demo_images && p.demo_images.length) ? p.demo_images : null;
  const scene = (!imgs && p.demo_scene) ? p.demo_scene : null;
  let layers = "";
  if (imgs) layers += '<div class="demo-layer" id="dmg-' + uid + '">' + galleryHTML(imgs, uid) + "</div>";
  if (scene) layers += '<div class="demo-layer" id="dms-' + uid + '" hidden>' + sceneHTML(scene) + "</div>";
  layers += '<div class="demo-layer" id="dmt-' + uid + '"' + ((imgs || scene) ? " hidden" : "") + ">" +
    tplHTML(d.demo) + "</div>";
  return '<div class="demo-box" id="dmbox-' + uid + '">' + layers + "</div>";
}

/* 真实图加载失败：隐藏单张；整层全部失败 → 落到场景层或模板层 */
function onDemoImgErr(img, uid) {
  img.style.display = "none";
  const gal = document.getElementById("dmg-" + uid);
  if (!gal) return;
  const all = gal.querySelectorAll("img");
  if ([].every.call(all, x => x.style.display === "none")) {
    gal.hidden = true;
    const next = document.getElementById("dms-" + uid) || document.getElementById("dmt-" + uid);
    if (next) next.hidden = false;
  }
}

/* 展开面板：连贯的能力说明 + 真实元信息 + 效果示意 */
function detailPanel(p) {
  const demo = demoBox(p);

  // 能力区（单一、连贯，不拼凑无关内容）：
  //  有 LLM 中文能力 -> 逐条要点；
  //  无 key -> 只展示项目官方描述这一段“项目自述”，不再塞 README/话题等无关句子
  let abilityHTML, metaHTML;
  if (p.abilities_zh && p.abilities_zh.length) {
    abilityHTML = "<ul class=\"ability-list\">" + p.abilities_zh.map(a =>
      '<li><span class="tick">' + ICON.check + "</span>" + esc(a) + "</li>").join("") + "</ul>";
    metaHTML =
      '<div class="meta-grid">' +
        '<div class="meta-cell"><div class="k">典型使用场景</div><div class="v">' + esc(p.scene_zh || "—") + "</div></div>" +
        '<div class="meta-cell"><div class="k">适合人群</div><div class="v">' + esc(p.audience_zh || "—") + "</div></div>" +
      "</div>";
  } else {
    abilityHTML =
      '<div class="self-desc">' +
        esc(p.description ? p.description : "该项目暂未提供官方描述，可克隆后查看仓库文档了解其能力。") +
      "</div>" +
      '<div class="self-note">' + ICON.info + "项目官方描述 · 配置 LLM_API_KEY 后可生成逐项目中文核心能力</div>";
    metaHTML =
      '<div class="meta-grid">' +
        '<div class="meta-cell"><div class="k">主语言</div><div class="v">' + esc(p.language || "未知") + "</div></div>" +
        '<div class="meta-cell"><div class="k">创建时间</div><div class="v">' + esc(String(p.created_at || "—").slice(0, 10)) + "</div></div>" +
      "</div>";
  }

  return (
    '<div class="detail">' +
      "<div><h4>✦ 核心能力</h4>" + abilityHTML + "</div>" +
      metaHTML +
      '<div><h4>✦ 效果示意</h4><div class="demo">' + demo +
        '<div class="demo-note">' + ICON.info + "示意图为该赛道典型输入→输出，非此项目真实产物，实际效果以项目为准</div>" +
      "</div></div>" +
    "</div>"
  );
}
function projectCard(p, i) {
  const cmdLabel = "粘贴到 Agent 中克隆项目";
  const tags = (p.topics || []).slice(0, 4).map(t => '<span class="tag">' + esc(t) + "</span>").join("");
  const hn = p.hn_points
    ? '<span class="metric"><a href="' + esc(p.hn_url) + '" target="_blank" rel="noopener">' + ICON.comment + fmt(p.hn_points) + " / " + fmt(p.hn_comments) + " 评论</a></span>"
    : "";
  const cmd = agentCommand(p);
  return (
    '<article class="card" style="animation-delay:' + Math.min(i * 45, 450) + 'ms">' +
      '<div class="card-head"><div class="badges">' +
        '<span class="badge-cat">' + (p.category_emoji || "📦") + " " + esc(p.category || "其他") + "</span>" +
        (p.trend_type === "surge" ? '<span class="badge-surge">社区翻红</span>' : "") +
      "</div>" +
      '<a class="icon-btn" href="' + esc(p.url) + '" target="_blank" rel="noopener" title="在 GitHub 打开" aria-label="GitHub 链接">' + ICON.github + "</a></div>" +
      '<div class="card-title">' + esc(p.full_name) + "</div>" +
      '<div class="card-desc">' + zhDesc(p) + "</div>" +
      (p.summary_zh && p.description
        ? '<div class="card-desc-en" title="' + esc(p.description) + '">' + esc(p.description) + "</div>"
        : "") +
      '<div class="metrics">' +
        '<span class="metric">' + ICON.star + fmt(p.stars) + "</span>" +
        '<span class="metric">' + ICON.fork + fmt(p.forks) + "</span>" +
        hn +
        (p.language ? '<span class="metric"><span class="lang-dot"></span>' + esc(p.language) + "</span>" : "") +
      "</div>" +
      (tags ? '<div class="tag-row">' + tags + "</div>" : "") +
      '<button class="expand-toggle"><span class="chev">' + ICON.chevron + '</span><span class="expand-label">查看能力与效果示意</span></button>' +
      detailPanel(p) +
      '<div class="cmd-box"><span class="prompt-hint">' + cmdLabel + "</span>" +
        '<span class="cmd-text" title="' + esc(cmd) + '">' + esc(cmd) + "</span>" +
        '<button class="copy-btn" data-cmd="' + esc(cmd) + '">' + ICON.copy + "复制</button>" +
      "</div>" +
    "</article>"
  );
}
function renderProjects() {
  const q = state.query.trim().toLowerCase();
  let list = projects.filter(p => {
    if (state.category !== "全部" && p.category !== state.category) return false;
    if (!q) return true;
    const hay = [p.full_name, p.description, p.language, (p.topics || []).join(" ")].join(" ").toLowerCase();
    return hay.includes(q);
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
  const list = hfModels.filter(m => !q || [m.id, m.task_cn, (m.tags || []).join(" ")].join(" ").toLowerCase().includes(q));
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
  const list = hnStories.filter(s => !q || [s.title, s.url].join(" ").toLowerCase().includes(q));
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

/* ---------- 复制绑定 ---------- */
function bindCopy(root) {
  root.querySelectorAll(".copy-btn").forEach(btn =>
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
    if (label) label.textContent = isOpen ? "收起能力与效果示意" : "查看能力与效果示意";
  });
}

/* ---------- 灯箱：点击真实素材放大（document 委托一次，重渲染不失效） ---------- */
const lightbox = document.createElement("div");
lightbox.className = "lightbox";
lightbox.innerHTML = '<img alt="演示大图">';
document.body.appendChild(lightbox);
lightbox.addEventListener("click", () => lightbox.classList.remove("open"));
document.addEventListener("keydown", e => { if (e.key === "Escape") lightbox.classList.remove("open"); });
document.addEventListener("click", (e) => {
  const t = e.target;
  if (t && t.closest && t.closest(".demo-shot, .gal-thumb")) {
    lightbox.querySelector("img").src = t.currentSrc || t.src;
    lightbox.classList.add("open");
  }
});

/* ---------- 视图切换 ---------- */
function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === tab));
  const controls = document.getElementById("controls");
  const sortSel = document.getElementById("sort");
  controls.style.display = "flex";
  sortSel.style.display = tab === "projects" ? "" : "none";
  renderChips();
  if (tab === "projects") renderProjects();
  if (tab === "models") renderModels();
  if (tab === "hn") renderHN();
}

document.querySelectorAll(".tab").forEach(t =>
  t.addEventListener("click", () => switchTab(t.dataset.tab))
);
document.getElementById("search").addEventListener("input", e => {
  state.query = e.target.value;
  if (state.tab === "projects") renderProjects();
  else if (state.tab === "models") renderModels();
  else renderHN();
});
document.getElementById("sort").addEventListener("change", e => { state.sort = e.target.value; renderProjects(); });

renderHeader();
renderChips();
renderProjects();
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
    }


def main():
    parser = argparse.ArgumentParser(description="AIGC 趋势看板生成器")
    parser.add_argument("--data", help="指定数据 JSON；缺省优先取固定名 aigc_data.json")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--out", help="显式指定输出文件路径（部署时可直接产出 index.html）")
    args = parser.parse_args()

    data_path = args.data or find_latest_data(args.output_dir)
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    payload_json = json.dumps(build_payload(data), ensure_ascii=False)
    # JSON 内不含 </script> 的安全转义，防止内嵌脚本被提前闭合
    payload_json = payload_json.replace("</", "<\\/")
    html = HTML_TEMPLATE.replace(DATA_TOKEN, payload_json)

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
