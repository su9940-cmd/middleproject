"""Immediate Recheck 트리거 노드.

담당: E (인터페이스 엔지니어).
Worker Interrupt에서 작업자 응답이 resume된 직후, 해당 설비의 즉시 재측정을
요청한다 (FR-11). 실제 설비 통신은 services.iot_service 에 위임하고,
이 노드는 상태 전이(alert_status, recheck_requested_at)만 책임진다.

주의:
- 노드는 SafetyState 전체가 아니라 변경한 필드만 반환한다.
- 함수명(request_immediate_recheck), 반환 필드명은 공통 계약에 고정된 값이므로
  임의로 바꾸지 않는다. 변경이 필요하면 코드를 고치지 말고 팀에 먼저 보고한다.
"""

from datetime import datetime, timezone

from app.core.enums import AlertStatus
from app.core.exceptions import RecheckRequestError
from app.graph.state import SafetyState
from app.services.iot_service import request_measurement


def request_immediate_recheck(state: SafetyState) -> dict:
    """작업자 제출 직후 해당 설비의 즉시 재측정을 요청한다 (FR-11).

    성공 시:
        {"alert_status": AlertStatus.WAITING_RECHECK, "recheck_requested_at": datetime}

    실패 시(예: IoT 응답 없음, 설비 연결 오류):
        {"error_code": "RECHECK_REQUEST_FAILED", "error_message": str, "failed_node": "request_immediate_recheck"}

    error_code는 하드코딩하지 않고 예외 자체의 error_code 속성을 사용한다.
    RecheckRequestError가 아닌 예상 못한 예외가 올라와도(예: 네트워크 라이브러리가
    감싸지 않은 원본 예외), 공통 계약의 RECHECK_REQUEST_FAILED로 안전하게 대체한다.
    """
    machine_id = state["machine_id"]
    requested_at = datetime.now(timezone.utc)

    try:
        request_measurement(machine_id=machine_id, reason="immediate_recheck")
    except RecheckRequestError as exc:
        return {
            "error_code": exc.error_code,
            "error_message": str(exc),
            "failed_node": "request_immediate_recheck",
        }
    except Exception as exc:  # noqa: BLE001 - 감싸지 않은 예외에 대한 안전망
        return {
            "error_code": "RECHECK_REQUEST_FAILED",
            "error_message": str(exc),
            "failed_node": "request_immediate_recheck",
        }

    return {
        "alert_status": AlertStatus.WAITING_RECHECK,
        "recheck_requested_at": requested_at,
    }