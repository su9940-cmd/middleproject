import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Badge from "../components/Badge.jsx";
import {
  MACHINES,
  ALERT_STATUS_LABELS,
  RISK_LEVEL_LABELS,
  RISK_LEVELS,
  RISK_LEVEL_PRESETS,
  SAFE_RECHECK_PRESET,
} from "../constants/machines.js";
import { getActiveAlert } from "../api/alerts.js";
import { ingestSensorReading } from "../api/sensors.js";

function initialState() {
  return Object.fromEntries(
    MACHINES.map((machine) => [machine.machineId, { alert: null, loading: true, error: null }]),
  );
}

function randomRiskLevel() {
  return RISK_LEVELS[Math.floor(Math.random() * RISK_LEVELS.length)];
}

function formatTime(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function buildReadingId(machineId) {
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0];
  return `RD-${machineId.replace(/-/g, "")}-${timestamp}`;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [statuses, setStatuses] = useState(initialState);
  const [submittingId, setSubmittingId] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  const refreshMachine = useCallback(async (machineId) => {
    setStatuses((prev) => ({ ...prev, [machineId]: { ...prev[machineId], loading: true, error: null } }));
    try {
      const alert = await getActiveAlert(machineId);
      setStatuses((prev) => ({ ...prev, [machineId]: { ...prev[machineId], alert, loading: false, error: null } }));
    } catch (error) {
      setStatuses((prev) => ({ ...prev, [machineId]: { ...prev[machineId], alert: null, loading: false, error } }));
    }
  }, []);

  useEffect(() => {
    MACHINES.forEach((machine) => refreshMachine(machine.machineId));
  }, [refreshMachine]);

  function handleCardClick(machine, alert) {
    if (!alert) return;
    navigate(`/machines/${machine.machineId}/worker`);
  }

  async function handleSensorInput(event, machine) {
    event.stopPropagation();
    setLastResult(null);
    setSubmittingId(machine.machineId);
    const level = randomRiskLevel();
    try {
      const payload = {
        ...SAFE_RECHECK_PRESET,
        ...RISK_LEVEL_PRESETS[machine.machineType][level],
        reading_id: buildReadingId(machine.machineId),
        machine_id: machine.machineId,
        machine_type: machine.machineType,
        measured_at: new Date().toISOString(),
        measurement_mode: "PERIODIC",
      };
      const result = await ingestSensorReading(payload);
      setLastResult({ machineId: machine.machineId, ...result });
      await refreshMachine(machine.machineId);
    } catch (error) {
      setLastResult({ machineId: machine.machineId, error });
    } finally {
      setSubmittingId(null);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>알림 센터</h1>
        <p>
          활성 경보가 있는 설비를 탭하면 체크리스트로 이동해요. 실제 IoT 장비가 없는 데모라 "센서 입력"을
          누르면 정상 → 주의 → 경고 → 긴급 순으로 한 단계씩 시뮬레이션 값을 제출합니다.
        </p>
      </div>

      <div className="alert-list">
        {MACHINES.map((machine) => {
          const { alert, loading, error } = statuses[machine.machineId] || {
            alert: null,
            loading: true,
            error: null,
          };
          const clickable = Boolean(alert);
          const submitting = submittingId === machine.machineId;
          const result = lastResult?.machineId === machine.machineId ? lastResult : null;

          return (
            <div
              key={machine.machineId}
              className={`alert-list-item${clickable ? " clickable" : ""}`}
              onClick={() => handleCardClick(machine, alert)}
            >
              <div className="row-top">
                {!loading && !error && <Badge level={alert?.risk_level || "NORMAL"} />}
                <span className="machine-name">{machine.displayName}</span>
                <button
                  type="button"
                  className="ghost"
                  disabled={submitting}
                  onClick={(event) => handleSensorInput(event, machine)}
                >
                  {submitting ? "제출 중..." : "센서 입력"}
                </button>
              </div>
              <div className="row-meta">
                <span>{machine.machineId}</span>
                <span className="sep">·</span>
                <span>
                  {loading
                    ? "확인 중..."
                    : error
                      ? "오류"
                      : alert
                        ? `${ALERT_STATUS_LABELS[alert.alert_status] || alert.alert_status} · 확인필요`
                        : "활성 경보 없음"}
                </span>
                {alert && alert.repeat_count > 0 && (
                  <>
                    <span className="sep">·</span>
                    <span>반복 {alert.repeat_count}회</span>
                  </>
                )}
                <span className="sep">·</span>
                <span>{formatTime(alert?.updated_at)}</span>
              </div>

              {result && (
                <div className="fill" style={{ marginTop: 10 }} onClick={(event) => event.stopPropagation()}>
                  {result.error ? (
                    <span className="status-block error">{result.error.message}</span>
                  ) : (
                    <>
                      판정 결과: <b>{RISK_LEVEL_LABELS[result.risk_level] || result.risk_level}</b> ·{" "}
                      {ALERT_STATUS_LABELS[result.alert_status] || result.alert_status}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p style={{ fontSize: 11, color: "var(--faint)", margin: "12px 2px 0" }}>
        1=정상 · 2=주의 · 3=경고 · 4=긴급(삼각형)
      </p>
    </>
  );
}
