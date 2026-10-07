#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC 前沿趋势自动简报
=====================
采集近 N 天（默认 30 天）AIGC 领域的前沿开源项目 / 模型 / 社区热议，
输出结构化 Markdown 简报 + JSON 数据明细。

数据源（均为官方公开 API，零第三方依赖，Python 3.9+）：
  1. GitHub Search API    —— 近 30 天新建的高热度仓库
  2. Hacker News Algolia  —— 技术社区热议（points > 50）
  3. Hugging Face API     —— 近期热门新模型（likes7d 榜，近 30 天创建）

可选增强（无凭证时自动降级，不影响主流程）：
  GITHUB_TOKEN   GitHub PAT，提升 Search 限流（匿名 10 次/分钟 -> 认证 30 次/分钟）
  LLM_API_KEY    豆包方舟 / 任意 OpenAI 兼容接口，用于生成「本期趋势洞察」
  LLM_BASE_URL   默认 https://ark.cn-beijing.volces.com/api/v3
  LLM_MODEL      默认 doubao-seed-1-6-250615，可用环境变量覆盖
  HTTPS_PROXY    如需代理，按系统环境变量自动生效

用法：
  python3 aigc_trend_brief.py              # 默认近 30 天
  python3 aigc_trend_brief.py --days 7     # 指定窗口
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- #
# 配置区（口径常量，集中管理）
# --------------------------------------------------------------------------- #

WINDOW_DAYS = 30
GITHUB_MIN_STARS = 20          # topic 组仓库的最低 star
KEYWORD_MIN_STARS = 50         # 关键词组（噪声更大）提高门槛
FALLBACK_MIN_STARS = 100       # 全站兜底组门槛，客户端再过 AIGC 白名单
TOP_N_PROJECTS = 20
TOP_N_HF = 15
TOP_N_HN = 10
HN_MIN_POINTS = 50

# 注意 GitHub Search 的实际行为：限定符之间不能用 OR
# （topic:a OR topic:b / language:a OR language:b 均返回空集），
# OR 只适用于自由文本词。因此 topic 必须逐个单独查询。
# 认证模式：18 个 topic + 2 个自由文本词组 + 1 个兜底 = 21 请求（< 30/min）
GH_TOPICS = [
    "generative-ai", "aigc", "llm", "large-language-models", "llms", "agent",
    "ai-agents", "autonomous-agents", "multimodal", "rag", "diffusion",
    "text-to-image", "text-to-video", "image-generation", "stable-diffusion",
    "comfyui", "langchain", "text-to-speech",
]
# 匿名模式只取前 8 个最高价值 topic（9 请求 × 7.5s，卡在 10/min 限流线下）
GH_TOPICS_ANON = [
    "generative-ai", "aigc", "llm", "agent", "ai-agents", "multimodal",
    "rag", "diffusion",
]
# 自由文本 OR 组（每组括号内 6 个词 = 5 个 OR，符合语法上限）
GH_KEYWORD_GROUPS = [
    ["aigc", '"text-to-video"', "agentic", "comfyui", "sora", "genai"],
    ['"generative ai"', '"ai agent"', '"ai coding"', '"open-source llm"',
     '"text-to-image"', '"stable diffusion"'],
]

# HN 搜索词组（Algolia，多词默认 AND，短语带引号）
HN_QUERIES = [
    ("story", '"generative AI"'),
    ("story", '"open-source" LLM'),
    ("story", "LLM"),
    ("story", '"AI agent"'),
    ("story", "agentic AI"),
    ("story", "text-to-video AI"),
    ("story", '"stable diffusion"'),
    ("story", '"AI coding"'),
    ("story", '"Hugging Face"'),
    ("show_hn", "AI"),
]

# AIGC 强信号白名单（用于全站兜底结果 / HN 标题的相关性过滤）
AIGC_STRONG_RE = re.compile(
    r"aigc|genai|generative|\bllm\b|\bgpt\b|chatgpt|claude|gemini|qwen|llama|mistral|"
    r"agent|diffusion|comfyui|langchain|\brag\b|embedding|transformer|text-to-|"
    r"multimodal|vllm|ollama|copilot|openai|anthropic|hugging|stable.?diffusion|"
    r"vision.?language|\btts\b|\basr\b|speech|artificial intelligence|"
    r"deep learning|neural|inference|finetun|fine-tune|quantiz",
    re.IGNORECASE,
)

# 赛道分类规则：顺序敏感，首个命中即为主类（emoji, 名称, 正则）
# 所有正则均在 name+description+topics 小写文本上匹配，注意词边界防止子串误判
CATEGORIES = [
    ("🎬", "视频生成",
     r"text-to-video|image-to-video|video.?generat|generat\w*.{0,12}video|video out|"
     r"ai video|new video|videos made with|narrated.{0,20}video|sora|\bwan2|"
     r"hunyuan.?video|animate|talking.?head|digital.?human|motion film|\bfilms?\b"),
    ("🎨", "图像生成",
     r"image|diffusion|comfyui|\bflux\b|stable.?diffusion|painting|text-to-image|"
     r"img2img|\blora\b|photo|\blogo\b|design"),
    ("🎙️", "语音/音乐",
     r"speech|\btts\b|\bvoice\b|(?<!/)\baudio\b|music|\basr\b"),
    ("🤖", "Agent/智能体",
     r"agent|autonomous|\bauto\b|workflow|copilot|\bmcp\b|orchestr|agentic"),
    ("📚", "RAG/知识库",
     r"\brag\b|retriev|vector|knowledge.?base|embedding"),
    ("🖼️", "多模态/视觉",
     r"multimodal|vision.?language|\bvlm\b|\bvqa\b|\bocr\b|"
     r"\bvisual\b(?!-novel)|vision"),
    ("🧠", "模型/推理/微调",
     r"\bllm\b|large.?language|\bgpt\b|qwen|llama|mistral|pretrain|language.?model|"
     r"transformer|inference|quantiz|finetun|fine-tune|instruct|reasoning|\bmodel\b|"
     r"classifier|classification|autoregressive|decision model|decision engine"),
    ("💬", "AI应用/产品",
     r"chatbot|assistant|\bapp\b|webui|desktop|\bchat\b|saas|platform"),
    ("🛠️", "开发工具/框架",
     r"framework|\bsdk\b|toolkit|library|\bapi\b|dataset|\beval\b|observ|gateway|"
     r"deploy|\bcli\b|plugin"),
]

