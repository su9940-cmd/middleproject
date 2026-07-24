"""실제 알림 발송 채널 구현 (Slack Incoming Webhook).

역할 E(인터페이스 엔지니어) 구현을 채택. API 키/URL 같은 민감정보는 코드에
직접 작성하지 않고 환경 변수(SLACK_ALERT_WEBHOOK_URL)에서 읽는다.
"""

from __future__ import annotations

import os
from typing import Any

import requests

from app.core.exceptions import NotificationError


def send_alert(alert_id: str, machine_id: str, message: str) -> None:
    """Slack 채널로 긴급 알림을 발송한다.

    Args:
        alert_id: 경보 ID (예: "AL-M0101-20260723T101500")
        machine_id: 설비 ID
        message: 알림 본문

    Raises:
        NotificationError: 웹훅 URL 미설정, 네트워크 오류, 4xx/5xx 응답 등
            알림 발송이 실패한 모든 경우. `send_immediate_alert` 노드가 이
            예외를 잡아 notification_status=FAILED로 변환한다.
    """
    webhook_url = os.environ.get("SLACK_ALERT_WEBHOOK_URL")
    if not webhook_url:
        raise NotificationError("SLACK_ALERT_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")

    payload: dict[str, Any] = {
        "text": f":rotating_light: {message}",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*:rotating_light: 긴급 알림*\n{message}"},
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"alert_id: `{alert_id}` · machine_id: `{machine_id}`"}
                ],
            },
        ],
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise NotificationError(
            f"Slack 알림 발송 실패: {exc}",
            details={"alert_id": alert_id, "machine_id": machine_id},
        ) from exc
