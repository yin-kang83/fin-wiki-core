# -*- coding: utf-8 -*-
"""确定性文档编译器 v0：结构化条目 → SourceSpan → FactCandidate。

不做 LLM 推理；只接收“原文 + 区间 + 结构化值”，校验区间/取值后生成候选。
LLM 可在上游产出 SpanSpec，但必须经过本编译器与人工复核。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .models import FactCandidate, SourceSpan
from .wiki import CompiledWiki


@dataclass(frozen=True)
class SpanSpec:
    entity: str
    key: str
    value: Decimal
    unit: str
    start: int
    end: int
    valid_from: date
    valid_to: date | None = None
    confidence: str = "high"


class DocumentCompiler:
    def compile(self, *, doc_id: str, version: str, text: str,
                specs: list[SpanSpec]) -> CompiledWiki:
        wiki = CompiledWiki()
        wiki.add_document(doc_id, version, text)
        for s in specs:
            if not (0 <= s.start < s.end <= len(text)):
                raise ValueError(f"区间越界：{doc_id} [{s.start},{s.end})")
            span = SourceSpan(doc_id=doc_id, doc_version=version,
                              start=s.start, end=s.end, text=text[s.start:s.end])
            wiki.add_candidate(FactCandidate(
                entity=s.entity, key=s.key, value=s.value, unit=s.unit,
                valid_from=s.valid_from, valid_to=s.valid_to,
                source=span, confidence=s.confidence,
            ))
        return wiki
