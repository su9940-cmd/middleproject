"""
Memory Agent가 요구하는 리포지토리 프로토콜.

구현체는 C(백엔드·DB 엔지니어)가 담당한다. Memory Agent는 이 프로토콜에만
의존하므로, C의 실제 DB 구현이 완성되기 전에도 독립적으로 개발·테스트할 수 있다.

프로토콜 확정은 C와 협의 후 결정된다. 아래는 Memory Agent 개발을 위한 초안이며,
실제 DB 스키마와 다른 필드명이 확정되면 이 파일을 먼저 갱신해야 한다.
"""

from datetime import datetime
from typing import Any, Protocol


class AlertRepository(Protocol):
    """경보(alerts) 테이블 조회 인터페이스."""

    def list_by_machine(self, machine_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """설비의 최근 경보를 최신순으로 반환한다.

        각 dict는 최소 다음 키를 포함해야 한다:
            alert_id: str
            risk_level: str          # RiskLevel 값
            alert_status: str        # AlertStatus 값
            created_at: datetime
            resolved_at: datetime | None
        """
        ...


class ChecklistRepository(Protocol):
    """체크리스트 항목(checklist_items) 조회 인터페이스."""

    def list_items_by_machine(
        self, machine_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """설비의 최근 체크리스트 항목을 최신순으로 반환한다.

        각 dict는 최소 다음 키를 포함해야 한다:
            checklist_item_id: str
            action_id: str
            title: str
            status: str              # ChecklistItemStatus 값
            worker_note: str | None
            completed_at: datetime | None
        """
        ...


class WorkerResponseRepository(Protocol):
    """작업자 응답(worker_responses) 조회 인터페이스."""

    def latest_note_by_machine(self, machine_id: str) -> str | None:
        """설비의 가장 최근 작업자 메모를 반환한다. 없으면 None."""
        ...


class MaintenanceRepository(Protocol):
    """정비 요청(maintenance_requests) 조회 인터페이스."""

    def list_by_machine(
        self, machine_id: str, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """설비의 정비 요청 이력을 최신순으로 반환한다.

        각 dict는 최소 다음 키를 포함해야 한다:
            maintenance_request_id: str
            requested_at: datetime
            approval_status: str
            priority: str
        """
        ...
