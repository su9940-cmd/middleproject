# C 담당 파트 - 백엔드/DB (센서 수신 슬라이스)

## 실행
```
uv sync
uv run uvicorn main:app --reload
```
서버가 시작될 때 `app.core.db.create_tables`가 자동으로 DB 테이블을 만듭니다(없으면 생성, 있으면 그대로 둠).

## 테스트
```
uv run pytest tests/ -q
```

## 설계 메모: 실제 IoT 센서 없음
아직 진짜 IoT 장비가 없어서, 15분 주기 자동 폴링(스케줄러) 대신 **사람이 직접 센서값을 입력**하는 방식으로 갑니다. `POST /sensors/ingest` 하나가 최초 측정값과 즉시재측정(Immediate Recheck) 값을 모두 받는 단일 진입점이고, 어느 쪽인지는 요청 본문의 `measurement_mode`(PERIODIC/IMMEDIATE_RECHECK)로만 구분합니다. 별도의 스케줄러/타이머는 없습니다.

## 이번 슬라이스에 포함된 것
- app/core/{enums,exceptions}.py, app/models/sensor.py, app/graph/state.py
  : 팀 공통 규약 파일 그대로
- app/core/config.py, app/core/db.py
  : 환경변수 기반 설정 + SQLAlchemy 비동기 엔진/세션 (기본 SQLite, `DATABASE_URL`로 교체 가능),
    `create_tables()`로 시작 시 테이블 자동 생성
- app/models/orm_models.py, app/repositories/{sensor,alert,checklist}_repository.py
  : SQLAlchemy 테이블 정의 + 센서/경보/체크리스트 저장·조회
- app/nodes/persistence.py
  : save_sensor_reading / save_alert_state / save_worker_response LangGraph 노드
    (state만 받아 변경 필드만 반환하는 규칙 준수)
- app/api/{sensor,alert,worker}_routes.py, main.py
  : IoT 센서 수신 API(정기/즉시재측정 겸용 단일 엔드포인트), 경보 조회 API, 작업자 응답 제출 API,
    공통 예외 → HTTP 응답 매핑(`main.py`의 `@app.exception_handler(ApplicationError)`).
    라우터 등록 완료.
- `POST /sensors/ingest` 동작:
  1. 원본 센서값을 무조건 저장(정상 포함, 전량 저장 정책)
  2. 해당 설비에 이미 열려있는 경보가 있는지 DB에서 조회 → 있으면 그 `alert_id`/`thread_id`를 재사용,
     없으면 새로 발급(그래프가 NORMAL로 끝나면 실제로 저장되지는 않음)
  3. 시작 시 한 번만 컴파일해 둔 LangGraph(`app.state.safety_graph`)를 `ainvoke`로 실행
  4. 결과로 나온 경보 상태를 DB에 반영
  - `predictive_agent`가 실패(예: 로컬에 학습된 모델 파일이 없음)하면 그래프가 `risk_policy`까지
    이어가다 죽는 대신 깨끗하게 멈추고, API는 센서값은 저장된 채로 502 대신 500 + `error_code`를
    반환합니다(직접 `TestClient`로 재현·검증함).
- app/nodes/alert_lifecycle.py (`alert_lifecycle_node`)
  : 원래 10-node 설계에는 없던 노드. `risk_policy`가 CAUTION/WARNING/EMERGENCY로 판정하면
    `recovery_node`(NORMAL 전용) 대신 이 노드가 먼저 실행되어 `alert_status`를 OPEN/ESCALATED로
    전이시키고, 그 다음에 RAG/Memory(+긴급 시 즉시알림)로 분기함. 규칙: 경보 없음/RESOLVED 상태에서
    비정상 → OPEN(긴급이면 바로 ESCALATED); WAITING_RECHECK/MONITORING 중 재발 → OPEN으로 복귀;
    이미 OPEN/IN_PROGRESS/ESCALATED면 그대로 유지하고 repeat_count만 누적; ESCALATED는 관리자
    조치 없이는 자동으로 안 내려감. `memory_context` 기반의 "악화/반복초과" 에스컬레이션은
    memory_agent가 아직 없어서 미반영 — 나중에 추가해야 함.
