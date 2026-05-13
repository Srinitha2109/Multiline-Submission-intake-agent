"""Per-task context for intake traces (local vs HTTP A2A specialist)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_EXECUTION_MODE: ContextVar[str] = ContextVar(
    "intake_execution_mode", default="unspecified"
)


def get_execution_mode() -> str:
    return _EXECUTION_MODE.get()


@contextmanager
def execution_mode(mode: str) -> Iterator[None]:
    token = _EXECUTION_MODE.set(mode)
    try:
        yield
    finally:
        _EXECUTION_MODE.reset(token)


def attach_intake_semantics(span, logical_agent_name: str) -> None:
    """Standard attributes so Arize / Phoenix show agent + whether A2A applied."""
    mode = get_execution_mode()
    span.set_attribute("intake.execution_mode", mode)
    span.set_attribute(
        "intake.a2a",
        mode.startswith("a2a_http") or "sequential_a2a" in mode,
    )
    span.set_attribute("agent.name", logical_agent_name)
