# -*- coding: utf-8 -*-
"""Fin-Wiki v0：双时态证据账本 + 纯算子 DAG。"""

from .models import (
    CitationError,
    DerivedRecord,
    FactCandidate,
    FactConflictError,
    FactRecord,
    FinWikiError,
    MissingParameterError,
    SourceSpan,
)
from .store import TemporalFactStore
from .wiki import CompiledWiki
from .adapter import WikiAwareAdapter
from .operators import FirstOrderDiffEq
from .dag import ExecutionEngine, Node
from .watchdog import RuleBook, RuleVersion
from .compiler import DocumentCompiler, SpanSpec
from .resolver import ApplicabilityResolver, ApplicableVersion
from .case_study import CaseEvaluator, CaseFinding, CompanyDisclosure
from .annual_report import (
    AdoptionEvidence,
    AnnualReportDisclosureExtractor,
    build_company_disclosure,
    evaluate_text,
)

__all__ = [
    "CitationError", "DerivedRecord", "FactCandidate", "FactConflictError",
    "FactRecord", "FinWikiError", "MissingParameterError", "SourceSpan",
    "TemporalFactStore", "CompiledWiki", "WikiAwareAdapter", "FirstOrderDiffEq",
    "ExecutionEngine", "Node", "RuleBook", "RuleVersion",
    "DocumentCompiler", "SpanSpec",
    "ApplicabilityResolver", "ApplicableVersion",
    "CaseEvaluator", "CaseFinding", "CompanyDisclosure",
    "AdoptionEvidence", "AnnualReportDisclosureExtractor",
    "build_company_disclosure", "evaluate_text",
]
