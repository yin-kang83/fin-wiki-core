# -*- coding: utf-8 -*-
"""年报披露适配器测试：采用/未采用/多种措辞/冲突。"""

from __future__ import annotations

from datetime import date

import pytest

from fin_wiki import MissingParameterError, RuleVersion
from fin_wiki.annual_report import AnnualReportDisclosureExtractor, evaluate_text


def rules():
    return [
        RuleVersion("CAS21", "2018", date(2018, 1, 1), date(2020, 12, 31), "旧租赁", "CAS21-2018"),
        RuleVersion("CAS21", "2021", date(2021, 1, 1), None, "新租赁", "CAS21-2021",
                    transition="retrospective"),
    ]


@pytest.mark.parametrize("text", [
    "本公司自2021年1月1日起执行新租赁准则，对会计政策进行了调整。",
    "公司自2021年1月1日起实施新租赁准则。",
    "本公司自2021年1月1日起施行新租赁准则。",
    "本公司于2021年1月1日首次执行新租赁准则。",
    "本集团自2021年1月1日开始按照新修订的租赁准则进行会计处理。",
])
def test_adopted_variants(text):
    ev = AnnualReportDisclosureExtractor({2021: "2021"}).extract(text)
    assert ev.status == "adopted" and ev.version == "2021" and ev.adopted_year == 2021


def test_adopted_2021_is_timely():
    ev, finding = evaluate_text(
        "本公司自2021年1月1日起执行新租赁准则，对会计政策进行了调整。",
        ticker="000001", company="某公司", standard_id="CAS21",
        period_start=date(2021, 1, 1), period_end=date(2021, 12, 31),
        source="2021年年报-会计政策", version_by_year={2021: "2021"},
        old_version="2018", rules=rules(),
    )
    assert ev.status == "adopted" and ev.version == "2021"
    assert finding.status == "一致"


def test_not_adopted_in_2021_is_late():
    ev, finding = evaluate_text(
        "公司尚未执行新租赁准则，仍按原租赁准则核算。",
        ticker="000002", company="某公司", standard_id="CAS21",
        period_start=date(2021, 1, 1), period_end=date(2021, 12, 31),
        source="2021年年报-会计政策", version_by_year={2021: "2021"},
        old_version="2018", rules=rules(),
    )
    assert ev.status == "not_adopted" and ev.version == "2018"
    assert finding.status == "疑似未及时采用"


def test_multiple_including_2021_prefers_2021():
    ev = AnnualReportDisclosureExtractor({2019: "2019", 2021: "2021"}).extract(
        "子公司自2019年1月1日起执行新租赁准则；本公司自2021年1月1日起执行新租赁准则。")
    assert ev.adopted_year == 2021 and ev.version == "2021"


def test_multiple_without_2021_is_rejected():
    with pytest.raises(MissingParameterError):
        AnnualReportDisclosureExtractor({2019: "2019", 2020: "2020"}).extract(
            "公司自2019年1月1日起执行新租赁准则；自2020年1月1日起执行新租赁准则。")


def test_no_disclosure_is_rejected():
    with pytest.raises(MissingParameterError):
        AnnualReportDisclosureExtractor({2021: "2021"}).extract("本报告不涉及租赁准则。")
