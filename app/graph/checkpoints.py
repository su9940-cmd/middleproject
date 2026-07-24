"""Checkpointer factory for the safety graph.

`thread_id` follows the `{machine_id}:{alert_id}` format from the shared ID
contract (e.g. `M-0101:AL-M0101-20260723T101500`) so the 4 machines' graph
runs/interrupts stay fully independent of each other.
"""

from __future__ import annotations

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver


def get_checkpointer() -> BaseCheckpointSaver:
    """Return the checkpointer the graph resumes `worker_interrupt` from.

    In-memory today; swap for a persistent (Postgres) checkpointer before
    any deployment that must survive a process restart while an alert is
    mid-interrupt — process restarts would otherwise drop pending worker
    responses.
    """

    return InMemorySaver()
