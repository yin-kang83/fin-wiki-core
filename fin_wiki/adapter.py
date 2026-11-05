# -*- coding: utf-8 -*-
"""Wiki 感知适配器：只把 Wiki 候选事实写入账本，不计算。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from .models import FactRecord, MissingParameterError
from .store import TemporalFactStore
from .wiki import CompiledWiki

class WikiAwareAdapter:
    def __init__(self, wiki: CompiledWiki, store: TemporalFactStore) -> None:
        self.wiki = wiki
        self.store = store

    def extract_and_commit(
        self,
        entity: str,
        keys: list[str],
        *,
        as_of: date,
        recorded_at: Optional[datetime] = None,
    ) -> list[FactRecord]:
        resolved = []
        missing = []
        for key in keys:
            candidates = self.wiki.lookup(entity, key, as_of=as_of)
            if not candidates:
                missing.append(key)
                continue
            if len(candidates) > 1:
                raise MissingParameterError(f"Wiki 命中多个候选事实：{entity}.{key}")
            resolved.append(candidates[0])
        if missing:
            raise MissingParameterError(f"Wiki 中缺少事实：{entity}.{','.join(missing)}")
        return [self.store.commit(c, recorded_at=recorded_at) for c in resolved]
