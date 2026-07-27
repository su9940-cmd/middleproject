-- ============================================================================
-- 공장 화재위험 멀티에이전트 — PostgreSQL 스키마
--
-- Source of truth: app/models/orm_models.py (SQLAlchemy). 이 파일은 그 DDL을
-- 손으로 옮겨 적은 참고 문서로, 실제 실행 중인 앱은 SQLAlchemy의
-- `Base.metadata.create_all()`(app/core/db.py:create_tables)이 스키마를
-- 만든다 - Alembic 마이그레이션은 아직 없다(MVP 단계, 팀 전체가 아직 안 씀).
-- 이 파일이 orm_models.py와 어긋나면 orm_models.py가 항상 맞다.
--
-- 이전 버전(ER Diagram Doc 03 / 요구분석 정의서 Doc 02 기반, F-01~F-10)은
-- risk_level을 한글(정상/주의/경고/긴급)로, alert_state를 3단계
-- (OPEN/MONITORING/RESOLVED)로 정의했었는데, 실제 구현은 공통 계약
-- (app/core/enums.py)의 영문 값과 7단계 AlertStatus를 그대로 쓰므로 여기서
-- 그에 맞춰 다시 썼다. app_user/machine/incident/external_ref/internal_ref/
-- hitl_decision/checklist_submission 등 원래 ER 다이어그램에 있던 나머지
-- 테이블은 아직 SQLAlchemy 레이어에 구현되지 않아 이 파일에서도 뺐다 -
-- 필요해지면 요구분석서_폐루프_최종설계.docx를 참고해 다시 추가할 것.
-- ============================================================================

-- ------------------------------------------------------------
-- ENUM 타입 (app/core/enums.py와 1:1 대응 — 값의 대소문자까지 정확히 일치)
-- ------------------------------------------------------------
CREATE TYPE machine_type_enum             AS ENUM ('REACTOR', 'COMPRESSOR', 'STORAGE_TANK', 'PUMP');
CREATE TYPE measurement_mode_enum         AS ENUM ('PERIODIC', 'IMMEDIATE_RECHECK');
CREATE TYPE shift_enum                    AS ENUM ('Day', 'Night');
CREATE TYPE experience_level_enum         AS ENUM ('Junior', 'Senior');
CREATE TYPE training_status_enum          AS ENUM ('Yes', 'No');
CREATE TYPE risk_level_enum               AS ENUM ('NORMAL', 'CAUTION', 'WARNING', 'EMERGENCY');
CREATE TYPE alert_status_enum             AS ENUM (
    'NONE', 'OPEN', 'IN_PROGRESS', 'WAITING_RECHECK', 'MONITORING', 'RESOLVED', 'ESCALATED'
);
CREATE TYPE notification_status_enum      AS ENUM ('NOT_REQUIRED', 'PENDING', 'SENT', 'FAILED');
CREATE TYPE maintenance_request_status_enum AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'DEFERRED');

