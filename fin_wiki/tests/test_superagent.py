# -*- coding: utf-8 -*-
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fin_wiki.superagent import (  # noqa: E402
    LLMParserWorker, MathOperatorWorker, Router, StateStore,
    SystemCollapseException, WorkerCrash, mock_llm,
)

CONVERT = (
    "2026年1月，A公司以1000万元取得B公司10%股权，按成本法核算，"
    "以前年度已计提减值准备100万元；2026年7月又以3000万元取得20%股权，"
    "持股30%，B公司可辨认净资产公允价值15000万元。"
)
PERIOD = "2026年B公司实现净利润2000万元，其他综合收益500万元，宣告现金股利300万元。"
REVERSAL = "2026年末，A公司拟转回以前年度长期股权投资减值准备100万元。"


class BrokenParser(LLMParserWorker):
    def run(self, task):
        raise WorkerCrash("模拟 Worker 崩溃")


class SuperAgentTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.td.name) / "s.db")

    def tearDown(self):
        self.store.close()
        self.td.cleanup()

    def _router(self, parser_factory=None, math_factory=None, retries=2):
        return Router(
            self.store,
            parser_factory or (lambda: LLMParserWorker(mock_llm)),
            math_factory or (lambda: MathOperatorWorker()),
            max_retries=retries)

    def test_full_experiment(self):
        r = self._router()
        r.submit(CONVERT)
        r.submit(PERIOD)
        r.submit(REVERSAL)
        report = r.run_pending()
        self.assertEqual(report["processed"], 2)
        self.assertEqual(report["blocked"], 1)
        state = self.store.load_state()
        self.assertEqual(str(state.carrying_amount), "5160.00")
        self.assertEqual(str(state.impairment), "100.00")
        self.assertEqual(str(state.equity_income), "600.00")
        self.assertEqual(str(state.oci_share), "150.00")
        self.assertEqual(str(state.dividend_share), "90.00")
        self.assertEqual(str(state.non_operating_income), "600.00")
        self.assertEqual(state.status, "equity")
        # 拒绝转回：没有写新快照/新事实
        n_facts = self.store.conn.execute(
            "SELECT COUNT(*) FROM facts").fetchone()[0]
        n_snaps = self.store.conn.execute(
            "SELECT COUNT(*) FROM snapshots").fetchone()[0]
        self.assertEqual(n_facts, 11)
        self.assertEqual(n_snaps, 2)

    def test_worker_replacement(self):
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            if calls["n"] == 1:
                return BrokenParser(mock_llm)
            return LLMParserWorker(mock_llm)

        r = self._router(parser_factory=factory)
        r.submit(CONVERT)
        report = r.run_pending()
        self.assertEqual(report["processed"], 1)
        self.assertEqual(report["worker_replacements"], 1)
        self.assertEqual(str(self.store.load_state().carrying_amount),
                         "4500.00")

    def test_backlog_recovery(self):
        r1 = self._router()
        r1.submit(CONVERT)
        self.assertEqual(r1.run_pending()["processed"], 1)

        r1.submit(PERIOD)
        r_bad = self._router(
            parser_factory=lambda: BrokenParser(mock_llm), retries=1)
        report = r_bad.run_pending()
        self.assertEqual(report["deferred"], 1)
        self.assertEqual(len(self.store.pending_events()), 1)
        self.assertEqual(str(self.store.load_state().carrying_amount),
                         "4500.00")

        r_good = self._router()
        report2 = r_good.run_pending()
        self.assertEqual(report2["processed"], 1)
        self.assertEqual(len(self.store.pending_events()), 0)
        self.assertEqual(str(self.store.load_state().carrying_amount),
                         "5160.00")

    def test_append_only(self):
        r = self._router()
        r.submit(CONVERT)
        self.assertEqual(r.run_pending()["processed"], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute(
                "UPDATE facts SET name='tampered' WHERE 1=1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("DELETE FROM snapshots")
        self.store.conn.rollback()

    def test_unbalanced_entries_collapse(self):
        store = self.store

        def bad_llm(text):
            d = json.loads(mock_llm(text))
            d["entries"] = [
                {"account": "长期股权投资", "debit": "4000", "credit": "0"},
                {"account": "银行存款", "debit": "0", "credit": "3000"},
            ]
            return json.dumps(d, ensure_ascii=False)

        r = self._router(parser_factory=lambda: LLMParserWorker(bad_llm))
        r.submit(CONVERT)
        report = r.run_pending()
        self.assertEqual(report["deferred"], 1)
        self.assertEqual(store.conn.execute(
            "SELECT COUNT(*) FROM facts").fetchone()[0], 0)

    def test_chain_verification_ok(self):
        r = self._router()
        r.submit(CONVERT)
        r.submit(PERIOD)
        self.assertEqual(r.run_pending()["processed"], 2)
        report = self.store.verify_chain()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["facts"], 11)
        self.assertEqual(report["snapshots"], 2)

    def test_chain_detects_tamper(self):
        r = self._router()
        r.submit(CONVERT)
        r.run_pending()
        # 模拟离线篡改：绕过触发器直接改事实
        self.store.conn.execute("DROP TRIGGER facts_no_update")
        self.store.conn.execute(
            "UPDATE facts SET name='tampered' WHERE fact_id=(SELECT MIN(fact_id) FROM facts)")
        self.store.conn.commit()
        report = self.store.verify_chain()
        self.assertFalse(report["ok"])
        self.assertTrue(report["errors"])

    def test_processed_append_only(self):
        r = self._router()
        r.submit(CONVERT)
        r.run_pending()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute("DELETE FROM processed")
        self.store.conn.rollback()

    def test_sqlite_integrity_pragmas(self):
        journal = self.store.conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy = self.store.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(str(journal).lower(), "wal")
        self.assertEqual(int(busy), 5000)

    def test_event_priority_order(self):
        low = self.store.enqueue("low", priority=0)
        high = self.store.enqueue("high", priority=10)
        pending = self.store.pending_events()
        self.assertEqual([e.event_id for e in pending], [high.event_id, low.event_id])

    def test_bad_event_does_not_block_following(self):
        def llm(text):
            data = json.loads(mock_llm(text))
            if "BAD" in text:
                data["entries"] = [
                    {"account": "长期股权投资", "debit": "4000", "credit": "0"},
                    {"account": "银行存款", "debit": "0", "credit": "3000"},
                ]
            return json.dumps(data, ensure_ascii=False)

        r = self._router(parser_factory=lambda: LLMParserWorker(llm))
        r.submit("BAD " + CONVERT)
        r.submit(CONVERT)
        report = r.run_pending()
        self.assertEqual(report["quarantined"], 1)
        self.assertEqual(report["processed"], 1)
        self.assertEqual(len(self.store.pending_events()), 0)

    def test_event_timeout_is_quarantined(self):
        import time

        def slow_llm(text):
            time.sleep(0.02)
            return mock_llm(text)

        r = self._router(parser_factory=lambda: LLMParserWorker(slow_llm))
        r.event_timeout = 0.001
        r.submit(CONVERT)
        report = r.run_pending()
        self.assertEqual(report["quarantined"], 1)
        self.assertEqual(report["processed"], 0)


if __name__ == "__main__":
    unittest.main()

