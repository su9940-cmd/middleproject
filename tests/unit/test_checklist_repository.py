"""Unit tests for `app.repositories.checklist_repository.ChecklistRepository`
and the `AlertRepository.get_by_id` lookup the worker-response resume flow
depends on (see `app.api.worker_routes`)."""

from __future__ import annotations

import pytest

from app.core import db
from app.core.enums import AlertStatus, MachineType, RiskLevel
from app.core.exceptions import DatabaseOperationError
from app.models.orm_models import Base
from app.repositories.alert_repository import AlertRepository
from app.repositories.checklist_repository import ChecklistRepository


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


def _checklist_data(**overrides) -> dict:
    data = {
        "checklist_id": "CL-AL-M0101-001-V1",
        "alert_id": "AL-M0101-001",
        "version": 1,
        "risk_level": "EMERGENCY",
        "action_phase": "EMERGENCY",
        "items": [
            {
                "checklist_item_id": "CI-1",
                "action_id": "ACT-1",
                "title": "냉각수 밸브 개방",
                "instruction": "즉시 밸브를 연다.",
                "priority": 1,
                "source_ids": ["SOP-1"],
                "status": "PENDING",
                "worker_note": None,
                "completed_at": None,
            }
        ],
        "requires_manager_report": True,
        "requires_maintenance_request": False,
    }
    data.update(overrides)
    return data


@pytest.mark.asyncio
async def test_save_checklist_then_get_by_id(async_session):
    repo = ChecklistRepository(async_session)
    saved = await repo.save_checklist(_checklist_data())
    assert saved.checklist_id == "CL-AL-M0101-001-V1"

    fetched = await repo.get_by_id("CL-AL-M0101-001-V1")
    assert fetched is not None
    assert fetched.alert_id == "AL-M0101-001"
    assert fetched.items[0]["checklist_item_id"] == "CI-1"


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(async_session):
    repo = ChecklistRepository(async_session)
    assert await repo.get_by_id("CL-does-not-exist-V1") is None


@pytest.mark.asyncio
async def test_save_checklist_is_idempotent(async_session):
    """A second `save_checklist` call for the same id must not violate the primary key."""

    repo = ChecklistRepository(async_session)
    first = await repo.save_checklist(_checklist_data())
    second = await repo.save_checklist(_checklist_data())
    assert first.checklist_id == second.checklist_id


@pytest.mark.asyncio
async def test_get_latest_by_alert_picks_the_highest_version(async_session):
    repo = ChecklistRepository(async_session)
    await repo.save_checklist(_checklist_data(checklist_id="CL-AL-M0101-001-V1", version=1))
    await repo.save_checklist(_checklist_data(checklist_id="CL-AL-M0101-001-V2", version=2))

    latest = await repo.get_latest_by_alert("AL-M0101-001")
    assert latest is not None
    assert latest.checklist_id == "CL-AL-M0101-001-V2"


@pytest.mark.asyncio
async def test_update_worker_response_sets_items_note_and_completed_at(async_session):
    """worker_response matches what WorkerInterruptScreen.handleSubmit (role E) sends:
    `item_statuses` (a status per checklist_item_id) + `note`, not `items`/`worker_note`."""

    repo = ChecklistRepository(async_session)
    await repo.save_checklist(_checklist_data())

    updated = await repo.update_worker_response(
        "CL-AL-M0101-001-V1",
        {"item_statuses": {"CI-1": "COMPLETED"}, "note": "완료"},
    )

    assert updated.worker_note == "완료"
    assert updated.completed_at is not None
    # Only `status` changes - title/instruction/source_ids/etc. must survive.
    assert updated.items[0]["status"] == "COMPLETED"
    assert updated.items[0]["title"] == "냉각수 밸브 개방"
    assert updated.items[0]["source_ids"] == ["SOP-1"]


@pytest.mark.asyncio
async def test_update_worker_response_ignores_unknown_item_ids(async_session):
    repo = ChecklistRepository(async_session)
    await repo.save_checklist(_checklist_data())

    updated = await repo.update_worker_response(
        "CL-AL-M0101-001-V1",
        {"item_statuses": {"CI-does-not-exist": "COMPLETED"}, "note": "완료"},
    )

    assert updated.items[0]["status"] == "PENDING"  # unchanged


@pytest.mark.asyncio
async def test_update_worker_response_raises_when_checklist_missing(async_session):
    repo = ChecklistRepository(async_session)

    with pytest.raises(DatabaseOperationError):
        await repo.update_worker_response("CL-does-not-exist-V1", {"item_statuses": {}})


@pytest.mark.asyncio
async def test_save_checklist_wraps_db_errors(async_session, monkeypatch):
    async def _raise(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(async_session, "commit", _raise)

    with pytest.raises(DatabaseOperationError) as exc_info:
        await ChecklistRepository(async_session).save_checklist(_checklist_data())
    assert exc_info.value.error_code == "DATABASE_OPERATION_FAILED"


@pytest.mark.asyncio
async def test_update_worker_response_wraps_db_errors(async_session, monkeypatch):
    await ChecklistRepository(async_session).save_checklist(_checklist_data())

    async def _raise(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(async_session, "commit", _raise)

    with pytest.raises(DatabaseOperationError) as exc_info:
        await ChecklistRepository(async_session).update_worker_response(
            "CL-AL-M0101-001-V1", {"item_statuses": {"CI-1": "COMPLETED"}}
        )
    assert exc_info.value.error_code == "DATABASE_OPERATION_FAILED"


@pytest.mark.asyncio
async def test_alert_repository_get_by_id(async_session):
    await AlertRepository(async_session).upsert_alert_state(
        {
            "alert_id": "AL-M0101-001",
            "thread_id": "M-0101:AL-M0101-001",
            "machine_id": "M-0101",
            "machine_type": MachineType.REACTOR,
            "reading_id": "RD-M0101-001",
            "risk_level": RiskLevel.EMERGENCY,
            "alert_status": AlertStatus.ESCALATED,
        }
    )

    alert = await AlertRepository(async_session).get_by_id("AL-M0101-001")
    assert alert is not None
    assert alert.machine_id == "M-0101"
    assert alert.alert_status == AlertStatus.ESCALATED


@pytest.mark.asyncio
async def test_alert_repository_get_by_id_returns_none_when_missing(async_session):
    assert await AlertRepository(async_session).get_by_id("AL-does-not-exist") is None
