"""IoT 재측정 요청 서비스 — 제안 인터페이스.

주의: 이 파일의 실제 구현(설비와의 통신, 프로토콜, 재시도 정책 등)은
C(백엔드·DB 엔지니어) 담당 영역이다. 여기서는 request_immediate_recheck
노드가 기대하는 함수 시그니처만 먼저 제안해둔 것이며, C와 실제 계약
(인자, 예외 종류, 타임아웃 처리)을 맞춘 뒤 이 파일을 C가 확정해야 한다.
"""

from app.core.exceptions import RecheckRequestError


def request_measurement(machine_id: str, reason: str) -> None:
    """지정된 설비에 즉시 측정을 요청한다.

    Args:
        machine_id: 재측정을 요청할 설비 ID (예: "M-0101").
        reason: 요청 사유 (예: "immediate_recheck").

    Raises:
        RecheckRequestError: 설비 통신 실패, 타임아웃 등으로 재측정 요청이
            실패한 경우. 실제 구현에서는 저수준 예외(타임아웃, 연결 오류 등)를
            여기서 RecheckRequestError로 감싸서 올려야 한다.

    실제 구현 전까지는 RecheckRequestError를 발생시켜, 이 서비스가
    아직 완성되지 않았음을 계약을 어기지 않는 형태로 알린다.
    """
    raise RecheckRequestError(
        "C 담당: 실제 IoT 재측정 요청 구현 필요",
        details={"machine_id": machine_id, "reason": reason},
    )