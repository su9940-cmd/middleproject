"""Mock outbound-notification adapter for EMERGENCY alerts.

No real paging/SMS/Slack channel is wired up yet, so "sending" a
notification means logging it at CRITICAL level - this module is the single
seam to replace with a real HTTP call once a channel is chosen. Standing in
for a missing external integration this way mirrors how `app.api.sensor_routes`
stands in for real IoT hardware today.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.exceptions import NotificationError

logger = logging.getLogger(__name__)


def send_alert(payload: dict[str, Any]) -> None:
    """Dispatch one immediate-alert notification.

    Raises `NotificationError` if the payload can't be dispatched (missing
    `alert_id`, or a lower-level delivery failure once a real channel exists).
    Callers (see `app.nodes.notification.send_immediate_alert`) are
    responsible for catching this and reporting it through
    `notification_status`/`notification_error` rather than letting it
    propagate as an unhandled node error.
    """

    alert_id = payload.get("alert_id")
    if not alert_id:
        raise NotificationError("cannot send an immediate alert without alert_id")

    logger.critical("IMMEDIATE ALERT %s: %s", alert_id, payload)
