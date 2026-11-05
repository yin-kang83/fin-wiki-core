# -*- coding: utf-8 -*-
"""最小 DAG 执行器：事实/算子节点、依赖、血缘、幂等。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from .models import DerivedRecord, MissingParameterError, utcnow
from .operators import Operator
from .store import TemporalFactStore


@dataclass
class Node:
    name: str
    kind: str                     # fact / operator
    entity: str = ""
    key: str = ""
    op: Optional[Operator] = None
    inputs: dict[str, str] = field(default_factory=dict)
    params: dict[str, Decimal] = field(default_factory=dict)
    formula: str = ""


@dataclass
class Resolved:
    value: Decimal
    fact_ids: list[str]


class ExecutionEngine:
    def __init__(self, store: TemporalFactStore, nodes: dict[str, Node]) -> None:
        self.store = store
        self.nodes = nodes
        self._cache: dict[tuple[str, date, datetime], Resolved] = {}

    def run(self, target: str, *, as_of: date, knowledge_at: Optional[datetime] = None) -> Resolved:
        knowledge_at = knowledge_at or utcnow()
        return self._resolve(target, as_of, knowledge_at, set())

    def _resolve(self, name: str, as_of: date, knowledge_at: datetime, stack: set[str]) -> Resolved:
        if name in stack:
            raise ValueError(f"DAG 存在循环：{name}")
        key = (name, as_of, knowledge_at)
        if key in self._cache:
            return self._cache[key]
        node = self.nodes.get(name)
        if node is None:
            raise MissingParameterError(f"DAG 节点不存在：{name}")
        if node.kind == "fact":
            rec = self.store.get(node.entity, node.key, as_of=as_of, knowledge_at=knowledge_at)
            out = Resolved(rec.value, [rec.fact_id])
        elif node.kind == "operator":
            if node.op is None:
                raise ValueError(f"算子节点缺 op：{name}")
            vals = {}
            fact_ids: list[str] = []
            for param, dep in node.inputs.items():
                r = self._resolve(dep, as_of, knowledge_at, stack | {name})
                vals[param] = r.value
                fact_ids.extend(r.fact_ids)
            vals.update(node.params)
            value = node.op.apply(vals)
            derived = DerivedRecord(
                derived_id=f"D{len(self.store.derived()) + 1:06d}",
                key=name, value=value, unit="",
                operator=node.op.name, operator_version=node.op.version,
                input_fact_ids=sorted(set(fact_ids)),
                formula=node.formula or name,
                valid_at=as_of, computed_at=knowledge_at,
                citation="，".join(node.inputs.values()),
            )
            self.store.record_derived(derived)
            out = Resolved(value, derived.input_fact_ids)
        else:
            raise ValueError(f"未知节点类型：{node.kind}")
        self._cache[key] = out
        return out
