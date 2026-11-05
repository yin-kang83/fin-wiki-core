# -*- coding: utf-8 -*-
"""审查报告 8 组问题的回归契约。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from fin_wiki import (
    CaseEvaluator,
    CompiledWiki,
    FactCandidate,
    FirstOrderDiffEq,
    Node,
    RuleVersion,
    SourceSpan,
    TemporalFactStore,
    WikiAwareAdapter,
)
from fin_wiki.dag import ExecutionEngine
from fin_wiki.models import CitationError, FactConflictError, MissingParameterError

UTC = timezone.utc
DOC = "合同第3.2节：核心设备价值为1000万元。"


def span(text: str = "核心设备价值为1000万元") -> SourceSpan:
    i = DOC.index(text)
    return SourceSpan(doc_id="D", doc_version="1", start=i,
                      end=i + len(text), text=text)


def cand(value="1000", key="价值", valid_from=date(2023, 1, 1), valid_to=None):
    return FactCandidate(entity="设备", key=key, value=Decimal(value), unit="万元",
                         valid_from=valid_from, valid_to=valid_to, source=span())


def rules():
    return [
        RuleVersion("CAS21", "2018", date(2018, 1, 1), date(2020, 12, 31), "旧", "旧"),
        RuleVersion("CAS21", "2021", date(2021, 1, 1), None, "新", "新",
                    transition="retrospective"),
    ]


def test_public_record_cannot_be_mutated():
    store = TemporalFactStore()
    rec = store.commit(cand())
    with pytest.raises((ValidationError, TypeError, AttributeError)):
        rec.value = Decimal("9999")
    assert store.value("设备", "价值", as_of=date(2023, 6, 1)) == Decimal("1000")


def test_second_correction_is_accepted():
    store = TemporalFactStore()
    f1 = store.commit(cand("1000"))
    f2 = store.commit(cand("1200"), supersedes=f1.fact_id)
    f3 = store.commit(cand("1300"), supersedes=f2.fact_id)
    assert f3.supersedes == f2.fact_id
    assert store.value("设备", "价值", as_of=date(2023, 6, 1)) == Decimal("1300")


def test_batch_failure_leaves_store_unchanged():
    store = TemporalFactStore()
    store.commit(cand("1000", key="B"))
    wiki = CompiledWiki()
    wiki.add_document("D", "1", DOC)
    wiki.add_candidate(cand("2000", key="A"))
    wiki.add_candidate(cand("3000", key="B"))
    adapter = WikiAwareAdapter(wiki, store)
    before = len(store.all_facts())
    with pytest.raises(FactConflictError):
        adapter.extract_and_commit("设备", ["A", "B"], as_of=date(2023, 6, 1))
    assert len(store.all_facts()) == before
    assert store.value("设备", "B", as_of=date(2023, 6, 1)) == Decimal("1000")


def test_other_standard_is_not_lease_adoption():
    from fin_wiki.annual_report import AnnualReportDisclosureExtractor
    with pytest.raises(MissingParameterError):
        AnnualReportDisclosureExtractor({2021: "2021"}).extract(
            "本公司自2021年1月1日起首次执行新收入准则。公司尚未执行新租赁准则。")


def test_subsidiary_year_is_not_guessed():
    from fin_wiki.annual_report import AnnualReportDisclosureExtractor
    with pytest.raises(MissingParameterError):
        AnnualReportDisclosureExtractor({2019: "2019", 2021: "2021"}).extract(
            "本公司自2019年1月1日起执行新租赁准则；子公司自2021年1月1日起执行新租赁准则。")


def test_constant_cannot_shadow_fact_input():
    store = TemporalFactStore()
    store.commit(cand("1000"))
    nodes = {
        "A0": Node(name="A0", kind="fact", entity="设备", key="价值"),
        "第一期": Node(name="第一期", kind="operator", op=FirstOrderDiffEq(),
                       inputs={"A_prev": "A0"},
                       params={"A_prev": Decimal("1"), "lam": Decimal("1"),
                               "theta": Decimal("0")},
                       formula="bad"),
    }
    with pytest.raises(ValueError):
        ExecutionEngine(store, nodes).run("第一期", as_of=date(2023, 6, 1))


def test_early_adoption_respects_entity_scope():
    from fin_wiki import ApplicabilityResolver
    r = [
        RuleVersion("CAS21", "2018", date(2018, 1, 1), date(2020, 12, 31), "旧", "旧",
                    entity_scope=frozenset({"A"})),
        RuleVersion("CAS21", "2021", date(2021, 1, 1), None, "新", "新",
                    early_adoption_allowed=True, entity_scope=frozenset({"B"})),
    ]
    resolver = ApplicabilityResolver(r)
    got = resolver.resolve("CAS21", event_date=date(2020, 6, 1),
                           reporting_period_end=date(2020, 12, 31),
                           early_adoption=True, entity_scope=frozenset({"A"}))
    assert got.rule.version == "2018"


def test_case_version_lookup_is_namespaced_by_standard():
    r = [
        RuleVersion("CAS21", "2018", date(2018, 1, 1), date(2020, 12, 31), "旧", "旧"),
        RuleVersion("CAS21", "2021", date(2021, 1, 1), None, "新", "新",
                    transition="retrospective"),
        RuleVersion("OTHER", "2018", date(2030, 1, 1), None, "other", "other"),
    ]
    ev = CaseEvaluator(r)
    from fin_wiki.case_study import CompanyDisclosure
    c = CompanyDisclosure("000001", "某", "CAS21", "2018",
                          date(2021, 1, 1), date(2021, 12, 31), "年报")
    assert ev.evaluate(c).status == "疑似未及时采用"


def test_document_replacement_is_rejected():
    wiki = CompiledWiki()
    wiki.add_document("D", "1", "1000")
    with pytest.raises(CitationError):
        wiki.add_document("D", "1", "9999")
