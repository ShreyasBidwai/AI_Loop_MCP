"""Durable run state. Lives in a file, NOT in the agent's context window.

Why a file: if state lived only in the agent's head, context compaction would
silently erase the plan mid-run. The dashboard also reads this same file.
"""
from __future__ import annotations
import json, time, threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Optional

STATE_PATH = Path(".looping_state.json")
_lock = threading.Lock()

Status = Literal["idle", "proposing", "awaiting_confirm", "running",
                 "blocked_gate", "escalated", "done", "stopped", "failed"]


@dataclass
class Criterion:
    id: str
    text: str                       # plain product language the manager can read
    oracle_type: Literal["command", "browser", "manual"]
    oracle: str = ""                # e.g. "pytest -q" / URL flow / human note
    status: Literal["pending", "passing", "failing"] = "pending"
    detail: str = ""                # last failure detail (feeds the agent's re-plan)


@dataclass
class Gate:
    action: str                     # e.g. "php artisan migrate --env=staging"
    reason: str
    decided: Optional[bool] = None  # None=pending, True=approved, False=rejected


@dataclass
class RunState:
    goal: str = ""
    status: Status = "idle"
    risk: str = "unknown"           # low / medium / high
    lane: str = "unknown"           # auto / developer
    criteria: list[Criterion] = field(default_factory=list)
    # real, measured counters (safe to show live):
    turns: int = 0
    actions: int = 0
    started_at: float = 0.0
    # estimate only (label as ~):
    est_tokens: int = 0
    # safety:
    gate: Optional[Gate] = None
    escalation: Optional[dict] = None   # {trigger, reason, handoff}
    # convergence tracking:
    passing_history: list[int] = field(default_factory=list)
    activity: list[dict] = field(default_factory=list)   # {t, who, msg}

    # ---- helpers ----
    def passing(self) -> int:
        return sum(1 for c in self.criteria if c.status == "passing")

    def total(self) -> int:
        return len(self.criteria)

    def failing(self) -> list[Criterion]:
        return [c for c in self.criteria if c.status != "passing"]

    def log(self, who: str, msg: str) -> None:
        self.activity.insert(0, {"t": time.strftime("%H:%M:%S"), "who": who, "msg": msg})
        self.activity = self.activity[:200]


def load() -> RunState:
    with _lock:
        if not STATE_PATH.exists():
            return RunState()
        raw = json.loads(STATE_PATH.read_text())
        raw["criteria"] = [Criterion(**c) for c in raw.get("criteria", [])]
        if raw.get("gate"):
            raw["gate"] = Gate(**raw["gate"])
        return RunState(**raw)


def save(s: RunState) -> None:
    with _lock:
        STATE_PATH.write_text(json.dumps(asdict(s), indent=2))
