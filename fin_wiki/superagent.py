# -*- coding: utf-8 -*-
"""Fin-Wiki Core · DeepSeek Super-agent 架构骨架。

四大模块：
1. StateStore：SQLite 底稿池，只追加事实/快照，带 hash chain 与禁改触发器。
2. Worker：LLM_Parser_Worker / Math_Operator_Worker，无状态、无打印、返回 dict。
3. Watchdog：独立断言层，在写 StateStore 前强校验，失败熔断。
4. Router：常驻调度层，按 DAG 拓扑派发 Worker，调度 Watchdog，不参与计算/生成。

本文件同时包含长期股权投资实验：
- 成本法转权益法
- 长投减值不可转回
- Worker 坏了就换
- 积压事件可恢复
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .adapters import CallableAdapter, LLMAdapter

ZERO = Decimal("0")
CENT = Decimal("0.01")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ============================================================
# 0. 异常
# ============================================================

class SuperAgentError(RuntimeError):
    pass


class SystemCollapseException(SuperAgentError):
    """结构性/完整性错误，必须熔断。"""


class LegalViolationException(SuperAgentError):
    """会计法/准则红线，拒绝写入。"""


class WorkerCrash(SuperAgentError):
    """Worker 临时故障；Router 应换一个 Worker 重试。"""


class WorkerUnavailableException(SuperAgentError):
    """Worker 连续失败，无法继续处理当前积压；应保留事件并停止本轮。"""


# ============================================================
# 1. Pydantic 数据契约
# ============================================================

class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Entry(FrozenModel):
    account: str = Field(min_length=1)
    debit: Decimal = Field(default=ZERO, ge=0)
    credit: Decimal = Field(default=ZERO, ge=0)


class ParsedLT(FrozenModel):
    """LLM_Parser_Worker 的唯一输出结构。"""

    initial_cost: Decimal = Field(default=ZERO, ge=0)
    prior_impairment: Decimal = Field(default=ZERO, ge=0)
    additional_consideration: Decimal = Field(default=ZERO, ge=0)
    net_assets_fair_value: Decimal = Field(default=ZERO, ge=0)
    ownership: Decimal = Field(default=ZERO, ge=0, le=1)
    investee_profit: Decimal = Field(default=ZERO)
    other_comprehensive_income: Decimal = Field(default=ZERO)
    cash_dividend: Decimal = Field(default=ZERO, ge=0)
    impairment_loss: Decimal = Field(default=ZERO, ge=0)
    impairment_reversal_requested: Decimal = Field(default=ZERO, ge=0)
    entries: list[Entry] = Field(default_factory=list)


class LTState(BaseModel):
    """长期股权投资底稿状态。"""

    initial_cost: Decimal = ZERO
    impairment: Decimal = ZERO
    additional_consideration: Decimal = ZERO
    net_assets_fair_value: Decimal = ZERO
    ownership: Decimal = ZERO
    adjusted_cost: Decimal = ZERO
    non_operating_income: Decimal = ZERO
    equity_income: Decimal = ZERO
    oci_share: Decimal = ZERO
    dividend_share: Decimal = ZERO
    impairment_loss: Decimal = ZERO
    carrying_amount: Decimal = ZERO
    status: Literal["cost", "equity"] = "cost"


class CandidateFact(FrozenModel):
    name: str = Field(min_length=1)
    value: Decimal
    unit: str = "元"


class FactRecord(FrozenModel):
    fact_id: str
    event_id: str
    name: str
    value: Decimal
    unit: str
    recorded_at: str
    prev_hash: str
    fact_hash: str


class SnapshotRecord(FrozenModel):
    snapshot_id: str
    event_id: str
    state_json: str
    created_at: str
    prev_snapshot_hash: str
    snapshot_hash: str


class EventRecord(FrozenModel):
    event_id: str
    text: str
    created_at: str
    priority: int = 0


class MathOutput(FrozenModel):
    state: LTState
    facts: list[CandidateFact]
    entries: list[Entry]
    previous_impairment: Decimal
    reversal_requested: Decimal


# ============================================================
# 2. State Store（绝对事实源，只追加）
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  event_id TEXT PRIMARY KEY,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS facts(
  fact_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  name TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  fact_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS snapshots(
  snapshot_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  state_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  prev_snapshot_hash TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS processed(
  event_id TEXT PRIMARY KEY,
  processed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outcomes(
  outcome_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS facts_no_update BEFORE UPDATE ON facts
BEGIN SELECT RAISE(ABORT, 'facts is append-only'); END;
CREATE TRIGGER IF NOT EXISTS facts_no_delete BEFORE DELETE ON facts
BEGIN SELECT RAISE(ABORT, 'facts is append-only'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots is append-only'); END;
CREATE TRIGGER IF NOT EXISTS snapshots_no_delete BEFORE DELETE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots is append-only'); END;
CREATE TRIGGER IF NOT EXISTS outcomes_no_update BEFORE UPDATE ON outcomes
BEGIN SELECT RAISE(ABORT, 'outcomes is append-only'); END;
CREATE TRIGGER IF NOT EXISTS outcomes_no_delete BEFORE DELETE ON outcomes
BEGIN SELECT RAISE(ABORT, 'outcomes is append-only'); END;
CREATE TRIGGER IF NOT EXISTS processed_no_update BEFORE UPDATE ON processed
BEGIN SELECT RAISE(ABORT, 'processed is append-only'); END;
CREATE TRIGGER IF NOT EXISTS processed_no_delete BEFORE DELETE ON processed
BEGIN SELECT RAISE(ABORT, 'processed is append-only'); END;
"""

