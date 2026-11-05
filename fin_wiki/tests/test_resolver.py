# -*- coding: utf-8 -*-
"""准则适用性解析测试：旧/新/比较期/过渡/提前适用/冲突。"""

from __future__ import annotations

from datetime import date

import pytest

from fin_wiki import ApplicabilityResolver, FactConflictError, MissingParameterError, RuleVersion


def v(ver: str, start: date, end: date | None, transition: str = "prospective",
      early: bool = False) -> RuleVersion:
    return RuleVersion("租赁", ver, start, end, text=f"租赁准则 {ver}", citation=f"CAS21-{ver}",
                       transition=transition, early_adoption_allowed=early)


def test_old_transaction_uses_old_standard():
    rules = [v("2018", date(2018, 1, 1), date(2020, 12, 31)),
             v("2021", date(2021, 1, 1), None)]
    r = ApplicabilityResolver(rules).resolve("租赁", event_date=date(2019, 6, 1))
    assert r.rule.version == "2018" and r.basis == "transaction"


def test_new_transaction_uses_new_standard():
    rules = [v("2018", date(2018, 1, 1), date(2020, 12, 31)),
             v("2021", date(2021, 1, 1), None)]
    r = ApplicabilityResolver(rules).resolve("租赁", event_date=date(2022, 6, 1))
    assert r.rule.version == "2021" and r.basis == "transaction"


def test_retrospective_comparative_uses_new_standard():
    rules = [v("2018", date(2018, 1, 1), date(2020, 12, 31)),
             v("2021", date(2021, 1, 1), None, transition="retrospective")]
    r = ApplicabilityResolver(rules).resolve(
        "租赁", event_date=date(2020, 6, 1), reporting_period_end=date(2021, 12, 31))
    assert r.rule.version == "2021" and r.basis == "comparative_restated"


def test_prospective_comparative_keeps_old_standard():
    rules = [v("2018", date(2018, 1, 1), date(2020, 12, 31)),
             v("2021", date(2021, 1, 1), None, transition="prospective")]
    r = ApplicabilityResolver(rules).resolve(
        "租赁", event_date=date(2020, 6, 1), reporting_period_end=date(2021, 12, 31))
    assert r.rule.version == "2018" and r.basis == "transaction"


def test_early_adoption_when_allowed():
    rules = [v("2018", date(2018, 1, 1), date(2022, 12, 31)),
             v("2023", date(2023, 1, 1), None, early=True)]
    r = ApplicabilityResolver(rules).resolve(
        "租赁", event_date=date(2022, 6, 1), reporting_period_end=date(2022, 12, 31),
        early_adoption=True)
    assert r.rule.version == "2023" and r.basis == "early_adoption"


def test_missing_and_conflict_fail_closed():
    rules = [v("2021", date(2021, 1, 1), None)]
    with pytest.raises(MissingParameterError):
        ApplicabilityResolver(rules).resolve("租赁", event_date=date(2019, 1, 1))
    overlapping = [v("A", date(2020, 1, 1), None), v("B", date(2021, 1, 1), None)]
    with pytest.raises(FactConflictError):
        ApplicabilityResolver(overlapping).resolve("租赁", event_date=date(2022, 1, 1))
