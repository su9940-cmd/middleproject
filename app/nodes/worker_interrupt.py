"""Worker Interrupt 노드 — 체크리스트 전달 후 작업자 응답을 기다린다 (FR-10).

담당: E (인터페이스 엔지니어) — Worker Interrupt UI 연동.

interrupt()는 실제로 그래프 실행을 멈추고 체크포인트에 상태를 저장한다.
프론트엔드(WorkerInterruptScreen)는 이 payload를 그대로 받아 화면에
렌더링하고, 작업자가 제출하면 백엔드가 동일 thread_id로
Command(resume=worker_response)를 호출해 재개한다.
"""

from langgraph.types import interrupt

from app.graph.state import SafetyState


def worker_interrupt(state: SafetyState) -> dict:
    """체크리스트를 전달하고 작업자 응답이 resume될 때까지 대기한다 (FR-10).

    interrupt()에 전달하는 payload는 7.3절 "작업자 알림 출력" 표시 항목과
    동일한 필드로 구성한다 — WorkerInterruptScreen 컴포넌트의 props(state)와
    필드명이 그대로 대응된다.
    """
    payload = {
        "alert_id": state["alert_id"],
        "machine_id": state["machine_id"],
        "machine_type": state["machine_type"],
        "measured_at": state.get("measured_at"),
        "risk_level": state["risk_level"],
        "ml_risk_score": state["ml_risk_score"],
        "emergency_reasons": state.get("emergency_reasons", []),
        "final_checklist": state["final_checklist"],
        "notification_status": state.get("notification_status"),
        "immediate_alert_sent_at": state.get("immediate_alert_sent_at"),
    }

    worker_response = interrupt(payload)

    return {"worker_response": worker_response}