HF_TASK_CN = {
    "text-generation": "文本生成",
    "text2text-generation": "文本到文本",
    "text-classification": "文本分类",
    "text-ranking": "文本排序",
    "text-to-image": "文生图",
    "image-to-image": "图生图",
    "text-to-video": "文生视频",
    "image-to-video": "图生视频",
    "text-to-speech": "语音合成",
    "automatic-speech-recognition": "语音识别",
    "audio-to-audio": "音频处理",
    "image-text-to-text": "多模态理解",
    "visual-question-answering": "视觉问答",
    "any-to-any": "全模态",
    "feature-extraction": "特征/向量",
    "translation": "翻译",
    "fill-mask": "掩码预测",
}

GITHUB_API = "https://api.github.com/search/repositories"
HN_API = "https://hn.algolia.com/api/v1/search"
HF_API = "https://huggingface.co/api/models"

LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
LLM_MODEL = os.environ.get("LLM_MODEL", "doubao-seed-1-6-250615")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


# --------------------------------------------------------------------------- #
# HTTP 工具（urllib 标准库实现，自动读取系统代理）
# --------------------------------------------------------------------------- #

def _request(method, url, headers=None, body=None, timeout=30):
    # 输入：请求方法 method(GET/POST)、网址 url、请求头 headers、请求体 body、超时秒数 timeout
    # 返回值：成功时返回解析后的 JSON（dict/list）；失败时抛出 RuntimeError
    # 关键行为：组装请求 -> 最多重试 3 次，针对限流(403/429)/服务器错误(5xx)/网络异常分别等待或放弃
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        method=method,
    )
    req.add_header("User-Agent", "aigc-trend-brief/1.0")
    for k, v in (headers or {}).items():
        req.add_header(k, v)

    # 重试机制：最多 3 次。urllib 的 Request 对象可被重复发送，而本脚本全部
    # 是 GET / 查询类 POST（天然幂等），所以失败后重放同一请求是安全的。
    # 注意：下单、写入类有副作用的接口不能这样重放，可能造成重复操作。
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "ignore")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {"message": raw[:200]}

            # 限流处理
            if e.code in (403, 429):
                msg_text = payload.get("message", "")
                reset = e.headers.get("X-RateLimit-Reset")
                remaining = e.headers.get("X-RateLimit-Remaining")
                # 1) 主限流且已知 reset：只在等待时间很短（<=30s）时等
                if reset and remaining == "0":
                    wait_s = max(0, int(reset) - int(time.time())) + 1
                    if wait_s <= 30 and attempt < 2:
                        print(f"  ⏳ 限流，等待 {wait_s}s ...", flush=True)
                        time.sleep(wait_s)
                        last_err = msg_text
                        continue
                # 2) GitHub 次级限流（abuse）：短退避重试
                if "secondary rate limit" in msg_text.lower() and attempt < 2:
                    backoff = 8 * (attempt + 1)
                    print(f"  ⏳ 次级限流，退避 {backoff}s 重试 ...", flush=True)
                    time.sleep(backoff)
                    last_err = msg_text
                    continue
                # 3) 其余限流（如共享出口 IP 的 core 额度耗尽）：立即失败，
                #    交由上层跳过，不空等
                raise RuntimeError(f"HTTP {e.code}: {msg_text}") from None
            if e.code >= 500 and attempt < 2:
                time.sleep(3 * (attempt + 1))
                last_err = payload.get("message", str(e))
                continue
            raise RuntimeError(f"HTTP {e.code}: {payload.get('message', raw[:200])}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(e)
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise RuntimeError(f"网络错误: {last_err}") from None
    raise RuntimeError(f"请求失败: {last_err}")


def http_get_json(url, headers=None):
    # 输入：网址 url、可选请求头 headers
    # 返回值：GET 请求成功后解析出的 JSON
    # 关键行为：以 GET 方式调用统一请求函数 _request（用于"取数据"）
    return _request("GET", url, headers=headers)


def http_post_json(url, headers=None, body=None, timeout=60):
    # 输入：网址 url、请求头 headers、待提交的请求体 body、超时秒数 timeout(默认 60)
    # 返回值：POST 请求成功后解析出的 JSON
    # 关键行为：自动补 Content-Type: application/json，以 POST 调用 _request（用于向 LLM 提交数据）
    headers = dict(headers or {})
    headers["Content-Type"] = "application/json"
    return _request("POST", url, headers=headers, body=body, timeout=timeout)


# --------------------------------------------------------------------------- #
# Selector：分类 / 评分 纯函数（口径可复现，附 SQL 等效注释）
# --------------------------------------------------------------------------- #

def repo_text(repo):
    # 输入：单个仓库原始 dict（含 name/full_name/description/topics）
    # 返回值：拼接后的一段纯文本字符串
    # 关键行为：把名称、全名、描述、所有 topics 用空格连成一段，供相关性与分类匹配
    """拼接仓库可判文本（名称 + 描述 + topics）。"""
    return " ".join([
        repo.get("name") or "",
        repo.get("full_name") or "",
        repo.get("description") or "",
        " ".join(repo.get("topics") or []),
    ])


def is_aigc_related(text):
    # 输入：任意文本字符串 text
    # 返回值：布尔值，命中 AIGC 强信号词为 True，否则 False
    # 关键行为：用白名单正则 AIGC_STRONG_RE 搜索，判断内容是否与 AIGC 相关
    return bool(AIGC_STRONG_RE.search(text or ""))


def classify_repo(repo):
    # 输入：单个仓库 dict
    # 返回值：三元组 (emoji, 主赛道名, 附加标签列表)；无一命中时返回 ("📦","其他AIGC",[])
    # 关键行为：按 CATEGORIES 顺序匹配，首个命中为主赛道，第 2/3 命中降级为附加标签
    """
    返回 (emoji, 主类名, 附加标签)。
    机制：一个项目常同时命中多条赛道规则（如"做图像生成的 Agent"），
    因此直接用 CATEGORIES 的列表顺序作为赛道优先级 —— 首个命中即主类，
    第 2/3 个命中降级为附加标签，避免同一项目在多个榜单重复占位。
    """
    text = repo_text(repo).lower()
    matched = []
    for emoji, name, pattern in CATEGORIES:        # 顺序敏感：视频/图像在前，模型/工具在后
        if re.search(pattern, text, re.IGNORECASE):
            matched.append((emoji, name))
    if not matched:
        return ("📦", "其他AIGC", [])
    emoji, primary = matched[0]                    # 首个命中 = 主赛道
    extra = [n for _, n in matched[1:3]]           # 其余命中 = 辅助标签
    return emoji, primary, extra


def heat_score(stars, hn_points, hn_comments):
    # 输入：star 数 stars、HN 分数 hn_points、HN 评论数 hn_comments
    # 返回值：综合热度分（整数）
    # 关键行为：按 stars + hn_points*2 + hn_comments 计算；空 HN 数据按 0 处理
    """
    统一热度分（口径透明、常量可调）：
    -- SQL 等效： heat_score = stars + COALESCE(hn_points,0)*2 + COALESCE(hn_comments,0)
    -- 设计依据：HN 一点的曝光质量约等于 2 个 star；一条评论代表深度讨论，与 1 star 等权
    """
    return stars + (hn_points or 0) * 2 + (hn_comments or 0)


_GH_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)", re.IGNORECASE
)


