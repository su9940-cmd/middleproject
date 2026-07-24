"""Enums shared by every agent and graph node."""

from enum import StrEnum


class MachineType(StrEnum):
    """Supported machine types."""

    REACTOR = "REACTOR"
    COMPRESSOR = "COMPRESSOR"
    STORAGE_TANK = "STORAGE_TANK"
    PUMP = "PUMP"


class MeasurementMode(StrEnum):
    """How a sensor reading was requested."""

    PERIODIC = "PERIODIC"
    IMMEDIATE_RECHECK = "IMMEDIATE_RECHECK"


class Shift(StrEnum):
    """Shift categories used by the trained model."""

    DAY = "Day"
    NIGHT = "Night"


class ExperienceLevel(StrEnum):
    """Worker experience categories used by the trained model."""

    JUNIOR = "Junior"
    SENIOR = "Senior"


class TrainingStatus(StrEnum):
    """Worker safety-training categories used by the trained model."""

    YES = "Yes"
    NO = "No"


class RiskLevel(StrEnum):
    """Risk level produced by the risk policy."""

    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class AlertStatus(StrEnum):
    """Lifecycle state of an alert."""

    NONE = "NONE"
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_RECHECK = "WAITING_RECHECK"
    MONITORING = "MONITORING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class ActionPhase(StrEnum):
    """Checklist-generation phase for an alert."""

    INITIAL = "INITIAL"
    FOLLOW_UP = "FOLLOW_UP"
    EMERGENCY = "EMERGENCY"


class NotificationStatus(StrEnum):
    """Delivery state of an immediate notification."""

    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class ChecklistItemStatus(StrEnum):
    """Worker completion state for a checklist item."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class MaintenanceRequestStatus(StrEnum):
    """Manager decision state for a drafted maintenance request (FR-14).

    Not part of the original 12-role contract - `ManagerReviewScreen.jsx`
    (role E) called out this whole feature as unassigned; the team agreed
    role C owns it, starting with these four values (COMPLETED added later
    only if an actual maintenance-completion flow is needed).
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"
