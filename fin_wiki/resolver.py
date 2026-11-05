# -*- coding: utf-8 -*-
"""准则适用性解析：按业务时点/报表期间/过渡条款选择版本，不选“最新版”。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import FactConflictError, MissingParameterError
from .watchdog import RuleVersion


@dataclass(frozen=True)
class ApplicableVersion:
    rule: RuleVersion
    basis: str          # transaction / comparative_restated / modified / early_adoption
    reason: str


class ApplicabilityResolver:
    def __init__(self, rules: list[RuleVersion]) -> None:
        self._rules = rules

    def _active(self, standard_id: str, at: date, entity_scope: frozenset[str]) -> list[RuleVersion]:
        hits = []
        for r in self._rules:
            if r.rule_id != standard_id:
                continue
            if r.entity_scope and entity_scope and not (r.entity_scope & entity_scope):
                continue
            if r.valid_from <= at and (r.valid_to is None or r.valid_to >= at):
                hits.append(r)
        return hits

    def resolve(
        self,
        standard_id: str,
        *,
        event_date: date,
        reporting_period_end: Optional[date] = None,
        early_adoption: bool = False,
        entity_scope: frozenset[str] = frozenset(),
    ) -> ApplicableVersion:
        transaction_hits = self._active(standard_id, event_date, entity_scope)
        if len(transaction_hits) != 1:
            if not transaction_hits:
                raise MissingParameterError(f"缺少适用准则版本：{standard_id} @ {event_date}")
            raise FactConflictError(f"准则版本冲突：{standard_id} @ {event_date}")
        transaction = transaction_hits[0]

        if early_adoption:
            future = [
                r for r in self._rules
                if r.rule_id == standard_id
                and r.early_adoption_allowed
                and r.valid_from > event_date
                and (not r.entity_scope or not entity_scope or (r.entity_scope & entity_scope))
            ]
            if len(future) > 1:
                raise FactConflictError(f"提前适用候选冲突：{standard_id} @ {event_date}")
            if future:
                chosen = future[0]
                return ApplicableVersion(chosen, "early_adoption",
                                         f"允许提前适用：{chosen.version}（{chosen.valid_from} 起）")

        if reporting_period_end is None:
            return ApplicableVersion(transaction, "transaction", "业务发生时点适用版本")

        report_hits = self._active(standard_id, reporting_period_end, entity_scope)
        if len(report_hits) != 1:
            if not report_hits:
                raise MissingParameterError(f"报表日无适用版本：{standard_id} @ {reporting_period_end}")
            raise FactConflictError(f"报表日版本冲突：{standard_id} @ {reporting_period_end}")
        reporting = report_hits[0]
        if reporting.version == transaction.version:
            return ApplicableVersion(transaction, "transaction", "交易与报表适用同一版本")

        transition = (reporting.transition or "prospective").lower()
        if transition in ("retrospective", "modified"):
            basis = "comparative_restated" if transition == "retrospective" else "modified"
            return ApplicableVersion(
                reporting, basis,
                f"新准则 {reporting.version} 生效，过渡条款={transition}，报表比较期按新版本处理",
            )
        return ApplicableVersion(
            transaction, "transaction",
            f"新准则 {reporting.version} 采用未来适用法，交易仍按旧版本 {transaction.version}",
        )
