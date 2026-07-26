"""EMERGENCY 즉시 알림(Immediate Alert) 발송 노드 (contract section 8).

Risk Policy가 EMERGENCY로 판정하면, RAG·Memory·Validator 결과를 기다리지 않고
`alert_lifecycle_node`에서 rag_agent/memory_agent와 병렬로 즉시 발송된다
(`app.graph.builder._dispatch_from_alert_lifecycle`). 선통보에는 설비·위험
단계·긴급 규칙 근거만 포함하며, 완성된 체크리스트는 이후 동일 alert_id로
묶여 Worker Interrupt에서 같은 사건으로 이어진다.

중요: 이 노드가 실패해도 RAG·Memory·체크리스트 생성 경로를 중단시키면
안 된다(계약 8절: "알림 실패가 RAG·Memory·체크리스트 생성 경로를 중단시키면
안 됩니다"). 그래서 예외를 밖으로 전파하지 않고 notification_status=FAILED로
변환해 반환한다 - raise하면 `_with_error_handling`의 error_code 단락 로직에
걸려 action_draft_node/validator_agent가 무관한 이유로 건너뛰어진다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.enums import NotificationStatus
from app.core.exceptions import NotificationError
from app.graph.state import SafetyState
from app.services.notification_service import send_alert


def send_immediate_alert(state: SafetyState) -> dict[str, Any]:
    """EMERGENCY 판정 시 작업자 선통보를 발송한다.

    성공:
        {"notification_status": SENT, "immediate_alert_sent_at": datetime, "notification_error": None}
    실패:
        {"notification_status": FAILED, "notification_error": str}
    """

    message = _build_alert_message(state)

    try:
        send_alert(alert_id=state["alert_id"], machine_id=state["machine_id"], message=message)
    except NotificationError as exc:
        return {
            "notification_status": NotificationStatus.FAILED,
            "notification_error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - 안전망, 메인 경로를 막으면 안 됨
        return {
            "notification_status": NotificationStatus.FAILED,
            "notification_error": str(exc),
        }

    return {
        "notification_status": NotificationStatus.SENT,
        "immediate_alert_sent_at": datetime.now(timezone.utc),
        "notification_error": None,
    }


def _build_alert_message(state: SafetyState) -> str:
    """선통보 메시지 구성 - 설비·위험 단계·긴급 규칙 근거만 포함한다.

    체크리스트는 아직 생성되지 않은 시점이므로 절대 포함하지 않는다.
    """

    reasons = ", ".join(state.get("emergency_reasons", [])) or "상세 근거 확인 중"
    return (
        f"[EMERGENCY] {state['machine_id']} ({state['machine_type']}) "
        f"위험 단계: {state['risk_level']} — 근거: {reasons}"
    )
