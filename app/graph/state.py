"""Shared incident-scoped LangGraph state."""

from datetime import datetime
from typing import Any, TypedDict

from app.core.enums import (
    AlertStatus,
    MachineType,
    MeasurementMode,
    NotificationStatus,
    RiskLevel,
)


class SafetyState(TypedDict, total=False):
    """Serializable state shared by all agents and graph nodes."""

    # Execution and incident identity
    thread_id: str
    alert_id: str | None
    reading_id: str
    machine_id: str
    machine_type: MachineType

    # Current measurement
    measured_at: datetime
    measurement_mode: MeasurementMode
    sensor_reading: dict[str, Any]

    # ML prediction
    ml_risk_score: float
    model_version: str
    prediction_thresholds: dict[str, float]

    # Risk policy
    risk_level: RiskLevel
    emergency_reasons: list[str]
    policy_version: str

    # Alert lifecycle
    alert_status: AlertStatus
    repeat_count: int
    consecutive_normal_count: int

    # Machine profile
    machine_profile: dict[str, Any]
    manual_id: str
    manual_path: str

    # Parallel RAG and memory outputs
    retrieved_documents: list[dict[str, Any]]
    memory_context: dict[str, Any]

    # Action and checklist outputs
    action_draft: dict[str, Any]
    final_checklist: dict[str, Any]

    # Immediate alert
    notification_status: NotificationStatus
    immediate_alert_sent_at: datetime | None
    notification_error: str | None

    # Human-in-the-loop
    worker_response: dict[str, Any] | None

    # Immediate recheck
    recheck_requested_at: datetime | None
    recheck_reading_id: str | None

    # Maintenance request
    requires_maintenance_request: bool
    maintenance_request_id: str | None

    # Error reporting
    error_code: str | None
    error_message: str | None
    failed_node: str | None
