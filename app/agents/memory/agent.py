"""
Memory Agent (FR-08).

역할:
    이전 경보·체크리스트·작업자 응답·정비 이력·반복 횟수를 조회하여
    Action Draft가 최초/후속/긴급 조치를 구성할 수 있도록 memory_context를 반환한다.

구성:
    - 클래스로 구현하며, 리포지토리 4개는 생성자로 주입받는다.
    - LangGraph 노드 진입점은 __call__(state)이다.
    - 성공 시 {"memory_context": ...} 하나만 반환한다.
    - 실패 시 MemoryLookupError를 raise한다. dict로 오류 필드를 직접 반환하지 않는다.
    - 재시도와 최종 오류 처리(error_code/error_message dict 변환 등)는
      D의 builder/API 경계에서 담당한다.
"""

from typing import Any

from app.agents.memory.context_builder import (
    collect_previous_titles,
    compute_repeat_count,
    count_unresolved,
    extract_previous_risk_level,
    is_risk_escalated,
    partition_action_ids,
)
from app.core.exceptions import MemoryLookupError
from app.graph.state import SafetyState
from app.repositories.protocols import (
    AlertRepository,
    ChecklistRepository,
    MaintenanceRepository,
    WorkerResponseRepository,
)


# Action Draft가 반복 초과(is_repeat_limit_exceeded=True)를 감지하는 임계값.
# 현재는 잠정값이며, 팀 협의 후 app/core/config.py로 이관 예정.
REPEAT_LIMIT_THRESHOLD = 3


class MemoryAgent:
    """LangGraph의 memory_agent 노드를 담당하는 클래스.

    LangGraph 등록 시 인스턴스 자체를 노드로 넘긴다:

        agent = MemoryAgent(alert_repo, checklist_repo, worker_repo, maintenance_repo)
        graph.add_node("memory_agent", agent)

    LangGraph는 노드를 호출할 때 인스턴스를 callable로 취급하므로 __call__이 호출된다.
    """

    def __init__(
        self,
        alert_repository: AlertRepository,
        checklist_repository: ChecklistRepository,
        worker_response_repository: WorkerResponseRepository,
        maintenance_repository: MaintenanceRepository,
    ) -> None:
        self._alerts = alert_repository
        self._checklists = checklist_repository
        self._worker_responses = worker_response_repository
        self._maintenance = maintenance_repository

    def __call__(self, state: SafetyState) -> dict[str, Any]:
        """노드 진입점.

        Args:
            state: 최소 machine_id를 포함해야 한다. risk_level, repeat_count도 사용한다.

        Returns:
            {"memory_context": <dict>} 형태로만 반환한다.

        Raises:
            MemoryLookupError: machine_id 누락 또는 리포지토리 조회 실패 시.
                (LangGraph builder 계층에서 재시도/오류 필드 변환을 담당)
        """
        machine_id = state.get("machine_id")
        if not machine_id:
            raise MemoryLookupError(
                "machine_id is required to build memory context",
                details={"failed_node": "memory_agent"},
            )

        try:
            context = self._build_context(machine_id, state)
        except MemoryLookupError:
            raise
        except Exception as exc:  # noqa: BLE001
            # 리포지토리 예외는 어떤 종류이든 MemoryLookupError로 래핑하여
            # 상위 계층이 일관된 error_code로 처리할 수 있게 한다 (프롬프트 11번).
            raise MemoryLookupError(
                f"failed to load history for {machine_id}: {exc}",
                details={"failed_node": "memory_agent", "machine_id": machine_id},
            ) from exc

        return {"memory_context": context}

    def _build_context(self, machine_id: str, state: SafetyState) -> dict[str, Any]:
        """리포지토리 4개를 호출해 memory_context 계약 필드를 계산한다."""
        alerts = self._alerts.list_by_machine(machine_id)
        checklist_items = self._checklists.list_items_by_machine(machine_id)
        latest_note = self._worker_responses.latest_note_by_machine(machine_id)
        maintenance_history = self._maintenance.list_by_machine(machine_id)

        unresolved_count = count_unresolved(alerts)
        previous_risk_level = extract_previous_risk_level(alerts)
        completed_ids, failed_ids = partition_action_ids(checklist_items)

        repeat_count = compute_repeat_count(
            state_repeat_count=state.get("repeat_count", 0),
            unresolved_count=unresolved_count,
        )

        return {
            "previous_alert_count": len(alerts),
            "unresolved_count": unresolved_count,
            "previous_risk_level": previous_risk_level,
            "previous_checklist_items": collect_previous_titles(checklist_items),
            "completed_action_ids": completed_ids,
            "failed_action_ids": failed_ids,
            "latest_worker_note": latest_note,
            "maintenance_history": maintenance_history,
            "is_risk_escalated": is_risk_escalated(previous_risk_level, state.get("risk_level")),
            "is_repeat_limit_exceeded": repeat_count >= REPEAT_LIMIT_THRESHOLD,
        }
