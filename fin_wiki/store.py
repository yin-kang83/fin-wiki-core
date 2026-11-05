# -*- coding: utf-8 -*-
"""追加式双时态事实账本。"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from .models import (
    CitationError,
    DerivedRecord,
    FactCandidate,
    FactConflictError,
    FactRecord,
    MissingParameterError,
    utcnow,
)

GENESIS = "0" * 64


def _record_hash(rec: FactRecord) -> str:
    payload = rec.model_dump(mode="json")
    payload.pop("record_hash", None)
    payload.pop("prev_hash", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _overlap(a_from: date, a_to: Optional[date], b_from: date, b_to: Optional[date]) -> bool:
    a_end = a_to or date.max
    b_end = b_to or date.max
    return a_from <= b_end and b_from <= a_end


class TemporalFactStore:
    def __init__(self) -> None:
        self._facts: list[FactRecord] = []
        self._derived: list[DerivedRecord] = []

    # ---------------- facts ----------------
    def commit(
        self,
        candidate: FactCandidate,
        *,
        recorded_at: Optional[datetime] = None,
        supersedes: Optional[str] = None,
    ) -> FactRecord:
        if not candidate.source.text.strip():
            raise CitationError("来源文本为空")
        recorded_at = recorded_at or utcnow()
        if supersedes:
            old = next((r for r in self._facts if r.fact_id == supersedes), None)
            if old is None:
                raise MissingParameterError(f"supersedes 指向不存在的事实：{supersedes}")
            if (old.entity, old.key) != (candidate.entity, candidate.key):
                raise FactConflictError("supersedes 的 entity/key 不一致")

        # 同 key 的有效期重叠：没有显式 supersedes 就拒绝，防止静默覆盖
        for old in self._facts:
            if (old.entity, old.key) != (candidate.entity, candidate.key):
                continue
            if supersedes == old.fact_id:
                continue
            if _overlap(candidate.valid_from, candidate.valid_to, old.valid_from, old.valid_to):
                raise FactConflictError(
                    f"事实冲突：{candidate.entity}.{candidate.key} 与 {old.fact_id} 有效期重叠；"
                    "修正必须显式 supersedes"
                )

        prev_hash = self._facts[-1].record_hash if self._facts else GENESIS
        rec = FactRecord(
            **candidate.model_dump(),
            fact_id=f"F{len(self._facts) + 1:06d}",
            recorded_at=recorded_at,
            supersedes=supersedes,
            prev_hash=prev_hash,
            record_hash="",
        )
        rec = rec.model_copy(update={"record_hash": _record_hash(rec)})
        self._facts.append(rec)
        return rec

    def _visible(self, as_of: date, knowledge_at: datetime) -> list[FactRecord]:
        candidates = [
            r for r in self._facts
            if r.recorded_at <= knowledge_at
            and r.valid_from <= as_of
            and (r.valid_to is None or r.valid_to >= as_of)
        ]
        superseded = {r.supersedes for r in self._facts if r.supersedes and r.recorded_at <= knowledge_at}
        return [r for r in candidates if r.fact_id not in superseded]

    def get(self, entity: str, key: str, *, as_of: date, knowledge_at: Optional[datetime] = None) -> FactRecord:
        visible = [r for r in self._visible(as_of, knowledge_at or utcnow())
                   if (r.entity, r.key) == (entity, key)]
        if not visible:
            raise MissingParameterError(f"缺失事实：{entity}.{key}（as_of={as_of}）")
        visible.sort(key=lambda r: r.recorded_at)
        if len(visible) > 1:
            raise FactConflictError(f"同一时点存在多个有效事实：{entity}.{key}")
        return visible[0]

    def value(self, entity: str, key: str, *, as_of: date, knowledge_at: Optional[datetime] = None) -> Decimal:
        return self.get(entity, key, as_of=as_of, knowledge_at=knowledge_at).value

    def history(self, entity: str, key: str) -> list[FactRecord]:
        return [r for r in self._facts if (r.entity, r.key) == (entity, key)]

    def all_facts(self) -> list[FactRecord]:
        return list(self._facts)

    def verify_chain(self) -> bool:
        prev = GENESIS
        for r in self._facts:
            if r.prev_hash != prev:
                return False
            if r.record_hash != _record_hash(r):
                return False
            prev = r.record_hash
        return True

    # ---------------- derived ----------------
    def record_derived(self, derived: DerivedRecord) -> DerivedRecord:
        self._derived.append(derived)
        return derived

    def derived(self) -> list[DerivedRecord]:
        return list(self._derived)