def extract_github_repo_key(url):
    # 输入：任意 URL 字符串 url
    # 返回值：小写的 "owner/repo"；非 GitHub 链接或空值返回 None
    # 关键行为：用正则从 GitHub 链接中提取用户名与仓库名并转小写，供跨源关联
    """从任意 URL 中提取 owner/repo（小写），非 GitHub 链接返回 None。"""
    if not url:
        return None
    m = _GH_URL_RE.match(url)
    if not m:
        return None
    return f"{m.group(1).lower()}/{m.group(2).lower()}"


# --------------------------------------------------------------------------- #
# 采集器
# --------------------------------------------------------------------------- #

def fetch_github(start_date):
    # 输入：窗口起始日期 start_date（YYYY-MM-DD）
    # 返回值：去重后的 GitHub 仓库原始 dict 列表
    # 关键行为：逐 topic + 自由文本词组 + 全站兜底查询；按有无 Token 自适应认证/匿名节奏，白名单过滤
    """逐 topic + 自由文本词组 + 全站兜底；认证 / 匿名模式自适应。"""
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        topics = GH_TOPICS
        keyword_groups = GH_KEYWORD_GROUPS
        interval = 2.2                    # 认证 search 30 次/分钟
        mode = "认证(30 次/分钟)"
    else:
        topics = GH_TOPICS_ANON
        keyword_groups = []               # 匿名放弃关键词组，保限流安全
        interval = 7.5                    # 匿名 search 10 次/分钟
        mode = "匿名(10 次/分钟)"

    queries = []
    for t in topics:                       # 每个 topic 一个独立查询
        queries.append(f"created:>{start_date} stars:>{GITHUB_MIN_STARS} topic:{t}")
    for g in keyword_groups:               # 自由文本 OR：限定在名称/描述
        cond = " OR ".join(g)
        queries.append(
            f"created:>{start_date} stars:>{KEYWORD_MIN_STARS} ({cond}) in:name,description"
        )
    # 全站高 star 兜底（客户端白名单过滤）
    queries.append(f"created:>{start_date} stars:>{FALLBACK_MIN_STARS}")

    # 用 dict 承载结果、key=repo id：同一仓库可能被多个 topic 查询命中，
    # 写字典即天然去重，省掉事后再做一次 list 去重的 O(n) 遍历
    repos = {}
    print(f"[GitHub] 模式: {mode}，共 {len(queries)} 个查询", flush=True)
    for i, q in enumerate(queries, 1):
        params = urllib.parse.urlencode(
            {"q": q, "sort": "stars", "order": "desc", "per_page": 100}
        )
        data = http_get_json(f"{GITHUB_API}?{params}", headers=headers)
        items = data.get("items", [])
        kept = 0
        for item in items:
            # 兜底组结果必须过白名单；其余组也统一过一遍保证口径一致
            if not is_aigc_related(repo_text(item)):
                continue
            if item["id"] not in repos:
                repos[item["id"]] = item
                kept += 1
        print(f"  ({i}/{len(queries)}) 返回 {len(items)}，新增 {kept}，"
              f"累计 {len(repos)}", flush=True)
        if i < len(queries):
            time.sleep(interval)
    return list(repos.values())


def fetch_hackernews(start_ts):
    # 输入：窗口起始的 Unix 时间戳 start_ts（秒）
    # 返回值：按 objectID 去重后的 HN 帖子 dict 列表
    # 关键行为：用 10 个词组搜 Algolia（points>50、窗口内），客户端再用白名单过滤前缀噪声
    """多词组搜索 HN 近 30 天高分故事，按 objectID 去重。"""
    stories = {}
    print(f"[HackerNews] {len(HN_QUERIES)} 个词组，points > {HN_MIN_POINTS}",
          flush=True)
    for i, (tags, query) in enumerate(HN_QUERIES, 1):
        params = urllib.parse.urlencode({
            "query": query,
            "tags": tags,
            "numericFilters": f"created_at_i>{start_ts},points>{HN_MIN_POINTS}",
            "hitsPerPage": 50,
        })
        data = http_get_json(f"{HN_API}?{params}")
        hits = data.get("hits", [])
        new = 0
        for h in hits:
            oid = h.get("objectID")
            title = h.get("title") or ""
            # 客户端相关性：Algolia 存在前缀匹配噪声（如 aigc -> aircraft）
            if not is_aigc_related(title) and not is_aigc_related(h.get("url") or ""):
                continue
            if oid not in stories:
                stories[oid] = h
                new += 1
        print(f"  ({i}/{len(HN_QUERIES)}) {query!r}: {len(hits)} 命中，新增 {new}",
              flush=True)
        time.sleep(0.3)
    return list(stories.values())


def fetch_huggingface(start_date):
    # 输入：窗口起始日期 start_date（YYYY-MM-DD）
    # 返回值：窗口内创建、按 likes 降序排列的 HF 模型原始 dict 列表
    # 关键行为：一次取 likes7d 周榜 Top100，再用创建时间卡窗口
    """取 likes7d 榜 Top100，保留近窗口内创建的模型。"""
    params = urllib.parse.urlencode(
        {"sort": "likes7d", "direction": -1, "limit": 100}
    )
    print("[HuggingFace] 拉取 likes7d Top100 ...", flush=True)
    models = http_get_json(f"{HF_API}?{params}")
    kept = []
    for m in models:
        created = m.get("createdAt") or ""
        if created[:10] >= start_date:
            kept.append(m)
    kept.sort(key=lambda x: x.get("likes", 0), reverse=True)
    print(f"  近 {WINDOW_DAYS} 天创建且在榜: {len(kept)} 个", flush=True)
    return kept


# --------------------------------------------------------------------------- #
# 数据整合：标准化 + HN 交叉关联 + 分类评分
# --------------------------------------------------------------------------- #

