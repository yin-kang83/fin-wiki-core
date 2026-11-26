# -*- coding: utf-8 -*-
"""Fin-Wiki LLM adapter 边界测试（不联网）。"""
import json
import unittest

from fin_wiki.adapters import (
    AdapterError, CallableAdapter, OpenAICompatibleAdapter, extract_json,
)


class AdapterBoundaryTest(unittest.TestCase):
    def test_extract_json_fenced(self):
        value = extract_json('```json\n{"a": 1}\n```')
        self.assertEqual(value, {"a": 1})

    def test_retry_after_invalid_then_valid(self):
        calls = {"n": 0}

        def call(_text):
            calls["n"] += 1
            if calls["n"] == 1:
                return "not json"
            return json.dumps({"ok": True})

        adapter = CallableAdapter(call, retries=1, backoff=0.01)
        self.assertEqual(adapter.parse("x"), {"ok": True})
        self.assertEqual(calls["n"], 2)

    def test_timeout_raises_adapter_error(self):
        import time

        def slow(_text):
            time.sleep(0.5)
            return "{}"

        adapter = CallableAdapter(slow, timeout=0.05, retries=0)
        with self.assertRaises(AdapterError):
            adapter.parse("x")

    def test_prompt_too_long(self):
        adapter = CallableAdapter(lambda _t: "{}", max_prompt_chars=3)
        with self.assertRaises(AdapterError):
            adapter.parse("abcdef")

    def test_openai_request_build_and_response_parse(self):
        adapter = OpenAICompatibleAdapter(
            "https://example.invalid/v1", "test-key", "test-model")
        req = adapter.build_request("hello")
        self.assertTrue(req.full_url.endswith("/chat/completions"))
        self.assertIn("Bearer test-key", req.headers["Authorization"])
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["messages"][0]["content"], "hello")

    def test_worker_wraps_adapter(self):
        from fin_wiki.superagent import LLMParserWorker

        def call(_text):
            return json.dumps({"initial_cost": "1", "entries": []})

        worker = LLMParserWorker(adapter=CallableAdapter(call))
        out = worker.run({"text": "x"})
        self.assertEqual(out["parsed"]["initial_cost"], "1")


if __name__ == "__main__":
    unittest.main()

