-- ============================================================================
-- 공장 화재위험 멀티에이전트 — PostgreSQL 스키마
--
-- Source: ER Diagram (Doc 03) / 요구분석 정의서·요구사항 명세서 (Doc 02)
--         F-01~F-10, 페르소나 2명(현장관리자·안전관리자), checklist_type 3-way
-- Target: PostgreSQL (pyproject.toml의 psycopg2-binary / langchain-postgres /
--         pgvector 스택과 동일 DB에 붙는 것을 전제로 작성)
--
-- 주의: ER 다이어그램 대비 SENSOR_READING에 workers/factory/region/exp 4개
-- 컬럼을 추가했습니다. industrial_fire_custom_accident_ml.ipynb의
-- feature_columns(numeric_features+categorical_features)에는 있는데 ER
-- 다이어그램 작성 시 빠져 있던 걸 이번에 발견해서 반영한 것 — 이 컬럼들이
-- 없으면 predictive_ml_agent(F-01)가 실제 저장된 모델을 애초에 돌릴 수 없습니다.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ------------------------------------------------------------
-- ENUM 타입
-- ------------------------------------------------------------
CREATE TYPE machine_type_enum       AS ENUM ('REACTOR', 'COMPRESSOR', 'STORAGE_TANK', 'PUMP');
CREATE TYPE risk_level_enum         AS ENUM ('정상', '주의', '경고', '긴급');
CREATE TYPE alert_state_enum        AS ENUM ('OPEN', 'MONITORING', 'RESOLVED');
CREATE TYPE priority_enum           AS ENUM ('low', 'medium', 'high');
CREATE TYPE checklist_type_enum     AS ENUM ('FIRST_STANDARD', 'FIRST_EMERGENCY', 'ESCALATION');
CREATE TYPE submission_outcome_enum AS ENUM ('TRUE_POSITIVE', 'FALSE_POSITIVE', 'UNRESOLVED');
CREATE TYPE maintenance_status_enum AS ENUM ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED');
CREATE TYPE user_role_enum          AS ENUM ('현장관리자', '안전관리자');
CREATE TYPE shift_enum              AS ENUM ('Day', 'Night');
CREATE TYPE training_enum           AS ENUM ('Yes', 'No');
CREATE TYPE exp_enum                AS ENUM ('Junior', 'Senior');