def normalize_github(raw_repos):
    # 输入：GitHub 原始仓库 dict 列表 raw_repos
    # 返回值：字段统一的项目 dict 列表
    # 关键行为：只保留所需字段并预置 trend_type/source/HN 占位字段，完成标准化
    projects = []
    for r in raw_repos:
        projects.append({
            "id": r["id"],
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "url": r.get("html_url"),
            "description": (r.get("description") or "").strip(),
            "stars": r.get("stargazers_count", 0),
            "forks": r.get("forks_count", 0),
            "language": r.get("language"),
            "topics": r.get("topics") or [],
            "created_at": r.get("created_at"),
            "pushed_at": r.get("pushed_at"),
            "trend_type": "new",          # new=窗口内新发布
            "source": "github_search",
            "hn_points": 0,
            "hn_comments": 0,
            "hn_url": None,
        })
    return projects


def attach_hackernews(projects, hn_stories, start_date):
    # 输入：标准化项目列表 projects（可变，会被原地追加）、HN 帖子 hn_stories、起始日期 start_date
    # 返回值：非 GitHub 链接的 AI 热议故事列表（按 points 降序）
    # 关键行为：HN 三分支——关联已有项目/暂存未命中仓库/收非GitHub热议；再反查补全并区分 new 与 surge
    """
    HN 双向整合：
      1. 指向已有 GitHub 项目的故事 -> 写入 HN 热度；
      2. 指向集合外 GitHub 仓库的故事 -> 调 core API 反查补全（HN 反向捕获
         "近 30 天爆发的老项目" 与 "无 topic 的新项目"，补正向查询的盲区）；
      3. 其余 AI 故事 -> 社区热议列表。
    """
    by_key = {p["full_name"].lower(): p for p in projects}  # 小写键，容忍 URL 大小写差异
    hot_non_github = []
    # surge 暂存"HN 上出现、但 GitHub 正向查询没抓到"的仓库；
    # 同一仓库可能有多条 HN 故事，dict 赋值时只保留 points 最高的一条
    surge = {}          # repo_key -> 热度最高的 HN story
    linked = 0

    for h in hn_stories:
        story = {
            "title": h.get("title"),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
            "hn_url": f"https://news.ycombinator.com/item?id={h['objectID']}",
            "points": h.get("points", 0),
            "num_comments": h.get("num_comments", 0),
            "created_at": h.get("created_at"),
        }
        key = extract_github_repo_key(h.get("url"))
        target = by_key.get(key) if key else None
        if target:
            if h.get("points", 0) > target["hn_points"]:
                target["hn_points"] = story["points"]
                target["hn_comments"] = story["num_comments"]
                target["hn_url"] = story["hn_url"]
            linked += 1
        elif key:
            if key not in surge or story["points"] > surge[key]["points"]:
                surge[key] = story
        else:
            hot_non_github.append(story)

    # 反向补全：core API 认证 5000/h、匿名 60/h（共享出口 IP 常被耗尽）
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    else:
        # /rate_limit 端点本身不消耗配额，先探测再决定是否反查，避免空等
        try:
            rl = http_get_json("https://api.github.com/rate_limit", headers=headers)
            core_left = rl["resources"]["core"]["remaining"]
        except Exception:
            core_left = None          # 探测失败：乐观尝试
        if core_left is not None and core_left < len(surge):
            print(f"  ⏭️ core API 剩余 {core_left} 次 < 待补全 {len(surge)} 个，"
                  f"跳过 HN 反向补全（配置 GITHUB_TOKEN 后生效）", flush=True)
            surge = {}
    added = 0
    for key, story in surge.items():
        try:
            detail = http_get_json(
                f"https://api.github.com/repos/{urllib.parse.quote(key, safe='/')}",
                headers=headers,
            )
        except Exception as e:
            print(f"  ⚠️ 反查 {key} 失败: {e}", flush=True)
            continue
        p = normalize_github([detail])[0]
        p["trend_type"] = "new" if (p["created_at"] or "")[:10] >= start_date else "surge"
        p["source"] = "hn_surge"
        p["hn_points"] = story["points"]
        p["hn_comments"] = story["num_comments"]
        p["hn_url"] = story["hn_url"]
        projects.append(p)
        by_key[key] = p
        added += 1
        time.sleep(0.3 if GITHUB_TOKEN else 1.0)

    hot_non_github.sort(key=lambda x: x["points"], reverse=True)
    print(f"[整合] HN 关联已有项目 {linked} 次；反向补全仓库 {added} 个；"
          f"非 GitHub 的 AI 热议 {len(hot_non_github)} 条", flush=True)
    return hot_non_github


def finalize_projects(projects):
    # 输入：已整合 HN 数据的项目 dict 列表 projects
    # 返回值：同一列表（原地写入分类与热度字段后，按 heat_score 降序返回）
    # 关键行为：逐个分类、算热度分，全部算完后统一排序
    """分类 + 热度分 + 排序。"""
    for p in projects:
        emoji, category, extra = classify_repo(p)
        p["category"] = category
        p["category_emoji"] = emoji
        p["extra_tags"] = extra
        p["heat_score"] = heat_score(
            p["stars"], p["hn_points"], p["hn_comments"]
        )
    projects.sort(key=lambda x: x["heat_score"], reverse=True)
    return projects


def normalize_hf(models):
    # 输入：HF 原始模型 dict 列表 models
    # 返回值：字段统一的模型 dict 列表（仅前 TOP_N_HF 个）
    # 关键行为：翻译任务类型为中文、拼链接、剔除 region 标签、截取创建日期
    out = []
    for m in models[:TOP_N_HF]:
        task = m.get("pipeline_tag") or "—"
        out.append({
            "id": m.get("id") or m.get("modelId"),
            "url": f"https://huggingface.co/{m.get('id') or m.get('modelId')}",
            "likes": m.get("likes", 0),
            "downloads": m.get("downloads", 0),
            "task": task,
            "task_cn": HF_TASK_CN.get(task, task),
            "created_at": (m.get("createdAt") or "")[:10],
            "tags": [t for t in (m.get("tags") or []) if not t.startswith("region:")][:6],
        })
    return out


# --------------------------------------------------------------------------- #
# README 真实演示素材：抓取各仓库 README 内的 demo 图 / GIF（不走 core API 限流）
# --------------------------------------------------------------------------- #
README_CANDIDATES = ("README.md", "readme.md", "Readme.md", "README.MD", "README.rst", "docs/README.md")
_IMG_MD = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_IMG_HTML = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
_SOURCE_HTML = re.compile(r"<source[^>]+srcset=[\"']([^\"']+)[\"']", re.I)
_IMG_EXT = re.compile(r"\.(gif|png|jpe?g|webp|bmp|svg)(\?|#|$)", re.I)

