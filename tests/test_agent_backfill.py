import copy
import unittest

from aigc_trend_brief import enrich_translated_descriptions, translation_cache_key
from project_discovery import enrich_learning, evidence_key
from test_discovery import learning, project


class AgentCacheTests(unittest.TestCase):
    def test_agent_translation_is_reused_until_source_changes(self):
        original = {
            "full_name": "example/phone",
            "description": "Let your agent control your phone.",
            "description_zh": "让你的智能体操作手机。",
            "translation_provider": "trae-agent",
        }
        original["translation_cache_key"] = translation_cache_key(original["description"])

        def unexpected_request(*args):
            self.fail("An unchanged agent translation must not call the API.")

        current = [copy.deepcopy(original)]
        result = enrich_translated_descriptions(
            current, previous=[original], translator=unexpected_request,
        )
        self.assertEqual(result["cached"], 1)
        self.assertEqual(current[0]["description_zh"], original["description_zh"])
        self.assertEqual(current[0]["translation_provider"], "trae-agent")

        current[0]["description"] = "Control your phone and tablet."
        requests = []

        def translate_changed(text):
            requests.append(text)
            return "操作你的手机和平板。"

        result = enrich_translated_descriptions(
            current, previous=[original], translator=translate_changed,
        )
        self.assertEqual(result["cached"], 0)
        self.assertEqual(requests, ["Control your phone and tablet."])
        self.assertEqual(current[0]["description_zh"], "操作你的手机和平板。")

    def test_agent_translation_of_mixed_source_is_not_replaced_by_original(self):
        original = {
            "full_name": "example/mixed",
            "description": "UI design skill. 给智能体用的设计技能。",
            "description_zh": "供智能体使用的界面设计技能。",
            "translation_provider": "trae-agent",
        }
        original["translation_cache_key"] = translation_cache_key(original["description"])

        def unexpected_request(*args):
            self.fail("An unchanged mixed-source translation must not call the API.")

        current = [copy.deepcopy(original)]
        result = enrich_translated_descriptions(
            current, previous=[original], translator=unexpected_request,
        )
        self.assertEqual(result["cached"], 1)
        self.assertEqual(result["existing_zh"], 0)
        self.assertEqual(current[0]["description_zh"], original["description_zh"])

    def test_valid_agent_result_survives_external_model_switch(self):
        original = project()
        original.update(
            learning=learning(),
            learning_status="llm",
            learning_model="trae-assistant-session",
            learning_provider="trae-agent",
            learning_generated_at="2026-10-22T00:00:00+00:00",
        )
        original["learning_cache_key"] = evidence_key(
            original, original["learning_model"]
        )
        current = [copy.deepcopy(original)]

        def unexpected_request(*args):
            self.fail("An unchanged valid agent result must not call the API.")

        result = enrich_learning(
            current, unexpected_request, "openrouter/free",
            previous=[original], limit=90, log=lambda _: None,
        )
        self.assertEqual(result["cached"], 1)
        self.assertEqual(result["attempted"], 0)
        self.assertEqual(current[0]["learning_model"], "trae-assistant-session")
        self.assertEqual(current[0]["learning_provider"], "trae-agent")

    def test_changed_evidence_still_requires_fresh_analysis(self):
        original = project()
        original.update(learning=learning(), learning_model="trae-assistant-session")
        original["learning_cache_key"] = evidence_key(
            original, original["learning_model"]
        )
        current = [copy.deepcopy(original)]
        current[0]["evidence"][0]["text"] = "The product and its usage changed."
        result = enrich_learning(
            current, None, "openrouter/free",
            previous=[original], limit=0, log=lambda _: None,
        )
        self.assertEqual(result["cached"], 0)
        self.assertEqual(result["queued"], 1)
        self.assertNotIn("learning", current[0])


if __name__ == "__main__":
    unittest.main()
