import copy
import json
import unittest

from project_discovery import (
    extract_evidence, evidence_key, enrich_learning, validate_learning,
    growth_metrics, select_featured, validate_clusters, build_discovery,
)
from render_dashboard import build_html


def claim(text="解释", *refs):
    return {"text": text, "sources": list(refs or ("R1",))}


def project(name="owner/tool", created="2026-10-14T00:00:00Z", stars=100):
    return {"full_name": name, "name": name.split("/")[-1],
            "url": "https://github.com/" + name, "description": "Agent skill for charts",
            "stars": stars, "created_at": created, "topics": [],
            "evidence": [{"id": "R1", "heading": "Usage",
                          "url": "https://github.com/" + name + "#readme",
                          "text": "Use the chart skill to turn a table into a chart."}]}


def learning():
    return {"kind": "skill_tool", "kind_reason": claim(), "summary": claim("表格可视化技能"),
            "value": claim("把表格变成图形"), "mechanism": claim("模型规划，程序渲染"),
            "how_to": [claim("安装官方技能")],
            "demo": {"kind": "flow", "input": claim("表格"), "steps": [claim("绘图")], "output": claim("图形")}}


class EvidenceTests(unittest.TestCase):
    def test_late_quickstart_and_bounded_input(self):
        p = project()
        text = "# Tool\n" + "Introduction. " * 100 + "\n## Sponsors\n" + "Names " * 4000
        text += "\n## Quick start\nRun the official chart tool with a CSV table.\n"
        evidence = extract_evidence(p, text)
        self.assertTrue(any("Run the official" in e["text"] for e in evidence))
        self.assertLessEqual(sum(len(e["text"]) for e in evidence), 11200)
        self.assertEqual(len({e["id"] for e in evidence}), len(evidence))
        self.assertEqual(extract_evidence(p, None)[0]["id"], "D0")

    def test_reject_bad_sources_and_shape(self):
        for bad in (None, [], {"kind": []}, {"kind": "not_a_kind"}):
            self.assertIsNone(validate_learning(bad, project()["evidence"]))
        raw = learning()
        raw["summary"]["sources"] = ["R404"]
        self.assertIsNone(validate_learning(raw, project()["evidence"]))
        raw = learning()
        raw["how_to"] = "wrong shape"
        raw["demo"]["kind"] = []
        valid = validate_learning(raw, project()["evidence"])
        self.assertEqual(valid["how_to"], [])
        self.assertIsNone(valid["demo"])
        raw["summary"] = claim("当前获得 500 stars")
        self.assertIsNone(validate_learning(raw, project()["evidence"]))

    def test_usage_after_many_examples_and_autolinks_survive(self):
        text = "# Test\n" + "Intro " * 12
        for i in range(15):
            text += f"\n## Example {i}\n" + "Example description " * 10
        text += "\n## Usage\nVisit <https://example.org/docs> and run tool <path> to generate output."
        evidence = extract_evidence(project(), text)
        usage = next(e for e in evidence if e["heading"] == "Usage")
        self.assertIn("<https://example.org/docs>", usage["text"])
        self.assertIn("<path>", usage["text"])

    def test_description_only_not_deep_reading(self):
        raw = learning()
        raw["summary"]["sources"] = ["D0"]
        raw["kind_reason"]["sources"] = ["D0"]
        self.assertIsNone(validate_learning(raw, [{"id": "D0"}]))


class ModelTests(unittest.TestCase):
    def test_cache_reuse_and_evidence_change(self):
        calls = []

        def respond(system, prompt):
            calls.append(prompt)
            return json.dumps([{**learning(), "repo": "owner/tool"}])

        ps = [project()]
        result = enrich_learning(ps, respond, "model", log=lambda _: None)
        self.assertEqual(result["generated"], 1)
        self.assertIn("Use the chart skill", calls[0])
        self.assertEqual(ps[0]["learning_model"], "model")
        old = copy.deepcopy(ps)
        result = enrich_learning(ps, respond, "model", old, log=lambda _: None)
        self.assertEqual(result["cached"], 1)
        self.assertEqual(len(calls), 1)
        ps[0]["evidence"][0]["text"] += " Updated."
        enrich_learning(ps, respond, "model", old, log=lambda _: None)
        self.assertEqual(len(calls), 2)

    def test_failed_and_duplicate_responses_retry_next_time(self):
        for response in ("not json", "{}", json.dumps([{"repo": "wrong/repo"}]),
                         json.dumps([{**learning(), "repo": "owner/tool"}] * 2)):
            ps = [project()]
            result = enrich_learning(ps, lambda *_: response, "model", log=lambda _: None)
            self.assertEqual(result["failed"], 1)
            self.assertNotIn("learning_cache_key", ps[0])
        ps = [project()]
        enrich_learning(ps, None, "model", log=lambda _: None)
        self.assertEqual(ps[0]["learning_status"], "pending")

    def test_new_high_rank_not_starved_by_old_cache(self):
        old = project("owner/old", stars=100)
        old.update(learning=learning(), learning_model="model",
                   learning_cache_key=evidence_key(old, "model"))
        ps = [copy.deepcopy(old), project("owner/new", stars=500)]
        seen = []
        def reply(_, prompt):
            seen.append(prompt)
            return json.dumps([{**learning(), "repo": "owner/new"}])
        result = enrich_learning(ps, reply, "model", [old], limit=1, log=lambda _: None)
        self.assertEqual(result["cached"], 1)
        self.assertEqual(result["generated"], 1)
        self.assertEqual(len(seen), 1)

    def test_keep_session_provenance_without_remote_model(self):
        old = project()
        old.update(learning=learning(), learning_model="session",
                   learning_cache_key=evidence_key(old, "session"))
        ps = [project()]
        result = enrich_learning(ps, None, "configured-model", [old], log=lambda _: None)
        self.assertEqual(result["cached"], 1)
        self.assertEqual(ps[0]["learning_model"], "session")


