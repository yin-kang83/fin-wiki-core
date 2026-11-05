# -*- coding: utf-8 -*-
"""纯 Decimal 算子：算子只计算，不读 Wiki、不写底稿。"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

QUANT = Decimal("0.01")


class Operator(Protocol):
    name: str
    version: str
    def apply(self, params: dict[str, Decimal]) -> Decimal: ...


class FirstOrderDiffEq:
    name = "first_order_diff_eq"
    version = "1"

    def apply(self, params: dict[str, Decimal]) -> Decimal:
        lam = params["lam"]
        theta = params["theta"]
        a_prev = params["A_prev"]
        return (a_prev * lam + theta).quantize(QUANT, rounding=ROUND_HALF_UP)
