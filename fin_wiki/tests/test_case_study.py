# -*- coding: utf-8 -*-
"""上市公司准则采用案例评估器测试（合成标签，不涉及真实公司结论）。"""

from __future__ import annotations

from datetime import date

from fin_wiki.case_study import CaseEvaluator, CompanyDisclosure
from fin_wiki.watchdog import RuleVersion


def rules():
    return [
        RuleVersion("CAS21", "2018", date(2018, 1, 1), date(2020, 12, 31), "旧租赁", "CAS21-2018"),
        RuleVersion("CAS21", "2021", date(2021, 1, 1), None, "新租赁", "CAS21-2021",
                    transition="retrospective"),
    ]


def case(version: str, start: date, end: date) -> CompanyDisclosure:
    return CompanyDisclosure("000001", "某公司", "CAS21", version, start, end, "年报附注-会计政策")


def test_timely_and_late_classification():
    ev = CaseEvaluator(rules())
    timely = ev.evaluate(case("2021", date(2021, 1, 1), date(2021, 12, 31)))
    late = ev.evaluate(case("2018", date(2021, 1, 1), date(2021, 12, 31)))
    assert timely.status == "一致"
    assert late.status == "疑似未及时采用"


def test_old_period_old_standard_is_consistent():
    ev = CaseEvaluator(rules())
    r = ev.evaluate(case("2018", date(2020, 1, 1), date(2020, 12, 31)))
    assert r.status == "一致"


def test_unknown_version_needs_evidence():
    ev = CaseEvaluator(rules())
    r = ev.evaluate(case("2099", date(2021, 1, 1), date(2021, 12, 31)))
    assert r.status == "证据不足"