class MetricsTests(unittest.TestCase):
    window = {"start": "2026-09-20", "end": "2026-10-20"}

    def test_exact_boundaries_distinct_and_future(self):
        ps = [project("o/a", "2026-10-06T00:00:00Z"),
              project("o/b", "2026-10-12T23:59:59Z"),
              project("o/c", "2026-10-13T00:00:00Z"),
              project("o/d", "2026-10-19T23:59:59Z"),
              project("o/e", "2026-10-20T00:00:00Z"),  # 不完整当日
              project("o/f", "2027-01-01T00:00:00Z"),
              project("o/g", "invalid")]
        m = growth_metrics(ps + [ps[0]], self.window)
        self.assertEqual((m["recent"], m["previous"], m["change_pct"]), (2, 2, 0.0))
        self.assertEqual(m["undated"], 1)
        self.assertEqual(m["members"], 7)
        # 时区转 UTC 后落入前一期。
        self.assertEqual(growth_metrics([project(created="2026-10-13T01:00:00+08:00")], self.window)["previous"], 1)

    def test_zero_baseline_and_short_window(self):
        ps = [project("o/" + str(i)) for i in range(4)]
        m = growth_metrics(ps, self.window)
        self.assertEqual(m["signal"], "新近涌现")
        self.assertIsNone(m["change_pct"])
        m = growth_metrics(ps, {"start": "2026-10-13", "end": "2026-10-20"})
        self.assertFalse(m["comparable"])
        self.assertIsNone(m["previous"])
        self.assertIsNone(growth_metrics(ps, {})["recent"])

    def test_acceleration_and_featured_threshold(self):
        ps = [project("o/" + str(i)) for i in range(4)]
        ps += [project("o/old" + str(i), "2026-10-08T12:00:00Z") for i in range(2)]
        m = growth_metrics(ps, self.window)
        self.assertEqual(m["signal"], "样本内加速")
        self.assertEqual(m["change_pct"], 100)
        ps += [project("o/low", stars=99), project("o/top", stars=1000)]
        self.assertEqual(select_featured(ps + [ps[0]], "skill_tool", limit=1), ["o/top"])
        self.assertNotIn("o/low", select_featured(ps, "skill_tool"))


class ClusterTests(unittest.TestCase):
    def test_members_and_sources_validated_and_metrics_recomputed(self):
        ps = [project("o/" + str(i)) for i in range(3)]
        for p in ps:
            p.update(learning=learning(), learning_status="llm")
        row = {"title": "机制", "mechanism": "共同做法", "members": [
            {"repo": p["full_name"], "why": "理由", "sources": ["R1"]} for p in ps],
            "metrics": {"recent": 99999}}
        rows = validate_clusters([row], ps, MetricsTests.window)
        self.assertEqual(rows[0]["metrics"]["recent"], 3)
        row["members"].append(row["members"][0])
        self.assertEqual(len(validate_clusters([row], ps, MetricsTests.window)[0]["members"]), 3)
        row["members"][1]["sources"] = ["R404"]
        self.assertEqual(validate_clusters([row], ps, MetricsTests.window), [])

    def test_no_key_never_labels_categories_as_mechanisms(self):
        ps = [project("o/" + str(i)) for i in range(3)]
        for p in ps: p["category"] = "Agent"
        d = build_discovery(ps, MetricsTests.window, {"model": "m"})
        self.assertEqual(d["clusters"], [])
        self.assertEqual(len(d["candidates"]), 1)

    def test_html_data_cannot_terminate_script(self):
        data = {"github_projects": [{**project(), "description": '</script><img src=x onerror="alert(1)">'}]}
        html = build_html(data)
        self.assertIn(r'<\/script><img', html)
        self.assertNotIn('</script><img src=x', html)
        self.assertNotIn("赛道通用示意", html)
        self.assertNotIn("GitHub 授权令牌", html)
        self.assertNotIn("LLM_API_KEY", html)
        self.assertNotIn("libsodium", html)
        self.assertNotIn("项目原文 · 待 AI 解读", html)
        self.assertNotIn("你能得到什么", html)
        self.assertIn("复制给 Agent 下载", html)


if __name__ == "__main__":
    unittest.main()
