# -*- coding: utf-8 -*-
"""Fin-Wiki v0：证据可追溯的双时态事实账本。

设计目标：
  · 事实只追加，不覆盖；修正用 supersedes
  · 双时态：valid_from/valid_to（业务时间）+ recorded_at（录入时间）
  · 每条事实必须有可校验的原文来源（SourceSpan）
  · 缺参/冲突/来源不合法 → 拒绝，不默认
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

import hashlib


class FinWikiError(Exception):
    pass


class MissingParameterError(FinWikiError):
    pass


class FactConflictError(FinWikiError):
    pass


class CitationError(FinWikiError):
    pass


class SourceSpan(BaseModel):
    """原文证据：文档 + 版本 + 字符区间 + 文本。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    doc_id: str = Field(min_length=1)
    doc_version: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_span(self):
        if self.end <= self.start:
            raise ValueError("end 必须大于 start")
        if len(self.text) != self.end - self.start:
            raise ValueError("text 长度必须等于 end-start")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class FactCandidate(BaseModel):
    """LLM/Wiki 只允许产出的候选事实；入账前必须校验。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str = Field(min_length=1)
    key: str = Field(min_length=1)
    value: Decimal
    unit: str = Field(min_length=1)
    valid_from: date
    valid_to: Optional[date] = None
    source: SourceSpan
    confidence: str = "high"

    @model_validator(mode="after")
    def check_dates(self):
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to 不能早于 valid_from")
        return self


class FactRecord(FactCandidate):
    """账本记录：追加后不可变。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    recorded_at: datetime
    supersedes: Optional[str] = None
    prev_hash: str
    record_hash: str


class DerivedRecord(BaseModel):
    """派生结果：必须记录算子、输入 fact_id 与公式。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    derived_id: str
    key: str
    value: Decimal
    unit: str
    operator: str
    operator_version: str
    input_fact_ids: tuple[str, ...]
    formula: str
    valid_at: date
    computed_at: datetime
    citation: str
    parameters: dict[str, str] = Field(default_factory=dict)
    input_mapping: dict[str, str] = Field(default_factory=dict)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
