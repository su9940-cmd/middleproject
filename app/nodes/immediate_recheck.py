"""Immediate Recheck - 작업자 응답 직후 해당 설비의 즉시 재측정을 요청한다 (contract section 8).

실제 새 센서 값은 `POST /sensors/ingest`에 `measurement_mode=IMMEDIATE_RECHECK`로
도착한다(`app.api.sensor_routes`) - 이 노드는 그 요청을 트리거하고
`alert_status`/`recheck_requested_at` 전이만 책임진다. `app.graph.builder`는
이 노드를 곧바로 `END`로 연결한다. 실제 설비 통신은 `app.services.iot_service`에
위임한다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.enums import AlertStatus
from app.core.exceptions import RecheckRequestError
from app.graph.state import SafetyState
from app.services.iot_service import request_measurement


def request_immediate_recheck(state: SafetyState) -> dict[str, Any]:
    """작업자 제출 직후 해당 설비의 즉시 재측정을 요청한다.

    성공:
        {"alert_status": WAITING_RECHECK, "recheck_requested_at": datetime}
    실패:
        {"error_code": "RECHECK_REQUEST_FAILED", "error_message": str, "failed_node": "request_immediate_recheck"}
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
    except Exception as exc:  # noqa: BLE001 - 안전망, 공통 오류 코드로 대체
        return {
            "error_code": "RECHECK_REQUEST_FAILED",
            "error_message": str(exc),
            "failed_node": "request_immediate_recheck",
        }

    return {
        "alert_status": AlertStatus.WAITING_RECHECK,
        "recheck_requested_at": requested_at,
    }