GENESIS = "0" * 64


class StateStore:
    """SQLite 底稿池。业务表禁改；只通过 append_* 写入。"""

    def __init__(self, path: str | Path = "data/superagent.db") -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(events)")}
        if "priority" not in cols:
            self.conn.execute(
                "ALTER TABLE events ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- 事件 ----------
    def enqueue(self, text: str, priority: int = 0) -> EventRecord:
        ev = EventRecord(event_id=f"E{uuid.uuid4().hex[:12]}",
                         text=text, created_at=utcnow(),
                         priority=int(priority))
        self.conn.execute(
            "INSERT INTO events(event_id,text,created_at,priority) VALUES(?,?,?,?)",
            (ev.event_id, ev.text, ev.created_at, ev.priority))
        self.conn.commit()
        return ev

    def pending_events(self) -> list[EventRecord]:
        rows = self.conn.execute(
            "SELECT e.event_id,e.text,e.created_at,e.priority FROM events e "
            "LEFT JOIN processed p ON p.event_id=e.event_id "
            "LEFT JOIN outcomes o ON o.event_id=e.event_id "
            "WHERE p.event_id IS NULL AND o.event_id IS NULL "
            "ORDER BY e.priority DESC, e.rowid").fetchall()
        return [EventRecord(**dict(r)) for r in rows]

    def append_outcome(self, event_id: str, status: str, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO outcomes(outcome_id,event_id,status,detail,created_at) "
            "VALUES(?,?,?,?,?)",
            (f"O{uuid.uuid4().hex[:12]}", event_id, status, detail, utcnow()))
        self.conn.commit()

    # ---------- 状态 ----------
    def load_state(self) -> LTState:
        row = self.conn.execute(
            "SELECT state_json FROM snapshots ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return LTState() if row is None else LTState.model_validate_json(
            row["state_json"])

    def last_fact_hash(self) -> str:
        row = self.conn.execute(
            "SELECT fact_hash FROM facts ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return GENESIS if row is None else row["fact_hash"]

    def last_snapshot_hash(self) -> str:
        row = self.conn.execute(
            "SELECT snapshot_hash FROM snapshots ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return GENESIS if row is None else row["snapshot_hash"]

    def facts(self) -> list[FactRecord]:
        rows = self.conn.execute(
            "SELECT fact_id,event_id,name,value,unit,recorded_at,"
            "prev_hash,fact_hash FROM facts ORDER BY rowid").fetchall()
        return [FactRecord(**dict(r)) for r in rows]

    def verify_chain(self) -> dict[str, Any]:
        """重算 facts/snapshots 全链；不改库，返回可审计报告。"""
        errors: list[str] = []
        prev = GENESIS
        rows = self.conn.execute(
            "SELECT fact_id,event_id,name,value,unit,recorded_at,"
            "prev_hash,fact_hash FROM facts ORDER BY rowid").fetchall()
        for row in rows:
            if row["prev_hash"] != prev:
                errors.append(f"{row['fact_id']}: prev_hash 断链")
            body = {
                "event_id": row["event_id"], "name": row["name"],
                "value": row["value"], "unit": row["unit"],
                "recorded_at": row["recorded_at"], "prev_hash": row["prev_hash"],
            }
            if row["fact_hash"] != sha256(canonical_json(body)):
                errors.append(f"{row['fact_id']}: fact_hash 不匹配")
            prev = row["fact_hash"]

        prev_snap = GENESIS
        snaps = self.conn.execute(
            "SELECT snapshot_id,event_id,state_json,created_at,"
            "prev_snapshot_hash,snapshot_hash FROM snapshots ORDER BY rowid").fetchall()
        for row in snaps:
            if row["prev_snapshot_hash"] != prev_snap:
                errors.append(f"{row['snapshot_id']}: prev_snapshot_hash 断链")
            body = {
                "state_json": row["state_json"], "event_id": row["event_id"],
                "prev_snapshot_hash": row["prev_snapshot_hash"],
            }
            if row["snapshot_hash"] != sha256(canonical_json(body)):
                errors.append(f"{row['snapshot_id']}: snapshot_hash 不匹配")
            prev_snap = row["snapshot_hash"]

        return {
            "ok": not errors,
            "facts": len(rows),
            "snapshots": len(snaps),
            "errors": errors[:50],
        }

    # ---------- 外部事实（进销存等）显式桥接 ----------
    def append_external_event(self, event_id: str, text: str,
                              facts: list[CandidateFact],
                              source: str = "external") -> str:
        """显式外部事件：写 event + 事实链 + outcome；不写 LTState 快照。

        幂等：同一 event_id 已有 outcome 时直接返回，不重复追加事实。
        仅允许桥接层调用；inventory 表本身不自动进入事实链。
        """
        if not event_id or not str(event_id).strip():
            raise ValueError("event_id 必填")
        now = utcnow()
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            exists = self.conn.execute(
                "SELECT 1 FROM outcomes WHERE event_id=? LIMIT 1",
                (event_id,)).fetchone()
            if exists:
                self.conn.commit()
                return event_id
            if not self.conn.execute(
                    "SELECT 1 FROM events WHERE event_id=?", (event_id,)).fetchone():
                self.conn.execute(
                    "INSERT INTO events(event_id,text,created_at,priority) "
                    "VALUES(?,?,?,0)", (event_id, text, now))
            prev_fact = self.last_fact_hash()
            fact_rows = []
            for i, f in enumerate(facts, 1):
                value = q(f.value)
                body = {
                    "event_id": event_id, "name": f.name,
                    "value": str(value), "unit": f.unit,
                    "recorded_at": now, "prev_hash": prev_fact,
                }
                rec = FactRecord(
                    fact_id=f"F{event_id}-{i:02d}", event_id=event_id,
                    name=f.name, value=value, unit=f.unit,
                    recorded_at=now, prev_hash=prev_fact,
                    fact_hash=sha256(canonical_json(body)))
                prev_fact = rec.fact_hash
                fact_rows.append(rec)
            for r in fact_rows:
                self.conn.execute(
                    "INSERT INTO facts(fact_id,event_id,name,value,unit,"
                    "recorded_at,prev_hash,fact_hash) VALUES(?,?,?,?,?,?,?,?)",
                    (r.fact_id, r.event_id, r.name, str(r.value), r.unit,
                     r.recorded_at, r.prev_hash, r.fact_hash))
            self.conn.execute(
                "INSERT INTO processed(event_id,processed_at) VALUES(?,?)",
                (event_id, now))
            self.conn.execute(
                "INSERT INTO outcomes(outcome_id,event_id,status,detail,"
                "created_at) VALUES(?,?,?,?,?)",
                (f"O{uuid.uuid4().hex[:12]}", event_id, "success",
                 f"external:{source}", now))
            self.conn.commit()
            return event_id
        except Exception as exc:
            self.conn.rollback()
            raise SystemCollapseException(
                f"外部事实提交失败，已回滚：{exc}") from exc

    # ---------- 原子提交：事实 + 快照 + processed ----------
    def commit_result(self, event_id: str, state: LTState,
                      facts: list[CandidateFact]) -> SnapshotRecord:
        now = utcnow()
        try:
            # 事务内取链头，避免并发读-写竞态；SQLite 单写者由 BEGIN IMMEDIATE 保证
            self.conn.execute("BEGIN IMMEDIATE")
            prev_fact = self.last_fact_hash()
            fact_rows = []
            for i, f in enumerate(facts, 1):
                value = q(f.value)
                body = {
                    "event_id": event_id, "name": f.name,
                    "value": str(value), "unit": f.unit,
                    "recorded_at": now, "prev_hash": prev_fact,
                }
                rec = FactRecord(
                    fact_id=f"F{event_id}-{i:02d}", event_id=event_id,
                    name=f.name, value=value, unit=f.unit,
                    recorded_at=now, prev_hash=prev_fact,
                    fact_hash=sha256(canonical_json(body)))
                prev_fact = rec.fact_hash
                fact_rows.append(rec)

            prev_snap = self.last_snapshot_hash()
            state_json = state.model_dump_json()
            snap = SnapshotRecord(
                snapshot_id=f"S{uuid.uuid4().hex[:12]}", event_id=event_id,
                state_json=state_json, created_at=now,
                prev_snapshot_hash=prev_snap,
                snapshot_hash=sha256(canonical_json({
                    "state_json": state_json, "event_id": event_id,
                    "prev_snapshot_hash": prev_snap})))

            for r in fact_rows:
                self.conn.execute(
                    "INSERT INTO facts(fact_id,event_id,name,value,unit,"
                    "recorded_at,prev_hash,fact_hash) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (r.fact_id, r.event_id, r.name, str(r.value), r.unit,
                     r.recorded_at, r.prev_hash, r.fact_hash))
            self.conn.execute(
                "INSERT INTO snapshots(snapshot_id,event_id,state_json,"
                "created_at,prev_snapshot_hash,snapshot_hash) "
                "VALUES(?,?,?,?,?,?)",
                (snap.snapshot_id, snap.event_id, snap.state_json,
                 snap.created_at, snap.prev_snapshot_hash, snap.snapshot_hash))
            self.conn.execute(
                "INSERT INTO processed(event_id,processed_at) VALUES(?,?)",
                (event_id, now))
            self.conn.execute(
                "INSERT INTO outcomes(outcome_id,event_id,status,detail,"
                "created_at) VALUES(?,?,?,?,?)",
                (f"O{uuid.uuid4().hex[:12]}", event_id, "success",
                 "committed", now))
            self.conn.commit()
            return snap
        except Exception as exc:
            self.conn.rollback()
            raise SystemCollapseException(
                f"StateStore 提交失败，已回滚：{exc}") from exc


# ============================================================
# 3. Worker（无状态）
# ============================================================

class Worker:
    kind: str

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class LLMParserWorker(Worker):
    """只调大模型，把自然语言抽成 ParsedLT JSON；不做计算。"""

    kind = "llm_parser"

    def __init__(self, llm_call=None, adapter: LLMAdapter | None = None) -> None:
        if adapter is not None:
            self.adapter = adapter
        elif llm_call is not None:
            self.adapter = CallableAdapter(llm_call)
        else:
            raise ValueError("必须提供 llm_call 或 adapter")
        self.worker_id = f"parser-{uuid.uuid4().hex[:8]}"

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        text = task.get("text")
        if not isinstance(text, str) or not text.strip():
            raise WorkerCrash("缺少自然语言 text")
        try:
            data = self.adapter.parse(text)
        except Exception as exc:  # noqa: BLE001
            raise WorkerCrash(f"LLM 调用/解析失败：{exc}") from exc
        try:
            parsed = ParsedLT.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise WorkerCrash(f"LLM 输出结构不合法：{exc}") from exc
        return {"parsed": parsed.model_dump(mode="json")}


class MathOperatorWorker(Worker):
    """只跑 Decimal 计算；输入 state + parsed，输出标准 dict。"""

    kind = "math_operator"

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        try:
            state = LTState.model_validate(task.get("state") or {})
            parsed = ParsedLT.model_validate(task.get("parsed") or {})
        except Exception as exc:  # noqa: BLE001
            raise WorkerCrash(f"数学输入不合法：{exc}") from exc

        previous_impairment = state.impairment
        if parsed.initial_cost > 0:
            state.initial_cost = parsed.initial_cost
        if parsed.prior_impairment > 0:
            state.impairment = parsed.prior_impairment
        if parsed.additional_consideration > 0:
            state.additional_consideration += parsed.additional_consideration
        if parsed.net_assets_fair_value > 0:
            state.net_assets_fair_value = parsed.net_assets_fair_value
        if parsed.ownership > 0:
            state.ownership = parsed.ownership

        conversion = any((parsed.initial_cost > 0,
                          parsed.additional_consideration > 0,
                          parsed.net_assets_fair_value > 0,
                          parsed.ownership > 0))
        if conversion:
            # 成本法转权益法：原账面价值 + 新增对价；与应享有净资产份额比较
            cost_carrying = q(state.initial_cost - state.impairment)
            conversion_base = q(cost_carrying + state.additional_consideration)
            equity_share = q(state.net_assets_fair_value * state.ownership)
            non_operating_income = q(
                max(equity_share - conversion_base, ZERO))
            state.adjusted_cost = q(max(equity_share, conversion_base))
            state.non_operating_income = non_operating_income
            state.status = "equity"
        else:
            # 后续计量：沿用已调整的权益法成本
            state.adjusted_cost = state.adjusted_cost or q(
                state.initial_cost - state.impairment
                + state.additional_consideration)

        # 权益法后续：净利润、其他综合收益、现金股利
        equity_income = q(parsed.investee_profit * state.ownership)
        oci_share = q(parsed.other_comprehensive_income * state.ownership)
        dividend_share = q(parsed.cash_dividend * state.ownership)

        # 减值只能增加，不能转回
        new_impairment = state.impairment + parsed.impairment_loss
        state.impairment = q(new_impairment)
        state.equity_income = equity_income
        state.oci_share = oci_share
        state.dividend_share = dividend_share
        state.impairment_loss = parsed.impairment_loss
        state.carrying_amount = q(
            state.adjusted_cost + equity_income + oci_share - dividend_share
            - parsed.impairment_loss)

        facts = [
            CandidateFact(name="长期股权投资—损益调整", value=equity_income),
            CandidateFact(name="长期股权投资—其他综合收益", value=oci_share),
            CandidateFact(name="长期股权投资—现金股利", value=dividend_share),
            CandidateFact(name="长期股权投资账面价值", value=state.carrying_amount),
        ]
        if conversion:
            facts[0:0] = [
                CandidateFact(name="长期股权投资—成本", value=state.initial_cost),
                CandidateFact(name="长期股权投资减值准备", value=state.impairment),
                CandidateFact(name="营业外收入",
                              value=state.non_operating_income),
            ]
        if parsed.impairment_loss > 0:
            facts.append(CandidateFact(name="资产减值损失",
                                       value=parsed.impairment_loss))
        return MathOutput(
            state=state, facts=facts, entries=list(parsed.entries),
            previous_impairment=previous_impairment,
            reversal_requested=parsed.impairment_reversal_requested,
        ).model_dump(mode="json")


# ============================================================
# 4. Watchdog（外部巡检）
# ============================================================

class Watchdog:
    """独立断言层；在 Router 写 StateStore 之前调用。"""

    def validate(self, event: EventRecord, output: MathOutput,
                 previous: LTState) -> None:
        entries = output.entries
        debit = sum((e.debit for e in entries), ZERO)
        credit = sum((e.credit for e in entries), ZERO)
        if entries and q(debit) != q(credit):
            raise SystemCollapseException(
                f"借贷不平：借方 {debit}，贷方 {credit}")

        # 会计红线：长投减值不可转回
        if output.reversal_requested > 0:
            raise LegalViolationException(
                "长期股权投资减值不可转回：拒绝写入 StateStore")
        if output.state.impairment < previous.impairment:
            raise LegalViolationException(
                "减值准备减少违反不可转回规则")

        # 结构完整性
        if output.state.carrying_amount < 0:
            raise SystemCollapseException("长期股权投资账面价值为负")
        expected = q(output.state.adjusted_cost + output.state.equity_income
                     + output.state.oci_share - output.state.dividend_share
                     - output.state.impairment_loss)
        if expected != output.state.carrying_amount:
            raise SystemCollapseException(
                f"账面价值勾稽失败：期望 {expected}，实际 "
                f"{output.state.carrying_amount}")
        if output.state.ownership < 0 or output.state.ownership > 1:
            raise SystemCollapseException("持股比例越界")


# ============================================================
# 5. Router（常驻调度）
# ============================================================

@dataclass(frozen=True)
class Task:
    name: str
    kind: str
    deps: tuple[str, ...] = ()


class Router:
    def __init__(self, store: StateStore,
                 parser_factory: Callable[[], Worker],
                 math_factory: Callable[[], Worker],
                 watchdog: Watchdog | None = None,
                 max_retries: int = 2,
                 event_timeout: float | None = None) -> None:
        self.store = store
        self.parser_factory = parser_factory
        self.math_factory = math_factory
        self.watchdog = watchdog or Watchdog()
        self.max_retries = max_retries
        self.event_timeout = event_timeout
        self.worker_replacements = 0
        self.task_graph: tuple[Task, ...] = (
            Task("parse", "llm_parser"),
            Task("math", "math_operator", ("parse",)),
        )

    def submit(self, text: str, priority: int = 0) -> str:
        return self.store.enqueue(text, priority).event_id

    def _worker(self, kind: str) -> Worker:
        if kind == "llm_parser":
            return self.parser_factory()
        if kind == "math_operator":
            return self.math_factory()
        raise SystemCollapseException(f"未知 Worker 类型：{kind}")

    def _run_with_replacement(self, kind: str, task: dict[str, Any]) -> dict:
        last: Exception | None = None
        for _ in range(self.max_retries + 1):
            worker = self._worker(kind)
            try:
                return worker.run(task)
            except WorkerCrash as exc:
                last = exc
                self.worker_replacements += 1
        raise WorkerUnavailableException(f"Worker 连续失败：{kind}: {last}")

    def _run_graph(self, event: EventRecord) -> MathOutput:
        state = self.store.load_state()
        results: dict[str, dict] = {}
        started = time.monotonic()
        for task in self.task_graph:
            if any(dep not in results for dep in task.deps):
                raise SystemCollapseException(f"任务依赖未完成：{task.name}")
            if task.kind == "llm_parser":
                results[task.name] = self._run_with_replacement(
                    task.kind, {"text": event.text})
            else:
                results[task.name] = self._run_with_replacement(
                    task.kind, {"state": state.model_dump(mode="json"),
                                "parsed": results["parse"]["parsed"]})
            if self.event_timeout and time.monotonic() - started > self.event_timeout:
                raise SystemCollapseException(
                    f"事件处理超时 > {self.event_timeout}s")
        return MathOutput.model_validate(results["math"])

    def _prepare(self, event: EventRecord) -> tuple[LTState, MathOutput]:
        previous = self.store.load_state()
        output = self._run_graph(event)
        # Watchdog 必须在写 StateStore 之前；坏事件在这里隔离
        self.watchdog.validate(event, output, previous)
        return previous, output

    def process(self, event: EventRecord) -> SnapshotRecord:
        _, output = self._prepare(event)
        return self.store.commit_result(event.event_id, output.state,
                                        output.facts)

    def run_pending(self) -> dict[str, int]:
        """处理积压：坏事件隔离；Worker 不可用则保留事件，下一轮恢复。"""
        processed = blocked = deferred = quarantined = 0
        for event in self.store.pending_events():
            try:
                _, output = self._prepare(event)
            except WorkerUnavailableException:
                deferred += 1
                break
            except LegalViolationException as exc:
                self.store.append_outcome(event.event_id, "blocked", str(exc))
                blocked += 1
                continue
            except SystemCollapseException as exc:
                # 结构性坏事件隔离：写 outcome，不阻塞后续事件
                self.store.append_outcome(event.event_id, "quarantined", str(exc))
                quarantined += 1
                deferred += 1
                continue
            self.store.commit_result(event.event_id, output.state, output.facts)
            processed += 1
        return {"processed": processed, "blocked": blocked,
                "deferred": deferred, "quarantined": quarantined,
                "worker_replacements": self.worker_replacements}


# ============================================================
# 6. 长期股权投资实验
# ============================================================

def mock_llm(text: str) -> str:
    """模拟 LLM 输出；真实环境替换为模型调用即可。"""
    if "转回" in text:
        return json.dumps({
            "impairment_reversal_requested": "100",
            "entries": [
                {"account": "长期股权投资减值准备", "debit": "100",
                 "credit": "0"},
                {"account": "资产减值损失", "debit": "0", "credit": "100"},
            ],
        }, ensure_ascii=False)
    if "净利润" in text:
        return json.dumps({
            "investee_profit": "2000",
            "other_comprehensive_income": "500",
            "cash_dividend": "300",
        }, ensure_ascii=False)
    return json.dumps({
        "initial_cost": "1000",
        "prior_impairment": "100",
        "additional_consideration": "3000",
        "net_assets_fair_value": "15000",
        "ownership": "0.3",
        "entries": [
            {"account": "长期股权投资", "debit": "4000", "credit": "0"},
            {"account": "银行存款", "debit": "0", "credit": "4000"},
        ],
    }, ensure_ascii=False)


def parse_args(argv: list[str] | None = None):
    import argparse
    ap = argparse.ArgumentParser(prog="finwiki_superagent")
    ap.add_argument("--db", default="data/superagent.db")
    ap.add_argument("--demo", action="store_true")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = StateStore(args.db)
    router = Router(store, lambda: LLMParserWorker(mock_llm),
                    lambda: MathOperatorWorker())
    store.enqueue(
        "2026年1月，A公司以1000万元取得B公司10%股权，按成本法核算，"
        "以前年度已计提减值准备100万元；2026年7月又以3000万元取得20%股权，"
        "持股30%，B公司可辨认净资产公允价值15000万元。")
    store.enqueue("2026年B公司实现净利润2000万元，其他综合收益500万元，"
                  "宣告现金股利300万元。")
    store.enqueue("2026年末，A公司拟转回以前年度长期股权投资减值准备100万元。")
    report = router.run_pending()
    state = store.load_state()
    print(canonical_json({
        "report": report,
        "state": state.model_dump(mode="json"),
        "facts": [f.model_dump(mode="json") for f in store.facts()],
    }))
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

