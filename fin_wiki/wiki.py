# -*- coding: utf-8 -*-
"""Wiki 证据索引：只提供候选事实与原文引用，不做数值计算。"""

from __future__ import annotations

import hashlib
from datetime import date

from .models import CitationError, FactCandidate, MissingParameterError


class CompiledWiki:
    def __init__(self) -> None:
        self._candidates: list[FactCandidate] = []
        self._docs: dict[str, str] = {}
        self._doc_hashes: dict[str, str] = {}

    def add_document(self, doc_id: str, version: str, text: str) -> None:
        key = f"{doc_id}@{version}"
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if key in self._docs:
            if self._docs[key] != text or self._doc_hashes[key] != digest:
                raise CitationError(
                    f"文档版本内容不可变：{key} 已登记，内容变化必须使用新版本号"
                )
            return
        self._docs[key] = text
        self._doc_hashes[key] = digest

    def validate(self, candidate: FactCandidate) -> None:
        """入账边界再次校验：来源必须回指当前文档版本。"""
        key = f"{candidate.source.doc_id}@{candidate.source.doc_version}"
        text = self._docs.get(key)
        if text is None:
            raise MissingParameterError(f"来源文档不存在：{key}")
        if self._doc_hashes[key] != hashlib.sha256(text.encode("utf-8")).hexdigest():
            raise CitationError(f"来源文档摘要已变化：{key}")
        if text[candidate.source.start:candidate.source.end] != candidate.source.text:
            raise CitationError("SourceSpan 与当前文档原文不一致")
        if candidate.source.sha256 != hashlib.sha256(
                candidate.source.text.encode("utf-8")).hexdigest():
            raise CitationError("来源 hash 不一致")

    def add_candidate(self, candidate: FactCandidate) -> None:
        self.validate(candidate)
        self._candidates.append(candidate)

    def lookup(self, entity: str, key: str, *, as_of: date) -> list[FactCandidate]:
        return [c for c in self._candidates
                if c.entity == entity and c.key == key
                and c.valid_from <= as_of
                and (c.valid_to is None or c.valid_to >= as_of)]