# 强淘汰：徽章/赞助/社交按钮/头像等（命中即弃，不进入候选）
_BLOCK_HOST = re.compile(
    r"(buymeacoffee\.com|opencollective\.com|patreon\.com|ko-fi\.com|paypal\.com|donorbox|liberapay|"
    r"teepublic|redbubble|avatars\.githubusercontent|shields\.io|badge\.fury|badgen\.net|codecov|"
    r"coveralls|travis-ci|circleci|visitorbadge|hits\.dwyl|wakatime|forthebadge|img\.icons8|gitter|pepy\.)",
    re.I)
_BLOCK_PATH = re.compile(
    r"(favicon|badge|sponsor|donate|contributors|stargazers|/social/|/buttons?/|paypal|opencollective|"
    r"logo|/icon|/banner|/cover|/assets/static|mineru|star\.png|fork\.png|made-with)", re.I)
# 正向信号：真实演示素材
_GOOD_HINT = re.compile(
    r"(demo|example|screenshot|showcase|preview|usage|effect|/screen|result|output|compare|comparison|"
    r"hero|overview|tutorial|/states?/|screenshot)", re.I)
_DIAGRAM_HINT = re.compile(r"(schema|architecture|diagram|workflow|pipeline|framework|flow\b)", re.I)
_TRUSTED_HOST = re.compile(
    r"(raw\.githubusercontent\.com|github\.com|githubusercontent\.com|githubassets\.com|imgur\.com)", re.I)


def _fetch_readme(key, timeout=15):
    # 输入：owner/repo
    # 返回值：README 文本或 None
    # 关键行为：用 HEAD 作为分支引用，依次尝试常见 README 文件名，避开 core API
    for name in README_CANDIDATES:
        url = f"https://raw.githubusercontent.com/{key}/HEAD/{name}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(400_000).decode("utf-8", "ignore")
        except Exception:
            continue
    return None


def _score_image(url, order_idx):
    # 输入：图片绝对 URL、在 README 中的出现序号
    # 返回值：得分（<0 或低于阈值表示弃用）
    # 关键行为：GIF/demo/screenshot 加分，logo/徽章淘汰，靠前出现略加分
    if not _IMG_EXT.search(url):
        return -1
    if _BLOCK_HOST.search(url) or _BLOCK_PATH.search(url):
        return -1
    score = 0
    low = url.lower()
    if low.endswith(".gif") or ".gif?" in low or ".gif#" in low:
        score += 60
    elif low.endswith(".webp") or ".webp?" in low:
        score += 8
    elif low.endswith(".svg"):
        score -= 8
    else:
        score += 6
    if _GOOD_HINT.search(url):
        score += 25
    if _DIAGRAM_HINT.search(url):
        score += 12
    if not _TRUSTED_HOST.search(url):
        score -= 15  # 外站图（部分图床可用）降权但不直接淘汰
    score += max(0, 20 - order_idx * 3)  # 位置靠前优先
    return score


def _extract_demo_images(key, readme):
    # 输入：owner/repo、README 文本
    # 返回值：按质量排序的真实演示图 URL 列表（最多 3 张）
    base = f"https://raw.githubusercontent.com/{key}/HEAD/"
    raw_urls = _IMG_MD.findall(readme) + _IMG_HTML.findall(readme) + _SOURCE_HTML.findall(readme)
    scored = []
    seen = set()
    order = 0  # 只对“通过硬淘汰、有图片扩展名”的候选计数，避免 badge 占序号
    for u in raw_urls:
        u = u.strip()
        if not u or u.startswith(("data:", "#")):
            continue
        if not u.startswith(("http://", "https://")):
            u = base + u.lstrip("/") if u.startswith("/") else urllib.parse.urljoin(base, u)
        if u in seen:
            continue
        seen.add(u)
        if not _IMG_EXT.search(u) or _BLOCK_HOST.search(u) or _BLOCK_PATH.search(u):
            continue
        order += 1
        s = _score_image(u, order - 1)
        if s >= 5:
            scored.append((s, u))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored[:3]]


def attach_readme_demos(projects, max_workers=16):
    # 输入：项目列表（就地回填 demo_images 字段）
    # 返回值：命中真实素材的项目数
    # 关键行为：多线程抓取 README，解析/打分/排序；失败项目不回填，交由后续 LLM/模板兜底
    if not projects:
        return 0
    def work(p):
        readme = _fetch_readme(p["full_name"])
        if not readme:
            return p["full_name"], []
        return p["full_name"], _extract_demo_images(p["full_name"], readme)

    hit = 0
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(work, p): p for p in projects}
        for fut in as_completed(futures):
            p = futures[fut]
            done += 1
            try:
                _, imgs = fut.result()
            except Exception:
                imgs = []
            if imgs:
                p["demo_images"] = imgs
                hit += 1
            if done % 40 == 0 or done == len(projects):
                print(f"[README] 演示素材扫描 {done}/{len(projects)}，命中 {hit}", flush=True)
    print(f"[README] 真实演示素材命中 {hit}/{len(projects)} 个项目", flush=True)
    return hit


# --------------------------------------------------------------------------- #
# Enrichment：逐项目中文能力（LLM 回填派生字段；只读源字段 description 不改动）
# --------------------------------------------------------------------------- #
def _extract_json_array(text):
    # 输入：模型原始输出 text
    # 返回值：解析出的 JSON 数组
    # 关键行为：容忍 ```json 代码块包裹或前后多余文字，定位首个 [ 到末个 ]
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = fence.group(1) if fence else text
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("响应中未找到 JSON 数组")
    return json.loads(raw[start:end + 1])