- app/services/notification_service.py, app/nodes/notification.py (`send_immediate_alert`)
  : EMERGENCY 즉시알림. **역할 E(선주님)의 실제 구현을 채택**(2026-07-24) — Slack Incoming Webhook으로
    발송하며, 웹훅 URL은 코드에 하드코딩하지 않고 `SLACK_ALERT_WEBHOOK_URL` 환경변수에서 읽음(미설정
    시 `NotificationError`). 발송 실패는 절대 raise하지 않고 `notification_status=FAILED`로만 보고 —
    raise하면 병렬로 도는 RAG/Memory/체크리스트 생성 경로가 `_with_error_handling`의 error_code 단락
    로직에 걸려 같이 끊겨버림(계약 8절 명시 사항). 테스트 환경에는 웹훅이 없으므로
    `app.nodes.notification.send_alert`를 모킹해서 검증(`tests/unit/test_notification.py`).
- app/services/iot_service.py (`request_measurement`)
  : **역할 C가 확정**(2026-07-24) — 역할 E가 제안한 시그니처(`request_measurement(machine_id, reason)`)와
    예외 계약(`RecheckRequestError`)을 그대로 채택. 실제 IoT 장비가 없는 데모라 재측정 데이터 자체는
    작업자가 `POST /sensors/ingest`에 `measurement_mode=IMMEDIATE_RECHECK`로 직접 다시 제출하므로,
    이 함수는 요청 사실을 로그로 남기고 정상 반환하는 것 외에는 할 일이 없음(실제 설비 프로토콜이
    생기면 본문만 교체).
- app/nodes/worker_interrupt.py (`worker_interrupt`), app/nodes/immediate_recheck.py (`request_immediate_recheck`)
  : `worker_interrupt`는 `langgraph.types.interrupt()`로 그래프를 일시정지하고 `Command(resume=worker_response)`로만
    재개됨 → `{"worker_response": ...}` 반환. `request_immediate_recheck`는 `iot_service.request_measurement`
    호출 후 성공 시 계약대로 `alert_status=WAITING_RECHECK` + `recheck_requested_at`, 실패 시
    `error_code=RECHECK_REQUEST_FAILED` 반환.
  : **역할 E(선주님, UI 브랜치/`WorkerInterruptScreen`)와 인터페이스 정합**(2026-07-24 합의) —
    - interrupt payload: `alert_id`/`checklist_id`뿐 아니라 `machine_id`/`machine_type`/`measured_at`/
      `risk_level`/`ml_risk_score`/`emergency_reasons`/`final_checklist`/`notification_status`/
      `immediate_alert_sent_at`까지 전부 포함 — `WorkerInterruptScreen`이 `state.*`로 직접 읽는
      필드와 1:1로 맞춤(원래 3개 필드만 넘기던 것에서 확장).
    - worker_response(재개 payload) 필드명: `WorkerInterruptScreen.handleSubmit`이 실제로 보내는
      `{response_id, alert_id, submitted_at, item_statuses: {checklist_item_id: status}, note}`
      기준으로 `ChecklistRepository.update_worker_response`를 맞춤(`items`/`worker_note` 기대하던
      이전 구현에서 변경). `item_statuses`는 항목별 status만 담고 있어서, 저장된 각 항목의 `status`만
      갱신하고 title/instruction/source_ids 등 나머지 필드는 그대로 보존.
- app/api/worker_routes.py (`POST /worker/checklists/{checklist_id}/respond`)
  : checklist_id → alert_id → thread_id(`{machine_id}:{alert_id}`) 역산 후
    `graph.ainvoke(Command(resume=...), config=...)`로 재개. 재개 전 `graph.aget_state(...).next`에
    `worker_interrupt`가 없으면(이미 응답 완료 등) 409로 거부. 재개 후 `save_worker_response` +
    `save_alert_state`로 결과 영속화.
- app/api/sensor_routes.py
  : 그래프가 `worker_interrupt`에서 멈추면(`ainvoke` 결과에 `"__interrupt__"` 키가 생김) 그 시점의
    `final_checklist`를 `ChecklistRepository.save_checklist`로 저장(재호출 대비 idempotent). 응답에
    `awaiting_worker_response`/`checklist_id` 추가. `measurement_mode=IMMEDIATE_RECHECK` 요청은
    계약대로 `recheck_reading_id`도 state에 채워서 넘김(이전엔 누락돼 있었음).
