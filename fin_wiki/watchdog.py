# -*- coding: utf-8 -*-
"""版本化规则查询：规则冲突/缺失时拒绝，不交给 LLM 自由判断。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from .models import FactConflictError, MissingParameterError


@dataclass(frozen=True)
class RuleVersion:
    rule_id: str
    version: str
    valid_from: date
    valid_to: Optional[date]
    text: str
    citation: str
    transition: str = "prospective"       # prospective / retrospective / modified
    early_adoption_allowed: bool = False
    entity_scope: frozenset[str] = frozenset()


class RuleBook:
    def __init__(self, rules: list[RuleVersion]) -> None:
        self._rules = rules

    def resolve(self, rule_id: str, *, as_of: date) -> RuleVersion:
        hits = [r for r in self._rules
                if r.rule_id == rule_id
                and r.valid_from <= as_of
                and (r.valid_to is None or r.valid_to >= as_of)]
        if not hits:
            raise MissingParameterError(f"规则缺失：{rule_id} @ {as_of}")
        if len(hits) > 1:
            raise FactConflictError(f"规则版本冲突：{rule_id} @ {as_of} 命中 {len(hits)} 个版本")
        return hits[0]
