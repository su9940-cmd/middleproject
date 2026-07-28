import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Badge from "../components/Badge.jsx";
import ChecklistItem from "../components/ChecklistItem.jsx";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "../components/StatusBlock.jsx";
import { getActiveAlert, getAlertChecklist } from "../api/alerts.js";
import { ingestSensorReading } from "../api/sensors.js";
import { submitChecklistResponse } from "../api/worker.js";
import { machineById, RISK_LEVEL_LABELS, ALERT_STATUS_LABELS, SAFE_RECHECK_PRESET } from "../constants/machines.js";

const POLL_INTERVAL_MS = 1500;

function buildRecheckReadingId(machineId) {
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0];
  return `RD-${machineId.replace(/-/g, "")}-RECHECK-${timestamp}`;
}

function defaultItemState(items) {
  const state = {};
  for (const item of items) {
    // A worker must make a deliberate choice per item; nothing defaults to
    // "완료" on its own. An item that was already answered (e.g. reloading
    // this page after submitting) keeps its stored status instead.
    const stored = item.status && item.status !== "PENDING" && item.status !== "FAILED" ? item.status : "SKIPPED";
    state[item.checklist_item_id] = { status: stored, note: item.worker_note || "" };
  }
  return state;
}

export default function WorkerScreen() {
  const { machineId } = useParams();
  const machine = machineById(machineId);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [alert, setAlert] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [itemState, setItemState] = useState({});
  const [acknowledged, setAcknowledged] = useState(false);

  // "checklist" | "waiting_recheck" | "resolved"
  const [screenPhase, setScreenPhase] = useState("checklist");
  const [allCompletedAtSubmit, setAllCompletedAtSubmit] = useState(false);
  const [finalAlert, setFinalAlert] = useState(null);

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  // Experimental: auto-fill and auto-submit a safe reading instead of making
  // someone hand-type recheck values every time - see SAFE_RECHECK_PRESET.
  const [recheckAutoSubmitted, setRecheckAutoSubmitted] = useState(false);
  const [recheckError, setRecheckError] = useState(null);
  const [recheckAttempt, setRecheckAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const activeAlert = await getActiveAlert(machineId);
        if (cancelled) return;
        setAlert(activeAlert);
        if (!activeAlert) return;

        const latest = await getAlertChecklist(activeAlert.alert_id);
        if (cancelled) return;
        setChecklist(latest);
        if (!latest) return;

        if (latest.completed_at) {
          const wasAllCompleted = (latest.items || []).every((item) => item.status === "COMPLETED");
          setAllCompletedAtSubmit(wasAllCompleted);
          if (activeAlert.alert_status === "WAITING_RECHECK") {
            setScreenPhase("waiting_recheck");
          } else {
            setFinalAlert(activeAlert);
            setScreenPhase("resolved");
          }
        } else {
          setItemState(defaultItemState(latest.items || []));
        }
      } catch (error) {
        if (!cancelled) setLoadError(error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [machineId]);

  // A new incident (different alert_id) always needs a fresh acknowledgement,
  // even if this component instance stays mounted (route params changed but
  // the machine's alert was re-opened, etc.).
  useEffect(() => {
    setAcknowledged(false);
  }, [alert?.alert_id]);

  // The graph runs the whole EMERGENCY→checklist pipeline inside one request,
  // but notification (Slack) and checklist generation happen in parallel -
  // a worker who opens this screen straight from the Slack alert can arrive
  // before that same request has finished saving the checklist. Poll for it.
  useEffect(() => {
    if (!alert || checklist || screenPhase !== "checklist") return;
    const interval = setInterval(async () => {
      try {
        const latest = await getAlertChecklist(alert.alert_id);
        if (latest) {
          setChecklist(latest);
          setItemState(defaultItemState(latest.items || []));
          clearInterval(interval);
        }
      } catch {
        // keep polling - a transient failure here isn't this screen's to report
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [alert, checklist, screenPhase]);

  // Experimental: instead of requiring someone to fill in the recheck form
  // by hand, auto-submit a safe reading the moment this phase starts - the
  // poll effect below picks up the result the same way either way.
  useEffect(() => {
    if (!machine || screenPhase !== "waiting_recheck" || recheckAutoSubmitted) return;
    let cancelled = false;
    setRecheckError(null);
    (async () => {
      try {
        await ingestSensorReading({
          reading_id: buildRecheckReadingId(machine.machineId),
          machine_id: machine.machineId,
          machine_type: machine.machineType,
          measured_at: new Date().toISOString(),
          measurement_mode: "IMMEDIATE_RECHECK",
          ...SAFE_RECHECK_PRESET,
        });
        if (!cancelled) setRecheckAutoSubmitted(true);
      } catch (error) {
        if (!cancelled) setRecheckError(error);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [screenPhase, recheckAutoSubmitted, recheckAttempt, machine]);

  // After submit, poll until the recheck reading resolves the alert one way
  // or the other (there's no real IoT push - the auto-submit above is what
  // actually stands in for it).
  useEffect(() => {
    if (screenPhase !== "waiting_recheck") return;
    const interval = setInterval(async () => {
      try {
        const latestAlert = await getActiveAlert(machineId);
        const status = latestAlert ? latestAlert.alert_status : null;
        if (status !== "WAITING_RECHECK") {
          setFinalAlert(latestAlert);
          setScreenPhase("resolved");
          clearInterval(interval);
        }
      } catch {
        // keep polling
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [screenPhase, machineId]);

  function getItemState(itemId) {
    return itemState[itemId] ?? { status: "SKIPPED", note: "" };
  }

  function updateStatus(itemId, value) {
    setItemState((prev) => ({ ...prev, [itemId]: { ...getItemState(itemId), status: value } }));
  }

  function updateNote(itemId, value) {
    setItemState((prev) => ({ ...prev, [itemId]: { ...getItemState(itemId), note: value } }));
  }

  if (!machine) {
    return <ErrorBlock label={`알 수 없는 설비 ID입니다: ${machineId}`} />;
  }

  if (loading) return <LoadingBlock />;
  if (loadError) return <ErrorBlock error={loadError} />;
  if (!alert) return <EmptyBlock label="이 설비에는 활성 경보가 없습니다." />;

  const items = checklist?.items || [];

  // 보류 항목은 사유(note)가 없으면 제출할 수 없다.
  const allDecided =
    items.length > 0 &&
    items.every((item) => {
      const s = getItemState(item.checklist_item_id);
      if (s.status === "SKIPPED") return s.note.trim().length > 0;
      return true;
    });

  async function handleSubmit() {
    setSubmitting(true);
    setSubmitError(null);
    const wasAllCompleted = items.every((item) => getItemState(item.checklist_item_id).status === "COMPLETED");
    setAllCompletedAtSubmit(wasAllCompleted);

    const payloadItems = items.map((item) => {
      const s = getItemState(item.checklist_item_id);
      return { checklistItemId: item.checklist_item_id, status: s.status, note: s.note };
    });

    try {
      await submitChecklistResponse(checklist.checklist_id, { alertId: alert.alert_id, items: payloadItems });
      setScreenPhase("waiting_recheck");
    } catch (error) {
      setSubmitError(error);
    } finally {
      setSubmitting(false);
    }
  }

  // EMERGENCY pre-notification, gated behind an explicit acknowledgement
  // (five_screen_flow_v9.html's popup step ②) before the checklist itself is
  // shown - it fires the moment risk_level is known, independent of whether
  // the checklist has finished generating yet.
  const emergencyGate =
    alert.risk_level === "EMERGENCY" && !acknowledged && screenPhase === "checklist" ? (
      <div className="modal-backdrop">
        <div className="modal-card">
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <Badge level="EMERGENCY" />
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14.5 }}>
              {alert.machine_id} {alert.machine_type} 긴급 상황!
            </p>
          </div>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--muted)" }}>
            {(alert.emergency_reasons || []).map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <p style={{ color: "var(--faint)", fontSize: 12, margin: "10px 0 10px" }}>
            {checklist ? "체크리스트가 준비됐습니다." : "체크리스트를 생성하는 중입니다."}
          </p>
          <button type="button" className="primary" style={{ width: "100%" }} onClick={() => setAcknowledged(true)}>
            확인
          </button>
        </div>
      </div>
    ) : null;

  if (screenPhase === "waiting_recheck") {
    return (
      <>
        <div className="page-header">
          <h1>즉시 재측정 대기 중 · {machine.displayName}</h1>
          <p>작업자 응답이 저장되고 설비가 재측정 대기 상태로 전환됐습니다.</p>
        </div>
        <div className="card" style={{ textAlign: "center" }}>
          {recheckError ? (
            <>
              <p className="status-block error">재측정 자동 제출에 실패했습니다: {recheckError.message}</p>
              <button
                type="button"
                className="primary"
                onClick={() => {
                  setRecheckError(null);
                  setRecheckAttempt((n) => n + 1);
                }}
              >
                다시 시도
              </button>
            </>
          ) : recheckAutoSubmitted ? (
            <p className="status-block">
              정상 값으로 재측정을 제출했습니다. 판정 결과를 기다리는 중입니다...
            </p>
          ) : (
            <p className="status-block">
              (시범 기능) 실제 IoT 센서가 없는 데모 환경이라, 정상 값을 자동으로 채워 재측정을
              제출하는 중입니다...
            </p>
          )}
        </div>
      </>
    );
  }

  if (screenPhase === "resolved") {
    const displayLevel = allCompletedAtSubmit
      ? !finalAlert || finalAlert.alert_status === "MONITORING"
        ? "NORMAL"
        : alert.risk_level
      : alert.risk_level;
    const isResolved = displayLevel === "NORMAL";

    return (
      <>
        <div className="page-header">
          <h1>재판정 결과 · {machine.displayName}</h1>
        </div>
        <div className="card" style={{ textAlign: "center" }}>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <Badge level={displayLevel} />
          </div>
          <p style={{ fontSize: 12.5, color: "var(--muted)", margin: "8px 0 0" }}>
            {RISK_LEVEL_LABELS[displayLevel] || displayLevel}
          </p>
          {!allCompletedAtSubmit ? (
            <p className="status-block">보류 항목이 남아있어 위험단계가 유지됩니다.</p>
          ) : (
            <>
              <p className="status-block">
                재판정 결과: <b>{finalAlert ? ALERT_STATUS_LABELS[finalAlert.alert_status] || finalAlert.alert_status : "해소"}</b>
              </p>
              {!isResolved && (
                <p className="status-block">완료 처리했지만 재측정에서 이상이 지속돼 위험단계가 유지됩니다.</p>
              )}
            </>
          )}
          <Link to="/">
            <button type="button" className="primary" style={{ marginTop: 10 }}>
              대시보드로 돌아가기
            </button>
          </Link>
        </div>
      </>
    );
  }

  if (!checklist) {
    return (
      <>
        {emergencyGate}
        <div className="page-header">
          <h1>{machine.displayName}</h1>
        </div>
        <div className="card">
          {alert.risk_level === "EMERGENCY" && (
            <div className="notice">
              [EMERGENCY] {alert.machine_id} ({alert.machine_type}) — 근거:{" "}
              {(alert.emergency_reasons || []).join(" · ") || "상세 근거 확인 중"}
            </div>
          )}
          <p className="status-block">체크리스트를 생성하는 중입니다...</p>
        </div>
      </>
    );
  }

  return (
    <>
      {emergencyGate}
      <div className="page-header">
        <h1>체크리스트 · {machine.displayName}</h1>
      </div>

      <div className="card">
        {alert.risk_level === "EMERGENCY" && (
          <div className="notice">
            [EMERGENCY] {alert.machine_id} ({alert.machine_type}) — 근거:{" "}
            {(alert.emergency_reasons || []).join(" · ") || "상세 근거 확인 중"}
          </div>
        )}

        <div className="card-head">
          <div>
            <p className="title">
              {machine.machineId} · {machine.machineType}
            </p>
            <p className="sub">체크리스트 v{checklist.version}</p>
          </div>
          <Badge level={alert.risk_level} />
        </div>

        <div className="meta-row">
          <span>
            경보 ID <b>{alert.alert_id}</b>
          </span>
          <span>
            구분 <b>{checklist.action_phase}</b>
          </span>
        </div>

        {(checklist.requires_manager_report || checklist.requires_maintenance_request) && (
          <div className="button-row">
            {checklist.requires_manager_report && <Badge level="chip">관리자 보고 필요</Badge>}
            {checklist.requires_maintenance_request && <Badge level="chip">정비 요청 초안 필요</Badge>}
          </div>
        )}

        <p className="section-title">체크리스트 항목</p>
        <div className="items">
          {items.map((item) => {
            const s = getItemState(item.checklist_item_id);
            return (
              <ChecklistItem
                key={item.checklist_item_id}
                item={item}
                status={s.status}
                note={s.note}
                onStatusChange={updateStatus}
                onNoteChange={updateNote}
              />
            );
          })}
        </div>

        {submitError && <p className="status-block error">{submitError.message}</p>}
        <button type="button" className="primary" disabled={!allDecided || submitting} onClick={handleSubmit}>
          {submitting ? "제출 중..." : "제출"}
        </button>
      </div>
    </>
  );
}
