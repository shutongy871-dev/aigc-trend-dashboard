import datetime as dt
import unittest
from unittest.mock import patch

from monitor_daily import BEIJING, evaluate, report, sync_issue


DAY = dt.date(2026, 10, 23)


def clock(hour, minute=0):
    return dt.datetime(2026, 10, 23, hour, minute, tzinfo=BEIJING)


def fixture(status="in_progress", conclusion=None, started="2026-10-23T01:06:00Z"):
    run = {"id": 42, "run_number": 8, "event": "schedule", "head_branch": "main",
           "created_at": "2026-10-23T01:05:00Z", "status": status,
           "conclusion": conclusion, "html_url": "https://example.invalid/run/42"}
    build = {"name": "build", "status": status, "started_at": started,
             "conclusion": "success" if conclusion == "success" else conclusion}
    return run, {42: [build]}


class MonitorTests(unittest.TestCase):
    def test_missing_only_alerts_after_grace(self):
        self.assertEqual(evaluate(DAY, [], {}, clock(9))["status"], "not_due")
        self.assertFalse(evaluate(DAY, [], {}, clock(9, 34))["alert"])
        self.assertEqual(evaluate(DAY, [], {}, clock(9, 35))["status"], "missing")

    def test_queued_run_timestamp_does_not_count_as_actual_start(self):
        run, jobs = fixture("queued")
        result = evaluate(DAY, [run], jobs, clock(9, 35))
        self.assertEqual(result["status"], "queued_late")
        self.assertIsNone(result["started"])

    def test_running_and_timeout_use_actual_job_start(self):
        run, jobs = fixture()
        result = evaluate(DAY, [run], jobs, clock(10))
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["delay_minutes"], 1)
        self.assertFalse(evaluate(DAY, [run], jobs, clock(11, 5))["alert"])
        self.assertEqual(evaluate(DAY, [run], jobs, clock(11, 6))["status"], "timeout")

    def test_failure_and_cancellation_alert_immediately(self):
        for conclusion in ["failure", "cancelled", "timed_out", "action_required"]:
            run, jobs = fixture("completed", conclusion)
            self.assertEqual(evaluate(DAY, [run], jobs, clock(9, 10))["status"], "failed")

    def test_green_run_with_skipped_deployment_is_not_success(self):
        run, jobs = fixture("completed", "success")
        jobs[42].append({"name": "deploy", "conclusion": "skipped"})
        self.assertEqual(evaluate(DAY, [run], jobs, clock(10))["status"], "not_published")
        jobs[42][-1]["conclusion"] = "success"
        self.assertEqual(evaluate(DAY, [run], jobs, clock(10))["status"], "success")

    def test_manual_and_push_runs_cannot_mask_missing_schedule(self):
        run, jobs = fixture("completed", "success")
        for event in ["push", "workflow_dispatch"]:
            run["event"] = event
            self.assertEqual(evaluate(DAY, [run], jobs, clock(10))["status"], "missing")

    def test_beijing_date_includes_runs_created_on_previous_utc_day(self):
        run, jobs = fixture()
        run["created_at"] = "2026-10-22T23:30:00Z"
        self.assertIsNotNone(evaluate(DAY, [run], jobs, clock(10))["run"])
        self.assertIsNone(evaluate(DAY - dt.timedelta(days=1), [run], jobs, clock(10))["run"])

    def test_rerun_recovery_uses_current_attempt(self):
        run, jobs = fixture("completed", "success")
        run["run_attempt"] = 2
        jobs[42].append({"name": "deploy", "conclusion": "success"})
        old = dict(run, id=41, created_at="2026-10-23T01:04:00Z", conclusion="failure")
        self.assertEqual(evaluate(DAY, [old, run], jobs, clock(10))["status"], "success")

    @patch("monitor_daily.api")
    def test_daily_issue_updates_deduplicates_and_closes_on_recovery(self, api):
        result = evaluate(DAY, [], {}, clock(10))
        issue = {"number": 9, "title": "old", "body": report(result), "state": "open",
                 "user": {"login": "github-actions[bot]"}}
        sync_issue("owner/repo", result, [issue])
        self.assertEqual(api.call_args.args[1], "issues/9")
        issue.update(api.call_args.args[2])
        api.reset_mock()
        sync_issue("owner/repo", result, [issue])
        api.assert_not_called()
        run, jobs = fixture("completed", "success")
        jobs[42].append({"name": "deploy", "conclusion": "success"})
        recovered = evaluate(DAY, [run], jobs, clock(10))
        sync_issue("owner/repo", recovered, [issue])
        self.assertEqual(api.call_args.args[2]["state"], "closed")

    @patch("monitor_daily.api")
    def test_success_can_create_closed_daily_record(self, api):
        api.return_value = {"number": 10}
        run, jobs = fixture("completed", "success")
        jobs[42].append({"name": "deploy", "conclusion": "success"})
        sync_issue("owner/repo", evaluate(DAY, [run], jobs, clock(10)), [])
        self.assertEqual(api.call_count, 2)
        self.assertEqual(api.call_args.args[2], {"state": "closed"})

    @patch("monitor_daily.api")
    def test_not_due_creates_no_issue(self, api):
        sync_issue("owner/repo", evaluate(DAY, [], {}, clock(9)), [])
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