def enrich_project_abilities(projects, batch_size=25):
    # 输入：标准化后的项目列表（已含 category）
    # 返回值：无（就地回填派生字段 summary_zh / abilities_zh / scene_zh / audience_zh）
    # 关键行为：无 key 则跳过不编造；有 key 分批让模型仅依据真实 description/topics 生成
    if not projects:
        return
    if not LLM_API_KEY:
        print("[LLM] 未配置 LLM_API_KEY，跳过逐项目能力生成（看板用原始 description 兜底）", flush=True)
        return

    system_prompt = (
        "你是一名 AIGC 开源项目编辑。只能依据用户给出的每个项目的真实字段"
        "（英文描述、赛道、话题标签）撰写中文介绍，严禁编造数据中不存在的功能、"
        "公司、指标或效果；信息不足处用稳妥、概括的说法，不要虚构细节。"
    )
    total_batches = (len(projects) + batch_size - 1) // batch_size
    filled = 0
    demo_filled = 0
    for b in range(total_batches):
        chunk = projects[b * batch_size:(b + 1) * batch_size]
        items = [{
            "i": i,
            "name": p["full_name"],
            "category": p["category"],
            "description": (p.get("description") or "")[:200],
            "topics": (p.get("topics") or [])[:8],
            "need_demo": not bool(p.get("demo_images")),
        } for i, p in enumerate(chunk)]
        user_prompt = (
            "下面是一批 AIGC 开源项目的 JSON 数据，请逐条改写。\n"
            f"{json.dumps(items, ensure_ascii=False)}\n\n"
            "严格按输入的 i 顺序，只输出一个 JSON 数组，不要 Markdown 代码块或任何解释，"
            "数组每个元素形如：\n"
            '{"i": 0, "summary_zh": "一句话中文简介，点明它具体是什么、解决什么", '
            '"abilities_zh": ["体现该项目独特之处的能力1，不要套话", '
            '"差异化能力2", "差异化能力3"], '
            '"scene_zh": "最典型的一个使用场景", "audience_zh": "最适合的一类用户"}\n'
            "要求：summary_zh 不超过 45 字；每条 abilities_zh 不超过 24 字，"
            "必须基于该项目 description 的独特信息，同赛道不同项目不得雷同；"
            "字段齐全、全部中文、可被 json.loads 直接解析。\n"
            "此外，当某条输入的 need_demo 为 true 时，该元素额外给出 demo_scene 字段，"
            "用于还原它真实的使用过程，结构为：\n"
            '{"kind": "flow|chat|terminal|cards", "input": "用户典型输入的具体内容", '
            '"steps": ["≤12字的处理步骤1", "步骤2", "步骤3"], '
            '"output": "产出的具体结果或效果", '
            '"highlights": ["关键效果点1", "关键效果点2"]}\n'
            "kind 取最贴合该项目交互形态的一种：流程编排用 flow、对话问答用 chat、"
            "命令行/推理用 terminal、功能罗列用 cards。input/output/steps/highlights "
            "必须是能被该项目 description 支撑的具体内容，禁止空泛套话与虚构数据。"
        )
        try:
            resp = http_post_json(
                f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                body={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 4000,
                },
                timeout=90,
            )
            rows = _extract_json_array(resp["choices"][0]["message"]["content"])
        except Exception as e:
            print(f"[LLM] 第 {b + 1}/{total_batches} 批能力生成失败，该批跳过: {e}", flush=True)
            continue

        by_i = {row["i"]: row for row in rows if isinstance(row, dict) and "i" in row}
        for i, p in enumerate(chunk):
            row = by_i.get(i)
            if not row:
                continue
            summary = str(row.get("summary_zh") or "").strip()
            abilities = [str(a).strip() for a in row.get("abilities_zh") or [] if str(a).strip()]
            scene = str(row.get("scene_zh") or "").strip()
            audience = str(row.get("audience_zh") or "").strip()
            if summary:
                p["summary_zh"] = summary
            if abilities:
                p["abilities_zh"] = abilities[:4]
            if scene:
                p["scene_zh"] = scene
            if audience:
                p["audience_zh"] = audience
            if summary or abilities:
                filled += 1
            # demo_scene 仅回填给无真实素材的项目（严格校验结构，避免脏数据）
            ds_raw = row.get("demo_scene")
            if isinstance(ds_raw, dict) and not p.get("demo_images"):
                kind = str(ds_raw.get("kind") or "").strip().lower()
                if kind not in ("flow", "chat", "terminal", "cards"):
                    kind = "flow"
                inp = str(ds_raw.get("input") or "").strip()
                out = str(ds_raw.get("output") or "").strip()
                steps = [str(s).strip() for s in ds_raw.get("steps") or [] if str(s).strip()]
                highs = [str(s).strip() for s in ds_raw.get("highlights") or [] if str(s).strip()]
                if inp or out or steps or highs:
                    p["demo_scene"] = {
                        "kind": kind,
                        "input": inp[:80],
                        "steps": [s[:20] for s in steps[:4]],
                        "output": out[:80],
                        "highlights": [s[:24] for s in highs[:3]],
                    }
                    demo_filled += 1
        print(f"[LLM] 逐项目能力进度 "
              f"{min((b + 1) * batch_size, len(projects))}/{len(projects)}", flush=True)

    print(f"[LLM] 逐项目中文能力已回填 {filled}/{len(projects)} 个项目（{LLM_MODEL}）", flush=True)
    if LLM_API_KEY:
        print(f"[LLM] LLM 演示场景回填 {demo_filled} 个无真实素材项目，其余走赛道模板兜底", flush=True)


# --------------------------------------------------------------------------- #
# 趋势洞察：LLM（可选） + 规则降级
# --------------------------------------------------------------------------- #

def generate_insights_llm(top_projects, surge_projects, hf_models, window_days):
    # 返回值：LLM 生成的 Markdown 洞察文本；无密钥或调用失败时返回 None
    # 关键行为：瘦身项目 + HF 模型数据 -> 构造"禁止编造、须引用数字"的 prompt -> 调 /chat/completions
    if not LLM_API_KEY:
        return None
    payload_projects = [{
        "name": p["full_name"],
        "category": p["category"],
        "stars": p["stars"],
        "hn_points": p["hn_points"],
        "description": p["description"][:140],
    } for p in top_projects]
    payload_surge = [{
        "name": p["full_name"],
        "stars": p["stars"],
        "hn_points": p["hn_points"],
    } for p in surge_projects]
    # HF 模型层信号：likes=口碑，downloads=真实使用量；与 GitHub 项目并列作为独立上下文，
    # 不强行做项目级配对（两源无公共 join key，硬关联会产生幻觉式配对）
    payload_hf = [{
        "name": m["id"],
        "task": m["task_cn"],
        "likes": m["likes"],
        "downloads": m["downloads"],
    } for m in hf_models]

    system_prompt = (
        "你是一位 AIGC 行业分析师，擅长从开源数据中识别技术赛道趋势。"
        "只基于用户提供的数据发言，禁止编造数据中不存在的项目、数字或事实。"
    )
    user_prompt = (
        f"以下是近 {window_days} 天 AIGC 领域热度 Top {len(payload_projects)} "
        f"新发布开源项目的 JSON 数据：\n{json.dumps(payload_projects, ensure_ascii=False)}\n"
    )
    if payload_surge:
        user_prompt += (
            f"\n另有近 {window_days} 天在 Hacker News 社区爆发的项目"
            f"（可能为老项目翻红）：\n{json.dumps(payload_surge, ensure_ascii=False)}\n"
        )
    if payload_hf:
        user_prompt += (
            f"\n以下是近 {window_days} 天 Hugging Face 上热门的新模型"
            f"（likes 代表社区口碑、downloads 代表真实使用量）：\n"
            f"{json.dumps(payload_hf, ensure_ascii=False)}\n"
        )
    user_prompt += (
        "\n请输出 3~5 条本期趋势洞察，要求：\n"
        "1. 使用 Markdown 无序列表，每条一句话给出趋势判断，并用括号附上数据证据"
        "（项目名/模型名 + star/HN/likes/downloads 等具体数字）；\n"
        "2. 优先归纳赛道层面的变化（如某类项目集中爆发、技术路线迁移、某类模型密集发布等），"
        "可结合 GitHub 项目热度与 Hugging Face 模型的口碑/使用量交叉印证，不要逐条复述项目；\n"
        "3. 全部中文，不要输出标题、开场白或结束语。"
    )
    try:
        resp = http_post_json(
            f"{LLM_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {LLM_API_KEY}"},
            body={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
                "max_tokens": 700,
            },
        )
        content = resp["choices"][0]["message"]["content"].strip()
        print(f"[LLM] 已生成趋势洞察（{LLM_MODEL}）", flush=True)
        return content
    except Exception as e:
        print(f"[LLM] 调用失败，降级为规则洞察: {e}", flush=True)
        return None