-- ------------------------------------------------------------
-- APP_USER  ("user"는 예약어라 app_user로 명명)
-- 역할 2종(현장관리자·안전관리자) — 정비담당자/ML운영자는 범위 밖,
-- 필요해지면 user_role_enum에 값만 추가하면 됨 (스키마 변경 불필요).
-- ------------------------------------------------------------
CREATE TABLE app_user (
    user_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(100) NOT NULL,
    role       user_role_enum NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- MACHINE  (machine_profiles.json과 동일한 자연키 사용)
-- ------------------------------------------------------------
CREATE TABLE machine (
    machine_id      VARCHAR(20) PRIMARY KEY,       -- 예: 'M-0101'
    machine_type    machine_type_enum NOT NULL,
    display_name    VARCHAR(100) NOT NULL,
    manual_id       VARCHAR(50) NOT NULL,           -- data/SOP_260721/*.md 참조, DB FK 아님
    profile_version VARCHAR(20) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- SENSOR_READING  (전량 저장 정책 — 정상 포함, F-01 입력 그대로)
-- ------------------------------------------------------------
CREATE TABLE sensor_reading (
    reading_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id    VARCHAR(20) NOT NULL REFERENCES machine(machine_id) ON DELETE RESTRICT,
    ts            TIMESTAMPTZ NOT NULL,
    workers       INT NOT NULL,
    factory       VARCHAR(50) NOT NULL,
    region        VARCHAR(50) NOT NULL,
    shift         shift_enum NOT NULL,
    exp           exp_enum NOT NULL,
    training      training_enum NOT NULL,
    temp          REAL NOT NULL,
    pressure      REAL NOT NULL,
    humidity      REAL NOT NULL,
    vibration     REAL NOT NULL,
    speed         REAL NOT NULL,
    age           INT NOT NULL,
    service_days  INT NOT NULL,
    gas           REAL NOT NULL,
    sparks        INT NOT NULL,
    ml_risk_score REAL,               -- F-01 산출, 배치 채점 전에는 NULL
    risk_level    risk_level_enum,    -- ML 임계값 + 긴급 규칙 적용 후 산출
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sensor_reading_machine_ts ON sensor_reading (machine_id, ts DESC);
COMMENT ON TABLE sensor_reading IS
    '15분 주기 전량 저장(정상 포함). 기준선 비교·해결 증명·추세 감지·모델 재학습 라벨 확보 목적.';

-- ------------------------------------------------------------
-- ALERT  (F-07/F-09, 설비별 생애주기 OPEN→MONITORING→RESOLVED)
-- ------------------------------------------------------------
CREATE TABLE alert (
    alert_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id   VARCHAR(20) NOT NULL REFERENCES machine(machine_id) ON DELETE RESTRICT,
    state        alert_state_enum NOT NULL DEFAULT 'OPEN',
    risk_level   risk_level_enum NOT NULL,
    repeat_count INT NOT NULL DEFAULT 0,
    opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ,
    CONSTRAINT chk_alert_resolved_after_open CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
);
CREATE INDEX idx_alert_open ON alert (machine_id) WHERE state <> 'RESOLVED';
COMMENT ON TABLE alert IS
    'FC-15: 긴급은 즉시재측정 정상 확인만으로 RESOLVED 자동전환 금지, MONITORING까지만 — 애플리케이션 계층에서 강제 (DB 제약으로는 상태전이 순서를 표현하지 않음).';

-- ------------------------------------------------------------
-- INCIDENT  (F-06, 매 주기 스냅샷 — Alert 생애주기 동안 여러 개 쌓임)
-- ------------------------------------------------------------
CREATE TABLE incident (
    incident_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id      UUID NOT NULL REFERENCES alert(alert_id) ON DELETE CASCADE,
    anomaly_score REAL NOT NULL,
    priority      priority_enum NOT NULL,
    summary_3line TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_incident_alert ON incident (alert_id, created_at DESC);

-- ------------------------------------------------------------
-- EXTERNAL_REF / INTERNAL_REF  (F-02 산안법 / F-03 사내매뉴얼)
-- ------------------------------------------------------------
CREATE TABLE external_ref (
    ref_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incident(incident_id) ON DELETE CASCADE,
    clause      VARCHAR(200) NOT NULL,   -- 예: '안전보건기준에 관한 규칙 제273조'
    url         TEXT NOT NULL
);

CREATE TABLE internal_ref (
    ref_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id UUID NOT NULL REFERENCES incident(incident_id) ON DELETE CASCADE,
    manual_id   VARCHAR(50) NOT NULL,
    url         TEXT NOT NULL
);

-- ------------------------------------------------------------
-- CHECKLIST / CHECKLIST_ITEM / CHECKLIST_SUBMISSION  (F-08)
-- checklist_type 3-way: FIRST_STANDARD / FIRST_EMERGENCY / ESCALATION
-- (최초-긴급을 최초-일반과 분리 유지 — 설계 검토 결과)
-- ------------------------------------------------------------
CREATE TABLE checklist (
    checklist_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id    UUID NOT NULL REFERENCES incident(incident_id) ON DELETE CASCADE,
    checklist_type checklist_type_enum NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE checklist_item (
    item_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checklist_id UUID NOT NULL REFERENCES checklist(checklist_id) ON DELETE CASCADE,
    seq          SMALLINT NOT NULL,
    description  TEXT NOT NULL,
    is_completed BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (checklist_id, seq)
);
COMMENT ON COLUMN checklist_item.is_completed IS
    'ESCALATION 체크리스트 생성 시 "이전 수행 완료 항목 제외" 로직이 여기를 조회함.';

CREATE TABLE checklist_submission (
    submission_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checklist_id  UUID NOT NULL REFERENCES checklist(checklist_id) ON DELETE CASCADE,
    user_id       UUID NOT NULL REFERENCES app_user(user_id) ON DELETE RESTRICT,
    outcome       submission_outcome_enum,  -- 확장 후보 필드, 지금은 nullable/미사용
    notes         TEXT,
    evidence_url  TEXT,
    submitted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (checklist_id)   -- 1 checklist : 0..1 submission
);

-- ------------------------------------------------------------
-- HITL_DECISION  (F-05, 법령-매뉴얼 모순 시에만 생성)
-- ------------------------------------------------------------
CREATE TABLE hitl_decision (
    decision_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id    UUID NOT NULL REFERENCES incident(incident_id) ON DELETE CASCADE,
    reason         TEXT NOT NULL,
    human_decision TEXT,
    decided_by     UUID REFERENCES app_user(user_id) ON DELETE SET NULL,
    decided_at     TIMESTAMPTZ,
    UNIQUE (incident_id)   -- 1 incident : 0..1 HITL decision
);

-- ------------------------------------------------------------
-- MAINTENANCE_REQUEST  (F-04, 누적 경보 자동 트리거 또는 수동 요청)
-- ------------------------------------------------------------
CREATE TABLE maintenance_request (
    request_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_id             VARCHAR(20) NOT NULL REFERENCES machine(machine_id) ON DELETE RESTRICT,
    triggered_by_alert_id  UUID REFERENCES alert(alert_id) ON DELETE SET NULL,  -- nullable: 수동 요청 허용
    status                 maintenance_status_enum NOT NULL DEFAULT 'SCHEDULED',
    scheduled_at           TIMESTAMPTZ,
    completed_at           TIMESTAMPTZ,
    CONSTRAINT chk_maintenance_completed_after_scheduled
        CHECK (completed_at IS NULL OR scheduled_at IS NULL OR completed_at >= scheduled_at)
);
CREATE INDEX idx_maintenance_machine ON maintenance_request (machine_id);
