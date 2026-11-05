# -*- coding: utf-8 -*-
"""Wiki 证据索引：只提供候选事实与原文引用，不做数值计算。"""

from __future__ import annotations

from datetime import date
from typing import Optional

from .models import FactCandidate, MissingParameterError


class CompiledWiki:
    def __init__(self) -> None:
        self._candidates: list[FactCandidate] = []
        self._docs: dict[str, str] = {}

    def add_document(self, doc_id: str, version: str, text: str) -> None:
        self._docs[f"{doc_id}@{version}"] = text

    def add_candidate(self, candidate: FactCandidate) -> None:
        # 来源必须能在本文档索引中复现
        key = f"{candidate.source.doc_id}@{candidate.source.doc_version}"
        text = self._docs.get(key)
        if text is None:
            raise MissingParameterError(f"来源文档不存在：{key}")
        if text[candidate.source.start:candidate.source.end] != candidate.source.text:
            raise ValueError("SourceSpan 与文档原文不一致")
        if candidate.source.sha256 != __import__("hashlib").sha256(candidate.source.text.encode("utf-8")).hexdigest():
            raise ValueError("来源 hash 不一致")
        self._candidates.append(candidate)

    def lookup(self, entity: str, key: str, *, as_of: date) -> list[FactCandidate]:
        return [c for c in self._candidates
                if c.entity == entity and c.key == key
                and c.valid_from <= as_of
                and (c.valid_to is None or c.valid_to >= as_of)]
