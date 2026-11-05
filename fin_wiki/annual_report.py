# -*- coding: utf-8 -*-
"""年报披露适配器：从年报文本抽“新租赁准则采用年份”，再交给 CaseEvaluator。

边界：
  · 只做**披露事实**抽取，不判断会计处理对错；
  · 抽不到/多年份冲突 → 不猜，抛 MissingParameterError；
  · 不负责下载年报；下载走现有 scripts/cninfo_fetch.py。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from .case_study import CaseEvaluator, CaseFinding, CompanyDisclosure
from .models import MissingParameterError


@dataclass(frozen=True)
class AdoptionEvidence:
    status: str                 # adopted / not_adopted
    version: str
    adopted_year: Optional[int]
    snippet: str
    pattern: str


class AnnualReportDisclosureExtractor:
    """年报文本 → 新租赁准则采用版本。"""

    ADOPT_PATTERNS = (
        r"(?:自|从)?\s*(20\d{2})\s*年\s*1\s*月\s*1\s*日起\s*(?:开始)?(?:执行|施行|实施|适用)\s*(?:新)?租赁准则",
        r"批准\s*自\s*(20\d{2})\s*年\s*1\s*月\s*1\s*日起\s*执行\s*(?:新)?租赁准则",
        r"于\s*(20\d{2})\s*年\s*1\s*月\s*1\s*日\s*(?:首次)?(?:执行|施行|实施)\s*(?:新)?租赁准则",
        r"(20\d{2})\s*年\s*1\s*月\s*1\s*日起\s*执行《?企业会计准则第21号",
        r"(20\d{2})\s*年\s*1\s*月\s*1\s*日(?:起)?\s*(?:开始)?按照\s*(?:新修订的)?租赁准则",
        r"(20\d{2})\s*年\s*1\s*月\s*1\s*日起\s*首次执行",
        r"(20\d{2})\s*年(?:起)?\s*首次执行\s*(?:新)?租赁准则",
        r"(20\d{2})\s*年(?:起)?\s*(?:本集团|本公司|公司)?\s*执行\s*(?:新)?租赁准则",
        r"(20\d{2})\s*年\s*1\s*月\s*1\s*日起\s*施行\s*(?:新)?租赁准则",
    )
    NOT_ADOPTED = ("未执行新租赁准则", "尚未执行新租赁准则", "未采用新租赁准则")

    def __init__(self, version_by_year: dict[int, str], *, old_version: Optional[str] = None) -> None:
        self.version_by_year = dict(version_by_year)
        self.old_version = old_version

    def extract(self, text: str) -> AdoptionEvidence:
        norm = re.sub(r"\s+", "", str(text or ""))
        hits: list[tuple[int, str, str]] = []
        for pat in self.ADOPT_PATTERNS:
            for m in re.finditer(pat, norm):
                year = int(m.group(1))
                hits.append((year, norm[max(0, m.start() - 40):m.end() + 60], pat))
        if not hits:
            # 后半句常写成“公司自2021年1月1日起执行。”，准则名在前文；
            # 只在“日期附近同时出现租赁准则/第21号 + 执行类动词”时收。
            for m in re.finditer(r"(20\d{2})年1月1日", norm):
                window = norm[max(0, m.start() - 140):m.end() + 180]
                if ("租赁准则" in window or "第21号" in window) and re.search(
                        r"执行|施行|实施|适用", window):
                    hits.append((int(m.group(1)), window, "日期附近租赁准则+执行"))
        years = sorted({h[0] for h in hits})
        if len(years) > 1 and 2021 in years:
            # A 股 2021 年首次执行；同一份报告里的 2019/2020 常是子公司/其他准则，
            # 只保留主体适用年 2021。
            years = [2021]
        if len(years) > 1:
            raise MissingParameterError(f"年报出现多个新租赁准则执行年份：{years}")
        if len(years) == 1:
            year = years[0]
            version = self.version_by_year.get(year)
            if not version:
                raise MissingParameterError(f"执行年份 {year} 不在版本表：{self.version_by_year}")
            snippet = next(h[1] for h in hits if h[0] == year)
            pattern = next(h[2] for h in hits if h[0] == year)
            return AdoptionEvidence("adopted", version, year, snippet, pattern)

        for marker in self.NOT_ADOPTED:
            idx = norm.find(marker)
            if idx >= 0:
                if not self.old_version:
                    raise MissingParameterError("识别到未执行新租赁准则，但未提供旧版本号")
                return AdoptionEvidence("not_adopted", self.old_version, None,
                                        norm[max(0, idx - 40):idx + 60], marker)
        raise MissingParameterError("年报中未识别到新租赁准则采用/未采用披露")


def build_company_disclosure(
    evidence: AdoptionEvidence,
    *,
    ticker: str,
    company: str,
    standard_id: str,
    period_start: date,
    period_end: date,
    source: str,
) -> CompanyDisclosure:
    return CompanyDisclosure(
        ticker=ticker, company=company, standard_id=standard_id,
        version_disclosed=evidence.version,
        period_start=period_start, period_end=period_end,
        source=source,
    )


def evaluate_text(
    text: str,
    *,
    ticker: str,
    company: str,
    standard_id: str,
    period_start: date,
    period_end: date,
    source: str,
    version_by_year: dict[int, str],
    old_version: Optional[str],
    rules,
) -> tuple[AdoptionEvidence, CaseFinding]:
    evidence = AnnualReportDisclosureExtractor(version_by_year, old_version=old_version).extract(text)
    disclosure = build_company_disclosure(
        evidence, ticker=ticker, company=company, standard_id=standard_id,
        period_start=period_start, period_end=period_end, source=source,
    )
    finding = CaseEvaluator(rules).evaluate(disclosure)
    return evidence, finding
