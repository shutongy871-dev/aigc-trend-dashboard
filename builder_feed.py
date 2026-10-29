#!/usr/bin/env python3
"""Download Follow Builders' public X snapshot. No Agent or model calls."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

FEED_URL = "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json"
SOURCE_URL = "https://github.com/zarazhangrui/follow-builders"
MAX_BYTES = 4 * 1024 * 1024


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def normalize_feed(raw, now=None):
    """Preserve source text and metrics; discard unsafe/malformed entries, dedupe IDs."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(raw, dict) or not isinstance(raw.get("x"), list):
        raise ValueError("Expected an x array")
    generated = timestamp(raw.get("generatedAt"))
    if generated > now and (generated - now).total_seconds() > 300:
        raise ValueError("Source timestamp is in the future")
    errors = raw.get("errors") or []
    if not isinstance(errors, list):
        raise ValueError("Invalid source errors")
    posts, seen, skipped, total = [], set(), 0, 0
    for author in raw["x"]:
        if not isinstance(author, dict) or not isinstance(author.get("tweets"), list):
            raise ValueError("Invalid author/tweets")
        handle = author.get("handle")
        if not isinstance(handle, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle):
            raise ValueError("Invalid author handle")
        for tweet in author["tweets"]:
            total += 1
            if not isinstance(tweet, dict):
                skipped += 1
                continue
            tweet_id = str(tweet.get("id") or "")
            text = tweet.get("text")
            url = tweet.get("url")
            match = re.fullmatch(
                r"https://(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})/status/([0-9]+)",
                url or "") if isinstance(url, str) else None
            try:
                created = timestamp(tweet.get("createdAt"))
            except (ValueError, TypeError):
                skipped += 1
                continue
            if (not match or match[1].lower() != handle.lower() or match[2] != tweet_id
                    or not isinstance(text, str) or not text.strip()
                    or created > generated):
                skipped += 1
                continue
            if tweet_id in seen:
                continue
            seen.add(tweet_id)
            clean_text = html.unescape(text)
            substantive = re.sub(r"https?://\S+|@[A-Za-z0-9_]+", "", clean_text).strip()
            posts.append({
                "id": tweet_id, "name": str(author.get("name") or handle),
                "handle": handle, "bio": html.unescape(str(author.get("bio") or "")),
                "text": clean_text, "url": url, "created_at": created.isoformat(),
                "likes": count(tweet.get("likes")), "retweets": count(tweet.get("retweets")),
                "replies": count(tweet.get("replies")), "is_quote": bool(tweet.get("isQuote")),
                # A transparent reading aid, not a relevance or quality judgment.
                "short_context": len(substantive) < 60,
            })
    if not posts and (errors or total or raw["x"]):
        raise ValueError("Source has no usable posts")
    posts.sort(key=lambda p: (p["created_at"], p["id"]), reverse=True)
    warning = []
    if errors:
        warning.append("上游报告部分采集异常，当前内容可能不完整。")
    if skipped:
        warning.append(f"已跳过 {skipped} 条字段不完整或链接无效的记录。")
    return {
        "source_url": SOURCE_URL, "feed_url": FEED_URL,
        "generated_at": generated.isoformat(), "fetched_at": now.isoformat(),
        "last_attempt_at": now.isoformat(),
        "lookback_hours": count(raw.get("lookbackHours")),
        "status": "partial" if warning else "ok", "warning": " ".join(warning),
        "posts": posts,
    }


def fetch_feed():
    request = Request(FEED_URL, headers={"User-Agent": "aigc-trend-dashboard/1.0"})
    with urlopen(request, timeout=30) as response:
        content = response.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("Feed exceeds size limit")
    return json.loads(content)


def refresh(path, fetch=fetch_feed, now=None):
    now = now or datetime.now(timezone.utc)
    path = Path(path)
    previous = None
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(previous, dict) or not isinstance(previous.get("posts"), list):
                previous = None
        except (OSError, ValueError):
            print("Saved Builder snapshot is unreadable; fetching a new snapshot.", file=sys.stderr)
    try:
        result = normalize_feed(fetch(), now)
        if previous and previous.get("generated_at"):
            if timestamp(result["generated_at"]) < timestamp(previous["generated_at"]):
                raise ValueError("Source snapshot is older than the saved snapshot")
    except Exception as error:
        print(f"Builder feed refresh failed: {error}", file=sys.stderr)
        result = dict(previous or {
            "source_url": SOURCE_URL, "feed_url": FEED_URL, "posts": [],
            "generated_at": None, "fetched_at": None, "lookback_hours": None,
        })
        result.update(
            status="error", last_attempt_at=now.isoformat(),
            warning="本次更新失败，保留上次成功获取的内容。" if previous else
                    "暂时无法获取来源内容，请稍后再试。",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="output/builder_feed.json")
    args = parser.parse_args()
    result = refresh(args.out)
    print(f"Builder feed: {result['status']}, {len(result['posts'])} posts → {args.out}")
    if result["status"] != "ok":
        print(f"::warning::{result['warning']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