- app/api/alert_routes.py
  : `GET /alerts/{alert_id}/checklist` 추가(가장 최근 버전 체크리스트 조회 — `ChecklistRepository.get_latest_by_alert`).
- app/repositories/{alert,checklist}_repository.py
  : `AlertRepository.get_by_id`, `ChecklistRepository.{get_by_id,get_latest_by_alert}` 추가 — 위 재개
    플로우가 checklist_id만 가지고 thread_id를 역산하는 데 필요.
- app/core/enums.py (`MaintenanceRequestStatus`), app/models/orm_models.py (`MaintenanceRequestORM`),
  app/repositories/maintenance_repository.py, app/api/maintenance_routes.py
  : **정비 요청 승인 기능**(FR-14, `ManagerReviewScreen.jsx`용 — 코딩 프롬프트 12장에는 없던 신규 기능,
    2026-07-24 팀 논의로 role C 담당 확정). 팀 결정사항:
    - `alerts`와 분리된 별도 테이블(`maintenance_requests`) — 승인 생애주기가 경보 생애주기와 독립적.
    - 상태: `PENDING`/`APPROVED`/`REJECTED`/`DEFERRED`로 시작, 실제 정비완료 상태가 필요해지면 `COMPLETED` 추가.
    - API: `GET /maintenance-requests/pending`, `POST /maintenance-requests/{maintenance_request_id}/decision`.
    - 외부 JSON은 camelCase, 내부 DB/Python은 snake_case — 수동 별칭이 아니라
      `pydantic.alias_generators.to_camel`을 `alias_generator`로 지정해 자동 변환.
    - `maintenance_request_id = MR-{alert_id}`(타임스탬프 없음) — `action_draft_node`(role B)가
      아직 없어 같은 alert에 대해 여러 번 트리거될 수 있는 상황을 idempotent하게 처리하려는 의도
      (`ChecklistRepository.save_checklist`와 동일 패턴).
    - **아직 안 한 것**: `action_draft_node`(role B)가 `requires_maintenance_request`/`action_draft`를
      실제로 채우기 시작하면, 그 시점에 draft를 생성하는 persistence 노드(`create_draft` 호출)를
      그래프에 연결해야 함 — role B의 실제 출력 형태(title/priority/recommendation을 어떻게
      구성할지)를 보지 않고 지금 미리 만들면 추측성 매핑이 될 것 같아 스키마/API만 먼저 확정하고
      보류함.
- tests/unit/test_backend.py, tests/unit/test_{predictive_agent,risk_policy,recovery_node,graph_routes,alert_lifecycle,notification,immediate_recheck,iot_service,worker_interrupt,checklist_repository,maintenance_repository}.py,
  tests/integration/{test_safety_graph,test_sensor_ingest_api,test_worker_interrupt_flow,test_maintenance_routes}.py
  : 92건 전부 통과. `test_worker_interrupt_flow.py`는 rag_agent/memory_agent/action_draft_node/validator_agent
    (아직 없는 A/B 담당 노드)를 `sys.modules`에 최소 가짜 구현으로 꽂아 넣고, 실제 HTTP 요청으로
    EMERGENCY 접수 → 즉시알림 → 체크리스트 저장 → interrupt 정지 → 작업자 응답 → resume →
    WAITING_RECHECK까지 왕복 전체를 검증. `test_maintenance_routes.py`는 응답 JSON이 실제로
    camelCase인지(`maintenanceRequestId`, `alertId` 등)까지 검증.

## 셀프 점검(2026-07-24)에서 발견해 고친 것
- **`db/schema.sql`이 실제 스키마와 어긋나 있었음** — 원래 ER 다이어그램(Doc 03/F-01~F-10) 기반이라
  `risk_level`이 한글(정상/주의/경고/긴급), `alert_state`가 3단계(OPEN/MONITORING/RESOLVED)였는데
  실제 구현은 공통 계약의 영문 값 + 7단계 `AlertStatus`를 씀. `app/models/orm_models.py`와 1:1로
  맞춰 다시 씀(source of truth는 항상 orm_models.py). 아직 구현 안 된 `app_user`/`machine`/`incident`
  등 나머지 ER 테이블은 뺐음 — 필요해지면 요구분석서_폐루프_최종설계.docx 참고해 추가.
