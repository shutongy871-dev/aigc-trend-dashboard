#!/usr/bin/env python3
"""Validate and merge evidence-based cards written by the active TRAE assistant.

This is deliberately NOT a model client: it never calls an external model or
generates semantic content by rules. The assistant reads the evidence and writes
each batch; this utility only freezes work, validates, merges, and checkpoints.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from project_discovery import evidence_key, select_featured, validate_learning, PROMPT_VERSION

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "output/aigc_data.json"
WORK = ROOT / ".validation/agent-backfill"
RESULTS = ROOT / "output/agent_backfill"
MODEL = "trae-assistant-session"
PROVIDER = "trae-agent"
BATCH_SIZE = 12


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def fingerprint(project):
    return hashlib.sha256(json.dumps(
        [project["full_name"], project.get("evidence", [])],
        sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()


def prepare():
    manifest_path = WORK / "manifest.json"
    if manifest_path.exists():
        return read_json(manifest_path)
    dataset = read_json(DATA)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "original.json").write_bytes(DATA.read_bytes())
    pending = [
        p for p in dataset["github_projects"]
        if not validate_learning(p.get("learning"), p.get("evidence", []))
        and any(e["id"].startswith("R") for e in p.get("evidence", []))
    ]
    pending.sort(key=lambda p: (-p.get("stars", 0), p["full_name"]))
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "batch_size": BATCH_SIZE,
        "targets": [
            {"repo": p["full_name"], "evidence_sha256": fingerprint(p)}
            for p in pending
        ],
        "total": len(pending),
        "original_ready": sum(
            bool(validate_learning(p.get("learning"), p.get("evidence", [])))
            for p in dataset["github_projects"]
        ),
    }
    write_json(manifest_path, manifest)
    RESULTS.mkdir(parents=True, exist_ok=True)
    return manifest


def inspect_batch(batch, chars=3200):
    manifest = prepare()
    dataset = read_json(WORK / "original.json")
    by_repo = {p["full_name"]: p for p in dataset["github_projects"]}
    start = (batch - 1) * BATCH_SIZE
    targets = manifest["targets"][start:start + BATCH_SIZE]
    if not targets:
        raise ValueError("No records in that batch.")
    for item in targets:
        p = by_repo[item["repo"]]
        evidence = p.get("evidence", [])
        readme = [e for e in evidence if e["id"].startswith("R")]
        allowance = max(300, chars // max(1, len(readme)))
        excerpts = [
            {"id": e["id"], "heading": e["heading"], "text": e["text"][:allowance]}
            for e in readme
        ]
        print(json.dumps({
            "repo": p["full_name"], "description": p.get("description"),
            "description_zh": p.get("description_zh"),
            "topics": p.get("topics"), "evidence": excerpts,
        }, ensure_ascii=False))


def claim(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    text, sources = value
    if isinstance(sources, str):
        sources = sources.split(",")
    return {"text": text, "sources": sources}


def normalize(row):
    result = {"kind": row["kind"], "kind_reason": claim(row["basis"])}
    for field in ("summary", "value", "audience", "outcome", "mechanism",
                  "inspiration", "limitations"):
        result[field] = claim(row.get(field))
    result["how_to"] = [claim(c) for c in row.get("how_to", [])]
    demo = row.get("demo")
    result["demo"] = None if not demo else {
        "kind": demo.get("kind", "flow"),
        "input": claim(demo["input"]),
        "steps": [claim(c) for c in demo.get("steps", [])],
        "output": claim(demo["output"]),
    }
    return result


def merge():
    manifest = prepare()
    dataset = read_json(DATA)
    by_repo = {p["full_name"]: p for p in dataset["github_projects"]}
    frozen = {x["repo"]: x["evidence_sha256"] for x in manifest["targets"]}
    completed = set()
    now = datetime.now(timezone.utc).isoformat()
    for file in sorted(RESULTS.glob("batch-*.json")):
        batch = read_json(file)
        for row in batch["items"]:
            name = row["repo"]
            if name in completed:
                raise ValueError(f"Duplicate backfill row: {name}")
            if name not in frozen or name not in by_repo:
                raise ValueError(f"Unexpected project: {name}")
            p = by_repo[name]
            if fingerprint(p) != frozen[name]:
                raise ValueError(f"Source evidence changed: {name}")
            raw = normalize(row)
            valid = validate_learning(raw, p.get("evidence", []))
            if not valid:
                raise ValueError(f"Invalid source-linked learning card: {name}")
            for field in ("summary", "value", "mechanism"):
                content = valid.get(field)
                if not content or not re.search(r"[\u3400-\u9fff]", content["text"]):
                    raise ValueError(f"Missing Chinese {field}: {name}")
            for field in ("summary", "value", "mechanism", "audience", "outcome",
                          "inspiration", "limitations"):
                if raw.get(field) and valid.get(field) != raw[field]:
                    raise ValueError(f"Truncated or rejected {field}: {name}")
            if raw.get("demo") and not valid.get("demo"):
                raise ValueError(f"Rejected demo: {name}")
            p.update(
                learning=valid, discovery_kind=valid["kind"],
                learning_status="llm", learning_model=MODEL,
                learning_provider=PROVIDER,
                learning_generated_at=p.get("learning_generated_at") or now,
                learning_cache_key=evidence_key(p, MODEL),
            )
            completed.add(name)

    translation_file = RESULTS / "translations.json"
    if translation_file.exists():
        from aigc_trend_brief import translation_cache_key
        for row in read_json(translation_file)["items"]:
            p = by_repo[row["repo"]]
            if p.get("description") != row["source"]:
                raise ValueError(f"Translation source changed: {row['repo']}")
            text = row["text"].strip()
            if not re.search(r"[\u3400-\u9fff]", text):
                raise ValueError(f"Missing Chinese translation: {row['repo']}")
            p.update(
                description_zh=text,
                translation_provider=PROVIDER,
                translation_cache_key=translation_cache_key(row["source"]),
            )

    projects = list(by_repo.values())
    statuses = Counter(p.get("learning_status", "missing") for p in projects)
    dataset["translation"] = {
        "existing_zh": sum(p.get("translation_provider") == "source" for p in projects),
        "cached": sum(
            bool(p.get("description_zh"))
            and p.get("translation_provider") in {"bing", PROVIDER}
            for p in projects
        ),
        "translated": 0,
        "failed": sum(
            bool(p.get("description")) and not p.get("description_zh")
            for p in projects
        ),
    }
    dataset["discovery"]["skills_tools"] = select_featured(projects, "skill_tool")
    dataset["discovery"]["applications"] = select_featured(projects, "application")
    dataset["discovery"]["analysis"].update({
        "model": MODEL,
        "model_enabled": True,
        "execution": "TRAE conversation; no external model API",
        "prompt_version": PROMPT_VERSION,
        "cached": manifest["original_ready"],
        "generated": len(completed),
        "ready": statuses.get("llm", 0),
        "attempted": len(completed),
        "first_attempted": len(completed),
        "retried": 0,
        "failed": 0,
        "queued": len(frozen) - len(completed),
        "failure_reasons": [],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "status": "ready" if len(completed) == len(frozen) else "partial",
    })
    write_json(DATA, dataset)
    progress = {
        "target_total": len(frozen), "completed": len(completed),
        "remaining": len(frozen) - len(completed),
        "all_project_statuses": dict(statuses),
        "batches_complete": len(list(RESULTS.glob("batch-*.json"))),
    }
    write_json(RESULTS / "progress.json", progress)
    print(json.dumps(progress, ensure_ascii=False))


def status():
    manifest = prepare()
    files = sorted(RESULTS.glob("batch-*.json"))
    completed = {row["repo"] for file in files for row in read_json(file)["items"]}
    remaining = [x["repo"] for x in manifest["targets"] if x["repo"] not in completed]
    print(json.dumps({
        "total": len(manifest["targets"]), "completed": len(completed),
        "remaining": len(remaining), "batch_size": BATCH_SIZE,
        "next_batch": next(
            (i // BATCH_SIZE + 1 for i, x in enumerate(manifest["targets"])
             if x["repo"] not in completed), None),
    }, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "inspect", "merge", "status"])
    parser.add_argument("batch", nargs="?", type=int, default=1)
    parser.add_argument("--chars", type=int, default=3200)
    args = parser.parse_args()
    if args.command == "inspect":
        inspect_batch(args.batch, chars=args.chars)
    elif args.command == "merge":
        merge()
    else:
        status()
