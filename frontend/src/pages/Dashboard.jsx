import { Fragment, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Badge from "../components/Badge.jsx";
import SensorForm from "../components/SensorForm.jsx";
import { MACHINES, ALERT_STATUS_LABELS, RISK_LEVEL_LABELS } from "../constants/machines.js";
import { getActiveAlert } from "../api/alerts.js";

function initialState() {
  return Object.fromEntries(
    MACHINES.map((machine) => [machine.machineId, { alert: null, loading: true, error: null }]),
  );
}

function formatTime(iso) {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [statuses, setStatuses] = useState(initialState);
  const [openSensorForm, setOpenSensorForm] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  const refreshMachine = useCallback(async (machineId) => {
    setStatuses((prev) => ({ ...prev, [machineId]: { ...prev[machineId], loading: true, error: null } }));
    try {
      const alert = await getActiveAlert(machineId);
      setStatuses((prev) => ({ ...prev, [machineId]: { alert, loading: false, error: null } }));
    } catch (error) {
      setStatuses((prev) => ({ ...prev, [machineId]: { alert: null, loading: false, error } }));
    }
  }, []);

  useEffect(() => {
    MACHINES.forEach((machine) => refreshMachine(machine.machineId));
  }, [refreshMachine]);

  function handleRowClick(machine, alert) {
    if (!alert) return;
    navigate(`/machines/${machine.machineId}/worker`);
  }

  function toggleSensorForm(event, machineId) {
    event.stopPropagation();
    setLastResult(null);
    setOpenSensorForm((prev) => (prev === machineId ? null : machineId));
  }

  function handleSubmitted(machineId, result) {
    setLastResult({ machineId, ...result });
    refreshMachine(machineId);
  }

  return (
    <>
      <div className="page-header">
        <h1>설비 대시보드</h1>
        <p>
          활성 경보가 있는 설비 행을 클릭하면 체크리스트 화면으로 이동합니다. 실제 IoT 장비가 없는
          데모라 센서 값은 각 행의 "센서 입력"으로 직접 <code>POST /sensors/ingest</code>를 호출합니다.
        </p>
      </div>
      <div className="card">
        <table className="plain">
          <thead>
            <tr>
              <th>설비</th>
              <th>위험단계</th>
              <th>경보상태</th>
              <th>반복</th>
              <th>갱신</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {MACHINES.map((machine) => {
              const { alert, loading, error } = statuses[machine.machineId] || {
                alert: null,
                loading: true,
                error: null,
              };
              const clickable = Boolean(alert);
              const formOpen = openSensorForm === machine.machineId;

              return (
                <Fragment key={machine.machineId}>
                  <tr
                    className="row"
                    style={{ cursor: clickable ? "pointer" : "default" }}
                    onClick={() => handleRowClick(machine, alert)}
                  >
                    <td>
                      {machine.machineId} · {machine.machineType}
                    </td>
                    <td>{!loading && !error && <Badge level={alert?.risk_level || "NORMAL"} />}</td>
                    <td style={{ fontSize: 12.5, color: "var(--muted)" }}>
                      {loading
                        ? "확인 중..."
                        : error
                          ? "오류"
                          : alert
                            ? `${ALERT_STATUS_LABELS[alert.alert_status] || alert.alert_status} · 확인필요`
                            : "없음"}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--faint)" }}>
                      {alert && alert.repeat_count > 0 ? `반복 ${alert.repeat_count}회` : "-"}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--faint)" }}>{formatTime(alert?.updated_at)}</td>
                    <td>
                      <button type="button" className="ghost" onClick={(event) => toggleSensorForm(event, machine.machineId)}>
                        센서 입력
                      </button>
                    </td>
                  </tr>
                  {formOpen && (
                    <tr>
                      <td colSpan={6} style={{ padding: "12px 8px" }} onClick={(event) => event.stopPropagation()}>
                        <SensorForm
                          machine={machine}
                          measurementMode={alert?.alert_status === "WAITING_RECHECK" ? "IMMEDIATE_RECHECK" : "PERIODIC"}
                          onSubmitted={(result) => handleSubmitted(machine.machineId, result)}
                        />
                        {lastResult && lastResult.machineId === machine.machineId && (
                          <div className="fill" style={{ marginTop: 10 }}>
                            판정 결과: <b>{RISK_LEVEL_LABELS[lastResult.risk_level] || lastResult.risk_level}</b> ·{" "}
                            {ALERT_STATUS_LABELS[lastResult.alert_status] || lastResult.alert_status}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        <p style={{ fontSize: 11.5, color: "var(--faint)", margin: "10px 0 0" }}>
          1=정상 · 2=주의 · 3=경고 · 4=긴급(삼각형)
        </p>
      </div>
    </>
  );
}
