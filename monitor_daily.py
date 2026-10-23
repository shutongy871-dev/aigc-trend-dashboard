"""Monitor the existing daily Actions workflow; no external services or secrets."""
import argparse
import datetime as dt
import json
import os
import subprocess
from urllib.parse import urlencode

BEIJING = dt.timezone(dt.timedelta(hours=8))
START_GRACE = dt.timedelta(minutes=30)
RUN_LIMIT = dt.timedelta(hours=2)
WORKFLOW = "deploy.yml"


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(day, runs, jobs, now):
    """A success requires both build and Pages deployment, not just a green run."""
    expected = dt.datetime.combine(day, dt.time(9, 5), BEIJING)
    candidates = [
        r for r in runs
        if r["event"] == "schedule" and r.get("head_branch") == "main"
        and timestamp(r["created_at"]).astimezone(BEIJING).date() == day
    ]
    run = max(candidates, key=lambda r: (r["created_at"], r.get("run_attempt", 1)),
              default=None)
    result = {"day": day.isoformat(), "expected": expected.isoformat(),
              "run": run, "started": None, "delay_minutes": None}
    if now < expected:
        return dict(result, status="not_due", alert=False)
    if run is None:
        late = now >= expected + START_GRACE
        return dict(result, status="missing" if late else "waiting", alert=late)
    run_jobs = jobs.get(run["id"], [])
    build = next((j for j in run_jobs if j["name"] == "build"), None)
    started = timestamp(build["started_at"]) if (
        build and build.get("started_at") and build["status"] != "queued") else None
    if started:
        result.update(started=started.isoformat(),
                      delay_minutes=round((started - expected).total_seconds() / 60, 1))
    if run["status"] == "completed":
        if run["conclusion"] != "success":
            return dict(result, status="failed", alert=True)
        deployed = any(j["name"] == "deploy" and j.get("conclusion") == "success"
                       for j in run_jobs)
        built = build and build.get("conclusion") == "success"
        return dict(result, status="success" if built and deployed else "not_published",
                    alert=not (built and deployed))
    if started is None:
        late = now >= expected + START_GRACE
        return dict(result, status="queued_late" if late else "queued", alert=late)
    if now - started >= RUN_LIMIT:
        return dict(result, status="timeout", alert=True)
    return dict(result, status="running", alert=False)


STATUS = {
    "not_due": "尚未到计划时间", "waiting": "等待启动",
    "missing": "未发现当日定时任务", "queued": "已创建，等待执行",
    "queued_late": "超过启动宽限时间，仍未执行", "running": "运行中",
    "timeout": "运行超过 2 小时", "failed": "执行失败或被取消",
    "not_published": "流程结束，但未成功部署 Pages", "success": "采集及 Pages 部署成功",
}


def report(result):
    run = result["run"]
    lines = [
        f"<!-- daily-monitor:{result['day']} -->",
        f"状态：**{STATUS[result['status']]}**",
        f"计划启动：北京时间 {result['day']} 09:05；启动宽限：30 分钟；运行阈值：2 小时。",
    ]
    if run:
        lines += [f"任务：[#{run['run_number']}]({run['html_url']})",
                  f"创建时间：{timestamp(run['created_at']).astimezone(BEIJING).isoformat()}",
                  f"执行结果：{run.get('conclusion') or '尚未结束'}"]
    if result["started"]:
        lines += [
            f"实际启动：{timestamp(result['started']).astimezone(BEIJING).isoformat()}",
            f"相对计划延迟：{result['delay_minutes']} 分钟。",
        ]
    if result["alert"]:
        lines.append("请打开任务日志检查；必要时在 Actions 手动触发每日采集。")
    lines += [
        "",
        "监测每小时巡检，并在任务开始/结束时更新。同一天复用此记录，成功后自动关闭。",
        "GitHub 的调度及监测本身均可能延迟。成功表示 Actions 采集与 Pages 部署成功，"
        "不代表 Vercel 已完成发布，也不验证网页数据的完整性。",
    ]
    return "\n\n".join(lines)


def api(repo, path, payload=None, paginate=False):
    command = ["gh", "api", f"repos/{repo}/{path}"]
    if paginate:
        command += ["--paginate", "--slurp"]
    if payload is not None:
        command += ["--method", "PATCH" if path.startswith("issues/") else "POST",
                    "--input", "-"]
    output = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, check=True)
    return json.loads(output.stdout)


def sync_issue(repo, result, issues):
    # Before the grace period, a missing run needs no incident record.
    if result["status"] in ("not_due", "waiting"):
        return
    marker = f"<!-- daily-monitor:{result['day']} -->"
    issue = next((i for i in issues if not i.get("pull_request")
                  and i.get("user", {}).get("login") == "github-actions[bot]"
                  and marker in (i.get("body") or "")), None)
    title = f"[每日任务监测] {result['day']} · {STATUS[result['status']]}"
    body = report(result)
    state = "closed" if result["status"] == "success" else "open"
    if issue:
        if (issue["title"], issue["body"], issue["state"]) != (title, body, state):
            api(repo, f"issues/{issue['number']}", {"title": title, "body": body,
                                                 "state": state})
    else:
        issue = api(repo, "issues", {"title": title, "body": body})
        if state == "closed":
            api(repo, f"issues/{issue['number']}", {"state": "closed"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Read status without writing Issues")
    args = parser.parse_args()
    repo = os.environ["GITHUB_REPOSITORY"]
    now = dt.datetime.now(BEIJING)
    # Check yesterday too: a late run can finish after Beijing midnight.
    days = [now.date() - dt.timedelta(days=1), now.date()]
    since = dt.date.fromisoformat(os.environ.get("MONITOR_SINCE", now.date().isoformat()))
    days = [day for day in days if day >= since]
    if not days:
        print("尚未到监测启用日期。")
        return 0
    query = urlencode({"event": "schedule", "branch": "main", "per_page": 100,
                       "created": ">=" + (days[0] - dt.timedelta(days=1)).isoformat()})
    pages = api(repo, f"actions/workflows/{WORKFLOW}/runs?{query}", paginate=True)
    runs = [r for page in pages for r in page["workflow_runs"]]
    jobs = {}
    for run in runs:
        if timestamp(run["created_at"]).astimezone(BEIJING).date() in days:
            pages = api(repo, f"actions/runs/{run['id']}/jobs?per_page=100", paginate=True)
            jobs[run["id"]] = [job for page in pages for job in page["jobs"]]
    results = [evaluate(day, runs, jobs, now) for day in days]
    summary = "\n\n---\n\n".join(report(result) for result in results)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(summary + "\n")
    if not args.dry_run:
        pages = api(repo, "issues?state=all&per_page=100", paginate=True)
        issues = [issue for page in pages for issue in page]
        for result in results:
            sync_issue(repo, result, issues)
    return 1 if any(r["alert"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
