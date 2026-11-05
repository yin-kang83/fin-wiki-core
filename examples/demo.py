# -*- coding: utf-8 -*-
"""Fin-Wiki minimal demo：证据 → 双时态账本 → 一阶差分 DAG。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fin_wiki import (
    CompiledWiki,
    FactCandidate,
    FirstOrderDiffEq,
    Node,
    SourceSpan,
    TemporalFactStore,
    WikiAwareAdapter,
)
from fin_wiki.dag import ExecutionEngine

DOC = "合同第3.2节：核心设备价值为1000万元。"
TEXT = "核心设备价值为1000万元"
START = DOC.index(TEXT)


def main() -> int:
    wiki = CompiledWiki()
    wiki.add_document("contract-A", "2023", DOC)
    wiki.add_candidate(FactCandidate(
        entity="设备", key="价值", value=Decimal("1000"), unit="万元",
        valid_from=date(2023, 1, 1),
        source=SourceSpan(doc_id="contract-A", doc_version="2023",
                          start=START, end=START + len(TEXT), text=TEXT),
    ))
    store = TemporalFactStore()
    WikiAwareAdapter(wiki, store).extract_and_commit(
        "设备", ["价值"], as_of=date(2023, 6, 1),
        recorded_at=datetime(2023, 1, 2, tzinfo=timezone.utc),
    )
    nodes = {
        "A0": Node(name="A0", kind="fact", entity="设备", key="价值"),
        "第一期": Node(name="第一期", kind="operator", op=FirstOrderDiffEq(),
                       inputs={"A_prev": "A0"},
                       params={"lam": Decimal("1.10"), "theta": Decimal("-50")},
                       formula="A1 = 1.10*A0 - 50"),
    }
    result = ExecutionEngine(store, nodes).run(
        "第一期", as_of=date(2023, 6, 1),
        knowledge_at=datetime(2023, 6, 1, tzinfo=timezone.utc),
    )
    print("第一期 =", result.value)
    print("输入 fact =", result.fact_ids)
    print("哈希链 =", store.verify_chain())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
