"""EMERGENCY 즉시 알림(Immediate Alert) 발송 노드.

담당: E (인터페이스 엔지니어) — 실제 알림 발송 채널.

Risk Policy가 EMERGENCY로 판정하면, RAG·Memory·Validator 결과를 기다리지 않고
비동기·논블로킹으로 작업자 선통보를 발송한다 (FR-16). 선통보에는 설비·위험
단계·긴급 규칙 근거만 포함하며, 완성된 체크리스트는 이후 동일 alert_id로
묶여 Worker Interrupt에서 같은 사건으로 이어진다.

중요: 이 노드가 실패해도 RAG·Memory·체크리스트 생성 경로를 중단시키면
안 된다 (요구분석서 FR-16 / 10장 오류 처리 계약). 그래서 예외를 밖으로
전파하지 않고 notification_status=FAILED로 변환해 반환한다.
"""

from datetime import datetime, timezone

from app.core.enums import NotificationStatus
from app.core.exceptions import NotificationError
from app.graph.state import SafetyState
from app.services.notification_service import send_alert


def send_immediate_alert(state: SafetyState) -> dict:
    """EMERGENCY 판정 시 작업자 선통보를 비동기로 발송한다 (FR-16).

    성공:
        {"notification_status": SENT, "immediate_alert_sent_at": datetime, "notification_error": None}
    실패:
        {"notification_status": FAILED, "notification_error": str}
    """
    message = _build_alert_message(state)

    try:
        send_alert(
            alert_id=state["alert_id"],
            machine_id=state["machine_id"],
            message=message,
        )
    except NotificationError as exc:
        return {
            "notification_status": NotificationStatus.FAILED,
            "notification_error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 - 감싸지 않은 예외에 대한 안전망, 메인 경로를 막으면 안 됨
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
    """선통보 메시지 구성 — 설비·위험 단계·긴급 규칙 근거만 포함한다.

    체크리스트는 아직 생성되지 않은 시점이므로 절대 포함하지 않는다.
    """
    reasons = ", ".join(state.get("emergency_reasons", [])) or "상세 근거 확인 중"
    return (
        f"[EMERGENCY] {state['machine_id']} ({state['machine_type']}) "
        f"위험 단계: {state['risk_level']} — 근거: {reasons}"
    )