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
- tests/unit/test_backend.py, tests/unit/test_{predictive_agent,risk_policy,recovery_node,graph_routes,alert_lifecycle}.py,
  tests/integration/{test_safety_graph,test_sensor_ingest_api}.py
  : 42건 전부 통과. `test_sensor_ingest_api.py`는 실제 HTTP 요청 → DB 저장 → 재조회까지 왕복 검증.

## 다음 슬라이스 (아직 미구현)
- alert_routes/worker_routes를 그래프 재개(worker_interrupt resume)와 연결
- Memory Agent가 조회할 이력 쿼리(직전 체크리스트, 정비 이력 등)는 아직 리포지토리에 없음 — 필요해지면 추가
- memory_agent가 생기면 alert_lifecycle_node의 에스컬레이션 조건에 "악화 추세"/"반복 한도 초과" 반영