-- ------------------------------------------------------------
-- SENSOR_READINGS  (app.models.orm_models.SensorReadingORM)
-- 전량 저장 정책 — 정상 포함, POST /sensors/ingest가 받는 그대로 저장.
-- ------------------------------------------------------------
CREATE TABLE sensor_readings (
    reading_id        VARCHAR(64) PRIMARY KEY,
    machine_id        VARCHAR(32) NOT NULL,
    machine_type      machine_type_enum NOT NULL,

    measured_at       TIMESTAMPTZ NOT NULL,
    measurement_mode  measurement_mode_enum NOT NULL,

    temperature       REAL NOT NULL,
    pressure          REAL NOT NULL,
    humidity          REAL NOT NULL,
    vibration         REAL NOT NULL,
    speed             REAL NOT NULL,
    age               INT NOT NULL,
    service_days      INT NOT NULL,
    gas               REAL NOT NULL,
    sparks            INT NOT NULL,

    shift             shift_enum NOT NULL,
    experience        experience_level_enum NOT NULL,
    training          training_status_enum NOT NULL,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sensor_readings_machine ON sensor_readings (machine_id);

-- ------------------------------------------------------------
-- ALERTS  (app.models.orm_models.AlertORM)
-- 설비별 경보 생애주기. alert_id를 기본키로 upsert(없으면 생성, 있으면 갱신).
-- ------------------------------------------------------------
CREATE TABLE alerts (
    alert_id                      VARCHAR(64) PRIMARY KEY,
    thread_id                     VARCHAR(64) NOT NULL,
    machine_id                    VARCHAR(32) NOT NULL,
    machine_type                  machine_type_enum NOT NULL,
    reading_id                    VARCHAR(64) NOT NULL,

    risk_level                    risk_level_enum NOT NULL,
    alert_status                  alert_status_enum NOT NULL DEFAULT 'OPEN',

    repeat_count                  INT NOT NULL DEFAULT 0,
    consecutive_normal_count      INT NOT NULL DEFAULT 0,

    emergency_reasons             JSONB NOT NULL DEFAULT '[]',
    notification_status           notification_status_enum NOT NULL DEFAULT 'NOT_REQUIRED',

    requires_maintenance_request  BOOLEAN NOT NULL DEFAULT false,
    maintenance_request_id        VARCHAR(64),

    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alerts_machine ON alerts (machine_id);
COMMENT ON TABLE alerts IS
    'ESCALATED는 관리자 조치 없이는 자동으로 안 내려감(app.nodes.alert_lifecycle 참고) - '
    'DB 제약으로는 상태 전이 순서를 표현하지 않고 애플리케이션 계층에서 강제한다.';

-- ------------------------------------------------------------
-- CHECKLISTS  (app.models.orm_models.ChecklistORM)
-- Validator Agent(role B)가 생성한 체크리스트 + 작업자 응답.
-- ------------------------------------------------------------
CREATE TABLE checklists (
    checklist_id                  VARCHAR(64) PRIMARY KEY,
    alert_id                      VARCHAR(64) NOT NULL,
    version                       INT NOT NULL DEFAULT 1,

    risk_level                    VARCHAR(32) NOT NULL,
    action_phase                  VARCHAR(32) NOT NULL,

    items                         JSONB NOT NULL,
    supporting_references         JSONB NOT NULL DEFAULT '[]',
    worker_note                   TEXT,

    requires_manager_report       BOOLEAN NOT NULL DEFAULT false,
    requires_maintenance_request  BOOLEAN NOT NULL DEFAULT false,

    completed_at                  TIMESTAMPTZ,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_checklists_alert ON checklists (alert_id);

-- ------------------------------------------------------------
-- MAINTENANCE_REQUESTS  (app.models.orm_models.MaintenanceRequestORM)
-- FR-14, 코딩 프롬프트 12장에는 없던 신규 기능(2026-07-24 팀 결정으로 role C
-- 담당). alerts와 별도 테이블 — 승인 생애주기가 경보 생애주기와 독립적이다.
-- maintenance_request_id = 'MR-' || alert_id (타임스탬프 없음, idempotent).
-- ------------------------------------------------------------
CREATE TABLE maintenance_requests (
    maintenance_request_id  VARCHAR(64) PRIMARY KEY,
    alert_id                 VARCHAR(64) NOT NULL,
    machine_id                VARCHAR(32) NOT NULL,
    machine_type               machine_type_enum NOT NULL,

    title                      VARCHAR(200) NOT NULL,
    recommendation             TEXT NOT NULL,
    priority                   VARCHAR(20) NOT NULL,

    status                     maintenance_request_status_enum NOT NULL DEFAULT 'PENDING',
    decided_by                 VARCHAR(100),
    decision_comment           TEXT,
    decided_at                 TIMESTAMPTZ,

    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_maintenance_requests_alert ON maintenance_requests (alert_id);
CREATE INDEX idx_maintenance_requests_status ON maintenance_requests (status);
