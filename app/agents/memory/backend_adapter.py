"""Async database adapter for the Memory Agent contract."""

from __future__ import annotations

from sqlalchemy import select

from app.agents.memory.agent import REPEAT_LIMIT_THRESHOLD
from app.agents.memory.context_builder import (
    collect_previous_titles,
    compute_repeat_count,
    count_unresolved,
    extract_previous_risk_level,
    is_risk_escalated,
    partition_action_ids,
)
from app.core.db import session_scope
from app.core.exceptions import MemoryLookupError
from app.graph.state import SafetyState
from app.models.orm_models import AlertORM, ChecklistORM, MaintenanceRequestORM


async def backend_memory_agent(state: SafetyState) -> dict:
    """Read prior alerts, checklists, and maintenance requests for a machine."""

    machine_id = state.get("machine_id")
    if not machine_id:
        raise MemoryLookupError(
            "machine_id is required to build memory context",
            details={"failed_node": "memory_agent"},
        )

    async with session_scope() as session:
        alert_stmt = (
            select(AlertORM)
            .where(AlertORM.machine_id == machine_id)
            .order_by(AlertORM.created_at.desc())
        )
        alerts = list((await session.execute(alert_stmt)).scalars().all())
        current_alert_id = state.get("alert_id")
        previous_alerts = [
            _alert_dict(alert)
            for alert in alerts
            if not current_alert_id or alert.alert_id != current_alert_id
        ]

        alert_ids = [alert.alert_id for alert in alerts]
        checklist_rows: list[ChecklistORM] = []
        if alert_ids:
            checklist_stmt = select(ChecklistORM).where(ChecklistORM.alert_id.in_(alert_ids))
            checklist_rows = list((await session.execute(checklist_stmt)).scalars().all())

        maintenance_stmt = (
            select(MaintenanceRequestORM)
            .where(MaintenanceRequestORM.machine_id == machine_id)
            .order_by(MaintenanceRequestORM.created_at.desc())
        )
        maintenance_rows = list((await session.execute(maintenance_stmt)).scalars().all())

    checklist_items = [
        item
        for row in checklist_rows
        for item in (row.items or [])
        if isinstance(item, dict)
    ]
    unresolved_count = count_unresolved(previous_alerts)
    previous_risk_level = extract_previous_risk_level(previous_alerts)
    completed_ids, failed_ids = partition_action_ids(checklist_items)
    repeat_count = compute_repeat_count(
        state_repeat_count=state.get("repeat_count", 0),
        unresolved_count=unresolved_count,
    )
    latest_note = next(
        (
            row.worker_note
            for row in sorted(checklist_rows, key=lambda item: item.created_at, reverse=True)
            if row.worker_note
        ),
        None,
    )
    return {
        "memory_context": {
            "previous_alert_count": len(previous_alerts),
            "unresolved_count": unresolved_count,
            "previous_risk_level": previous_risk_level,
            "previous_checklist_items": collect_previous_titles(checklist_items),
            "completed_action_ids": completed_ids,
            "failed_action_ids": failed_ids,
            "latest_worker_note": latest_note,
            "maintenance_history": [_maintenance_dict(row) for row in maintenance_rows],
            "repeat_count": repeat_count,
            "is_risk_escalated": is_risk_escalated(
                previous_risk_level, state.get("risk_level")
            ),
            "is_repeat_limit_exceeded": repeat_count >= REPEAT_LIMIT_THRESHOLD,
        }
    }


def _alert_dict(alert: AlertORM) -> dict:
    return {
        "alert_id": alert.alert_id,
        "risk_level": alert.risk_level,
        "alert_status": alert.alert_status,
        "created_at": alert.created_at,
        "resolved_at": None,
    }


def _maintenance_dict(row: MaintenanceRequestORM) -> dict:
    return {
        "maintenance_request_id": row.maintenance_request_id,
        "requested_at": row.created_at,
        "approval_status": row.status,
        "priority": row.priority,
    }