def generate_insights_rule(top_projects):
    # 输入：新发布 Top 项目 dict 列表 top_projects
    # 返回值：规则生成的 Markdown 洞察文本
    # 关键行为：按赛道聚合项目数/star 总和并排序，输出前 3 赛道 + HN 口碑验证
    """无 LLM 时的确定性降级口径：赛道项目数 / star 聚集度。"""
    cat_stats = {}
    for p in top_projects:
        st = cat_stats.setdefault(p["category"], {"n": 0, "stars": 0, "top": None})
        st["n"] += 1
        st["stars"] += p["stars"]
        if st["top"] is None:
            st["top"] = p
    ranked = sorted(cat_stats.items(), key=lambda kv: kv[1]["stars"], reverse=True)

    lines = []
    total_stars = sum(p["stars"] for p in top_projects)
    for cat, st in ranked[:3]:
        share = st["stars"] * 100 / total_stars if total_stars else 0
        top = st["top"]
        lines.append(
            f"- **{cat} 热度领先**：Top 榜中占据 {st['n']} 席、合计 "
            f"{st['stars']:,} stars（占头部总 star 的 {share:.0f}%），"
            f"代表项目 {top['full_name']}（⭐{top['stars']:,}）"
        )
    new_found = [p for p in top_projects if p["hn_points"] > 0]
    if new_found:
        best = max(new_found, key=lambda x: x["hn_points"])
        lines.append(
            f"- **社区口碑验证**：{len(new_found)} 个项目同时登上 Hacker News 热榜，"
            f"其中 {best['full_name']} 获 {best['hn_points']} points、"
            f"{best['hn_comments']} 条深度讨论"
        )
    lines.append(
        "> ℹ️ 本期洞察由规则口径生成。配置 `LLM_API_KEY` 后可获得大模型语义级趋势解读。"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Markdown 渲染
# --------------------------------------------------------------------------- #

def _esc(text, limit=110):
    # 输入：待放入表格的文本 text、最大长度 limit
    # 返回值：清理并截断后的字符串
    # 关键行为：合并空白、转义竖杠、超长截断加省略号，防止 Markdown 表格错乱
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.replace("|", "\\|")
    return text[:limit] + ("…" if len(text) > limit else "")


def render_markdown(projects, hf_models, hn_hot, insights, window, meta):
    # 输入：全部项目 projects、HF 模型 hf_models、HN 热议 hn_hot、洞察 insights、窗口 window、元信息 meta
    # 返回值：完整的 Markdown 简报字符串
    # 关键行为：拆分 new/surge 项目，顺序拼装洞察/主榜/赛道盘点/爆发/HF/HN/口径附录六个章节
    start, end = window
    # 主结构区分：新发布项目（主榜）与社区爆发项目（含老项目翻红）
    new_projects = [p for p in projects if p["trend_type"] == "new"]
    surge_projects = [p for p in projects if p["trend_type"] == "surge"]

    lines = [
        f"# AIGC 前沿趋势简报（{start} ~ {end}）",
        "",
        f"> 数据源：GitHub 新建仓库 · Hacker News 社区热议 · Hugging Face 热门新模型"
        f" ｜ 生成时间：{meta['generated_at']}",
        "",
        "## 一、本期趋势洞察",
        "",
        insights,
        "",
        f"## 二、Top {min(TOP_N_PROJECTS, len(new_projects))} 新发布前沿项目",
        "",
        "| # | 项目 | 赛道 | 语言 | ⭐ Stars | HN 热度 | 简介 |",
        "|---|---|---|---|---:|---:|---|",
    ]

    for i, p in enumerate(new_projects[:TOP_N_PROJECTS], 1):
        hn = (f"[{p['hn_points']}]({p['hn_url']})" if p["hn_points"] else "—")
        lang = p["language"] or "—"
        lines.append(
            f"| {i} | [{p['full_name']}]({p['url']}) "
            f"| {p['category_emoji']} {p['category']} "
            f"| {lang} | {p['stars']:,} | {hn} | {_esc(p['description'])} |"
        )

    # 赛道盘点（仅新发布项目）
    lines += ["", "## 三、赛道分类盘点", ""]
    by_cat = {}
    for p in new_projects:
        by_cat.setdefault(f"{p['category_emoji']} {p['category']}", []).append(p)
    for cat, plist in sorted(by_cat.items(),
                             key=lambda kv: sum(x["heat_score"] for x in kv[1]),
                             reverse=True):
        lines.append(f"### {cat}（{len(plist)} 个）")
        for p in plist[:6]:
            tags = f" `{'` `'.join(p['extra_tags'])}`" if p["extra_tags"] else ""
            hn = f" · HN {p['hn_points']}pt" if p["hn_points"] else ""
            lines.append(
                f"- [{p['full_name']}]({p['url']}) — {_esc(p['description'], 80)}"
                f"（⭐{p['stars']:,}{hn}）{tags}"
            )
        if len(plist) > 6:
            lines.append(f"- ……另有 {len(plist) - 6} 个项目，见 JSON 明细")
        lines.append("")

    # 社区爆发（HN 反向捕获）
    lines += [
        "## 四、社区爆发项目（Hacker News 反向捕获，含老项目翻红）",
        "",
        "| # | 项目 | 创建日期 | ⭐ Stars | HN Points | 评论 | 简介 |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for i, p in enumerate(surge_projects, 1):
        created = (p["created_at"] or "")[:10]
        lines.append(
            f"| {i} | [{p['full_name']}]({p['url']}) | {created} "
            f"| {p['stars']:,} | [{p['hn_points']}]({p['hn_url']}) "
            f"| {p['hn_comments']} | {_esc(p['description'])} |"
        )
    if not surge_projects:
        lines.append("| — | 本期无 | — | — | — | — | — |")

    # Hugging Face
    lines += [
        "",
        "## 五、Hugging Face 近 30 天热门新模型",
        "",
        "| # | 模型 | 任务 | ❤️ Likes | Downloads | 发布日期 |",
        "|---|---|---|---:|---:|---|",
    ]
    for i, m in enumerate(hf_models, 1):
        lines.append(
            f"| {i} | [{m['id']}]({m['url']}) | {m['task_cn']} "
            f"| {m['likes']:,} | {m['downloads']:,} | {m['created_at']} |"
        )

    # HN 热议
    lines += [
        "",
        "## 六、Hacker News 社区热议（非 GitHub 链接）",
        "",
        "| # | 标题 | Points | 评论 | 链接 |",
        "|---|---|---:|---:|---|",
    ]
    for i, s in enumerate(hn_hot[:TOP_N_HN], 1):
        lines.append(
            f"| {i} | {_esc(s['title'], 70)} | {s['points']} "
            f"| {s['num_comments']} | [讨论]({s['hn_url']}) · [原文]({s['url']}) |"
        )

    # 口径附录
    lines += [
        "",
        "## 附录：统计口径说明",
        "",
        f"- 时间窗口：{start} ~ {end}（UTC，{meta['days']} 天）；"
        f"GitHub 正向 / HN / HF 均取窗口内 created 项目，另含 HN 反向补全的爆发项目",
        f"- GitHub：窗口内新建仓库，topic 查询 stars > {GITHUB_MIN_STARS}，"
        f"全站兜底 stars > {FALLBACK_MIN_STARS} 且经 AIGC 白名单过滤",
        f"- HN：points > {HN_MIN_POINTS}，经标题相关性过滤，按 objectID 去重；"
        f"HN 中出现但正向未捕获的 GitHub 仓库，用 core API 反查补全，"
        f"按创建时间区分为新发布 / 社区爆发",
        "- HF：likes7d 榜 Top100 中于窗口内创建的模型，按 likes 排序",
        "- 热度分口径：`heat_score = stars + hn_points*2 + hn_comments`",
        f"- 采集量：GitHub 新发布 {len(new_projects)} 个 + 社区爆发 {len(surge_projects)} 个 / "
        f"HN 热议 {meta['counts']['hn']} 条 / HF 新模型 {meta['counts']['hf']} 个",
        f"- 结构化明细：`{meta['json_name']}`",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    # 输入：无显式参数（从命令行读取 --days、--output-dir）
    # 返回值：无（副作用为生成 .md 简报与 .json 明细两个文件）
    # 关键行为：解析参数与时间窗口 -> 采集 -> 整合 -> LLM/规则洞察 -> 渲染落盘
    parser = argparse.ArgumentParser(description="AIGC 前沿趋势自动简报")
    parser.add_argument("--days", type=int, default=WINDOW_DAYS, help="回溯天数")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=args.days)
    start_date = start_dt.date().isoformat()
    end_date = now.date().isoformat()
    start_ts = int(start_dt.timestamp())

    print(f"=== AIGC 趋势简报 | 窗口 {start_date} ~ {end_date} ===", flush=True)

    # 核心调用链（数据从左向右流动）：
    #   采集  fetch_github / fetch_hackernews / fetch_huggingface
    #     ->  整合  normalize_github + attach_hackernews（HN 反向补全、关联热度）
    #     ->  评分  finalize_projects / normalize_hf（分类、热度分、标准化）
    #     ->  洞察  generate_insights_llm，失败降级 generate_insights_rule
    #     ->  落盘  render_markdown + json.dump（MD 简报 + JSON 明细）
    # 1. 采集
    raw_github = fetch_github(start_date)
    hn_stories = fetch_hackernews(start_ts)
    raw_hf = fetch_huggingface(start_date)

    # 2. 整合
    projects = normalize_github(raw_github)
    hn_hot = attach_hackernews(projects, hn_stories, start_date)
    projects = finalize_projects(projects)
    hf_models = normalize_hf(raw_hf)

    # 2.5 真实演示素材：扫描各仓库 README 的 demo 图/GIF（不走 core 限流，就地回填 demo_images）
    attach_readme_demos(projects)

    # 2.6 逐项目能力增强：有 LLM_API_KEY 时回填中文差异能力，并对无图项目生成 demo_scene；无 key 则跳过
    enrich_project_abilities(projects)

    # 3. 洞察（LLM 优先，失败降级规则；基于新发布项目 + 爆发项目上下文）
    new_projects = [p for p in projects if p["trend_type"] == "new"]
    surge_projects = [p for p in projects if p["trend_type"] == "surge"]
    insights = generate_insights_llm(
        new_projects[:TOP_N_PROJECTS], surge_projects, hf_models, args.days
    )
    if insights is None:
        insights = generate_insights_rule(new_projects[:TOP_N_PROJECTS])

    # 4. 输出
    os.makedirs(args.output_dir, exist_ok=True)
    md_name = "aigc_brief.md"
    json_name = "aigc_data.json"
    md_path = os.path.join(args.output_dir, md_name)
    json_path = os.path.join(args.output_dir, json_name)

    meta = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "days": args.days,
        "json_name": os.path.join(args.output_dir, json_name),
        "counts": {
            "github": len(projects),
            "hn": len(hn_stories),
            "hf": len(raw_hf),
        },
    }
    md = render_markdown(projects, hf_models, hn_hot, insights,
                         (start_date, end_date), meta)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    dataset = {
        "meta": meta,
        "window": {"start": start_date, "end": end_date, "days": args.days},
        "github_projects": projects,
        "hf_models": hf_models,
        "hn_hot_stories": hn_hot,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 简报已生成: {md_path}", flush=True)
    print(f"✅ 数据明细: {json_path}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 执行失败: {e}", file=sys.stderr)
        sys.exit(1)
