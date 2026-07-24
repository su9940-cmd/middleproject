"""IoT 즉시 재측정 요청 서비스.

역할 E가 제안한 시그니처(`request_measurement(machine_id, reason)`)와 예외
계약(`RecheckRequestError`)을 그대로 확정한다. 실제 IoT 장비가 없는 데모
환경(CLAUDE.md 참고)이라 재측정 데이터 자체는 작업자가
`POST /sensors/ingest`에 `measurement_mode=IMMEDIATE_RECHECK`로 직접 다시
제출한다 - 이 함수는 그 요청이 필요하다는 사실을 로그로 남기는 역할만
한다. 실제 설비 통신 채널이 생기면 이 함수 본문만 교체하면 된다.
"""

from __future__ import annotations

import logging

from app.core.exceptions import RecheckRequestError

logger = logging.getLogger(__name__)


def request_measurement(machine_id: str, reason: str) -> None:
    """`machine_id` 설비에 즉시 재측정을 요청한다.

    Raises:
        RecheckRequestError: `machine_id`가 비어 있는 등 요청 자체가 성립하지
            않는 경우. 실제 설비 프로토콜이 생기면 통신 실패(타임아웃,
            연결 오류 등)도 여기서 RecheckRequestError로 감싸 올려야 한다.
    """

    if not machine_id:
        raise RecheckRequestError("cannot request a recheck without machine_id")
    logger.info("immediate recheck requested for %s (reason=%s)", machine_id, reason)