- **그 과정에서 발견한 실제 버그**: `SensorReadingORM.shift/experience/training` 컬럼이 SQLAlchemy
  `Enum` 기본 동작 때문에 멤버 *이름*("DAY")을 저장하고 있었음 — 계약값("Day")과 다름(내부적으로는
  같은 Enum 타입으로 왕복하니 안 터졌지만, 원본 SQL로 읽으면 잘못된 대소문자가 보임).
  `values_callable`로 실제 `.value`를 저장하도록 수정.
- **DB 실패 경로 테스트 추가** — `save_sensor_reading`/`save_alert_state`/`save_worker_response`
  노드와 `{Alert,Checklist,MaintenanceRequest}Repository`의 모든 쓰기 메서드에 대해, 세션 commit이
  실패하는 상황을 몹킹해 `DatabaseOperationError`(error_code=`DATABASE_OPERATION_FAILED`)로 올바르게
  래핑되는지 검증(이전엔 "선택적 필드 없음 → no-op" 경로만 테스트하고 실제 DB 오류 경로는 안 봄).
  `save_worker_response` 노드는 성공 경로 테스트조차 없었어서 같이 추가.
- **`SensorValidationError`가 정의만 되고 실제로 한 번도 안 쓰이던 문제** — `POST /sensors/ingest`의
  `reading: SensorReading` 파라미터는 FastAPI가 핸들러 실행 전에 자체 검증해서, 잘못된 값은
  `SensorValidationError`가 아니라 FastAPI 기본 `RequestValidationError`(`{"detail": [...]}`)로
  빠짐. `main.py`에 `RequestValidationError` 핸들러를 추가하되 `/sensors/ingest` 경로에만 좁혀서
  계약이 정한 `{"error_code": "SENSOR_VALIDATION_FAILED", ...}` 형태로 바꾸고, 다른 라우트는
  FastAPI 기본 응답을 그대로 유지(`request_validation_exception_handler`로 위임) — 다른 라우트까지
  전부 SENSOR_VALIDATION_FAILED로 바뀌지 않는지도 테스트로 확인.
- **`.env.example` 추가** — `DATABASE_URL`/`MODEL_PIPELINE_PATH`/`MODEL_METADATA_PATH`/
  `RISK_POLICY_VERSION`/`SLACK_ALERT_WEBHOOK_URL` 5개 환경변수를 문서화(전에는 코드를 뒤져야 알 수 있었음).

## UI 브랜치(역할 E) 병합 시 확인한 것
- **`pyproject.toml`에 `langgraph-checkpoint<4` 누락**으로 `from langgraph.types import interrupt`가
  임포트 시점에 깨져 있었음(`langgraph-checkpoint>=4`가 `langchain-core==1.0.3`의 `Reviver` 시그니처와
  안 맞음) — origin/UI에 직접 수정해서 push함(`langgraph-checkpoint<4` 추가 + `pytest` dev 의존성 선언).
- ID 생성(`app/core/ids.py`)은 role C 소관이라 이번 병합 대상에서 제외 — 별도로 발견된
  "경보생명주기" 다운로드 폴더(다른 role C 시도로 추정)의 `RD-M-0101-...123` 포맷은 이 저장소의
  `RD-M0101-...`(계약 예시와 일치)와 다르므로 병합하지 않음.

## 다음 슬라이스 (아직 미구현)
- Memory Agent가 조회할 이력 쿼리(직전 체크리스트, 정비 이력 등)는 아직 리포지토리에 없음 — 필요해지면 추가
- memory_agent가 생기면 alert_lifecycle_node의 에스컬레이션 조건에 "악화 추세"/"반복 한도 초과" 반영
- action_draft_node(role B)가 실제로 생기면 `MaintenanceRequestRepository.create_draft`를 호출하는
  persistence 노드를 그래프에 연결 — title/recommendation/priority를 action_draft에서 어떻게
  뽑아낼지는 role B의 실제 출력을 보고 정해야 함
