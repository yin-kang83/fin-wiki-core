# -*- coding: utf-8 -*-
"""Fin-Wiki v0 回归：双时态/引用/缺参/DAG/规则版本/哈希链。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from fin_wiki import (
    CitationError,
    CompiledWiki,
    FactCandidate,
    FactConflictError,
    FirstOrderDiffEq,
    MissingParameterError,
    Node,
    RuleBook,
    RuleVersion,
    SourceSpan,
    TemporalFactStore,
    WikiAwareAdapter,
)
from fin_wiki.dag import ExecutionEngine

UTC = timezone.utc
DOC = "合同第3.2节：核心设备价值为1000万元，实际利率10%。"


def span(text: str = "核心设备价值为1000万元") -> SourceSpan:
    start = DOC.index(text)
    return SourceSpan(doc_id="contract-A", doc_version="2023", start=start,
                      end=start + len(text), text=text)


def candidate(value: str = "1000", valid_from: date = date(2023, 1, 1),
              valid_to: date | None = None) -> FactCandidate:
    return FactCandidate(entity="设备", key="价值", value=Decimal(value),
                         unit="万元", valid_from=valid_from, valid_to=valid_to,
                         source=span())


def test_bitemporal_correction_and_chain():
    store = TemporalFactStore()
    old = store.commit(candidate("1000"), recorded_at=datetime(2023, 1, 2, tzinfo=UTC))
    new = store.commit(candidate("1200"), recorded_at=datetime(2024, 1, 2, tzinfo=UTC),
                       supersedes=old.fact_id)
    assert old.record_hash and new.record_hash
    assert store.verify_chain()
    assert store.value("设备", "价值", as_of=date(2023, 6, 1),
                       knowledge_at=datetime(2023, 12, 31, tzinfo=UTC)) == Decimal("1000")
    assert store.value("设备", "价值", as_of=date(2023, 6, 1),
                       knowledge_at=datetime(2024, 12, 31, tzinfo=UTC)) == Decimal("1200")
    assert len(store.history("设备", "价值")) == 2


def test_overlap_without_supersedes_rejected():
    store = TemporalFactStore()
    store.commit(candidate("1000"))
    with pytest.raises(FactConflictError):
        store.commit(candidate("1100"))


def test_missing_fact_fail_closed():
    store = TemporalFactStore()
    with pytest.raises(MissingParameterError):
        store.value("设备", "不存在", as_of=date(2023, 1, 1))
    store.commit(candidate("1000", valid_from=date(2023, 1, 1)))
    with pytest.raises(MissingParameterError):
        store.value("设备", "价值", as_of=date(2022, 1, 1))


def test_wiki_citation_must_match_source():
    wiki = CompiledWiki()
    wiki.add_document("contract-A", "2023", DOC)
    good = candidate("1000")
    wiki.add_candidate(good)
    bad = FactCandidate(entity="设备", key="价值", value=Decimal("1000"), unit="万元",
                        valid_from=date(2023, 1, 1),
                        source=SourceSpan(doc_id="contract-A", doc_version="2023", start=0,
                                          end=6, text="XXXXXX"))
    with pytest.raises(CitationError):
        wiki.add_candidate(bad)


def test_adapter_requires_all_before_commit():
    wiki = CompiledWiki()
    wiki.add_document("contract-A", "2023", DOC)
    wiki.add_candidate(candidate("1000"))
    store = TemporalFactStore()
    adapter = WikiAwareAdapter(wiki, store)
    with pytest.raises(MissingParameterError):
        adapter.extract_and_commit("设备", ["价值", "利率"], as_of=date(2023, 6, 1))
    assert store.all_facts() == []


def test_dag_diffeq_and_lineage():
    store = TemporalFactStore()
    fact = store.commit(candidate("1000"))
    nodes = {
        "A0": Node(name="A0", kind="fact", entity="设备", key="价值"),
        "第一期": Node(name="第一期", kind="operator", op=FirstOrderDiffEq(),
                       inputs={"A_prev": "A0"},
                       params={"lam": Decimal("1.10"), "theta": Decimal("-50")},
                       formula="A1=1.10*A0-50"),
    }
    engine = ExecutionEngine(store, nodes)
    r = engine.run("第一期", as_of=date(2023, 6, 1))
    assert r.value == Decimal("1050.00")
    d = store.derived()[0]
    assert d.input_fact_ids == (fact.fact_id,)
    assert engine.run("第一期", as_of=date(2023, 6, 1)).value == Decimal("1050.00")


def test_rulebook_version_and_conflict():
    r1 = RuleVersion("研发加计", "2023", date(2023, 1, 1), date(2024, 12, 31), "75%", "财税2023-7")
    r2 = RuleVersion("研发加计", "2026", date(2025, 1, 1), None, "100%", "财税2026-1")
    book = RuleBook([r1, r2])
    assert book.resolve("研发加计", as_of=date(2024, 6, 1)).version == "2023"
    assert book.resolve("研发加计", as_of=date(2026, 6, 1)).version == "2026"
    with pytest.raises(MissingParameterError):
        book.resolve("研发加计", as_of=date(2022, 1, 1))
    overlapping = RuleBook([r1, RuleVersion("研发加计", "X", date(2024, 1, 1), None, "x", "x")])
    with pytest.raises(FactConflictError):
        overlapping.resolve("研发加计", as_of=date(2024, 6, 1))
