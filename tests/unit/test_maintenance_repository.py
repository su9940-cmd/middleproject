"""Unit tests for `app.repositories.maintenance_repository.MaintenanceRequestRepository`."""

from __future__ import annotations

import pytest

from app.core import db
from app.core.enums import MachineType, MaintenanceRequestStatus
from app.models.orm_models import Base
from app.repositories.maintenance_repository import MaintenanceRequestRepository


@pytest.fixture
async def async_session():
    """Point the shared DB engine at a fresh in-memory SQLite DB for this test."""

    db.configure("sqlite+aiosqlite:///:memory:")
    engine = db.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with db.session_scope() as session:
        yield session

    await engine.dispose()


def _draft_data(**overrides) -> dict:
    data = {
        "maintenance_request_id": "MR-AL-M0101-001",
        "alert_id": "AL-M0101-001",
        "machine_id": "M-0101",
        "machine_type": MachineType.REACTOR,
        "title": "가스 감지 센서 및 안전밸브 정밀 점검",
        "recommendation": "재발 방지를 위해 가스 감지 센서 교정 상태를 재점검할 것을 권장합니다.",
        "priority": "높음",
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_create_draft_then_get_by_id(async_session):
    repo = MaintenanceRequestRepository(async_session)
    created = await repo.create_draft(_draft_data())

    assert created.maintenance_request_id == "MR-AL-M0101-001"
    assert created.status == MaintenanceRequestStatus.PENDING

    fetched = await repo.get_by_id("MR-AL-M0101-001")
    assert fetched is not None
    assert fetched.alert_id == "AL-M0101-001"


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(async_session):
    repo = MaintenanceRequestRepository(async_session)
    assert await repo.get_by_id("MR-does-not-exist") is None


@pytest.mark.asyncio
async def test_create_draft_is_idempotent(async_session):
    """A second create_draft call for the same id must not violate the primary key."""

    repo = MaintenanceRequestRepository(async_session)
    first = await repo.create_draft(_draft_data())
    second = await repo.create_draft(_draft_data())

    assert first.maintenance_request_id == second.maintenance_request_id


@pytest.mark.asyncio
async def test_list_pending_excludes_decided_requests(async_session):
    repo = MaintenanceRequestRepository(async_session)
    await repo.create_draft(_draft_data(maintenance_request_id="MR-AL-M0101-001"))
    await repo.create_draft(_draft_data(maintenance_request_id="MR-AL-M0102-001", alert_id="AL-M0102-001"))
    await repo.apply_decision(
        "MR-AL-M0101-001",
        decision=MaintenanceRequestStatus.APPROVED,
        decided_by="manager-1",
        comment="승인",
    )

    pending = await repo.list_pending()

    assert [r.maintenance_request_id for r in pending] == ["MR-AL-M0102-001"]


@pytest.mark.asyncio
async def test_apply_decision_sets_status_decided_by_comment_and_decided_at(async_session):
    repo = MaintenanceRequestRepository(async_session)
    await repo.create_draft(_draft_data())

    updated = await repo.apply_decision(
        "MR-AL-M0101-001",
        decision=MaintenanceRequestStatus.REJECTED,
        decided_by="manager-1",
        comment="예산 부족으로 반려",
    )

    assert updated.status == MaintenanceRequestStatus.REJECTED
    assert updated.decided_by == "manager-1"
    assert updated.decision_comment == "예산 부족으로 반려"
    assert updated.decided_at is not None
