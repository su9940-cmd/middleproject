import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import Badge from "../components/Badge.jsx";
import ChecklistItem from "../components/ChecklistItem.jsx";
import LegalReferences from "../components/LegalReferences.jsx";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "../components/StatusBlock.jsx";
import { getActiveAlert, getAlertChecklist } from "../api/alerts.js";
import { decideMaintenanceRequest, listPendingMaintenanceRequests } from "../api/maintenance.js";
import { machineById } from "../constants/machines.js";

export default function ManagerScreen() {
  const { machineId } = useParams();
  const machine = machineById(machineId);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [alert, setAlert] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [maintenanceRequest, setMaintenanceRequest] = useState(null);

  const [comment, setComment] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [decideError, setDecideError] = useState(null);

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const activeAlert = await getActiveAlert(machineId);
      setAlert(activeAlert);
      if (!activeAlert) {
        setChecklist(null);
        setMaintenanceRequest(null);
        return;
      }
      const [latestChecklist, pending] = await Promise.all([
        getAlertChecklist(activeAlert.alert_id),
        listPendingMaintenanceRequests(),
      ]);
      setChecklist(latestChecklist);
      const matching = pending.find((request) => (request.alertId || request.alert_id) === activeAlert.alert_id);
      setMaintenanceRequest(matching || null);
    } catch (error) {
      setLoadError(error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machineId]);

  async function handleDecision(decision) {
    setDeciding(true);
    setDecideError(null);
    try {
      const updated = await decideMaintenanceRequest(maintenanceRequest.maintenanceRequestId, {
        decision,
        decidedBy: "안전관리자",
        comment,
      });
      setMaintenanceRequest(updated);
    } catch (error) {
      setDecideError(error);
    } finally {
      setDeciding(false);
    }
  }

  if (!machine) {
    return <ErrorBlock label={`알 수 없는 설비 ID입니다: ${machineId}`} />;
  }

  return (
    <>
      <div className="page-header">
        <h1>관리자 검토 · {machine.displayName}</h1>
        <p>
          작업자가 제출한 체크리스트를 검토하고, AI가 초안으로 만든 정비 요청(FR-14)이 있다면 승인
          여부를 결정합니다. 결정은 <code>POST /maintenance-requests/{`{id}`}/decision</code>으로
          전송됩니다.
        </p>
      </div>

      {loading && <LoadingBlock />}
      {!loading && loadError && <ErrorBlock error={loadError} />}
      {!loading && !loadError && !alert && <EmptyBlock label="이 설비에는 활성 경보가 없습니다." />}
      {!loading && !loadError && alert && !checklist && (
        <EmptyBlock label="경보는 있지만 아직 생성된 체크리스트가 없습니다." />
      )}

      {!loading && !loadError && alert && checklist && (
        <div className="card">
          <div className="card-head">
            <div>
              <p className="title">
                {machine.machineId} · {machine.machineType}
              </p>
              <p className="sub">{alert.alert_id}</p>
            </div>
            <Badge level={alert.risk_level} />
          </div>

          <LegalReferences
            compact
            references={Array.from(
              new Map(
                [
                  ...(checklist.supporting_references || []),
                  ...(checklist.items || []).flatMap((item) => item.citations || []),
                ].map((reference) => [reference.source_key || reference.source_id, reference]),
              ).values(),
            )}
          />

          {checklist.worker_note && (
            <>
              <p className="section-title">작업자 메모 (전체)</p>
              <div className="fill">{checklist.worker_note}</div>
            </>
          )}

          <p className="section-title">체크리스트</p>
          <div className="items">
            {(checklist.items || []).map((item) => (
              <ChecklistItem
                key={item.checklist_item_id}
                item={item}
                status={item.status}
                note={item.worker_note}
                readOnly
                showCitations={false}
              />
            ))}
          </div>

          {maintenanceRequest && (
            <div className="mtreq-box" style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--rule)" }}>
              <p className="section-title" style={{ marginTop: 0 }}>
                정비 요청 초안{" "}
                <span style={{ fontSize: 12, color: "var(--faint)", fontWeight: 400 }}>
                  (관리자 승인 필요 · FR-14)
                </span>
              </p>
              <div className="fill">
                <p style={{ margin: 0, fontWeight: 600 }}>{maintenanceRequest.title}</p>
                <p style={{ margin: "4px 0 0", color: "var(--muted)" }}>{maintenanceRequest.recommendation}</p>
                <p style={{ margin: "6px 0 0", color: "var(--faint)", fontSize: 12 }}>
                  우선순위: {maintenanceRequest.priority}
                </p>
              </div>

              {maintenanceRequest.status === "PENDING" ? (
                <>
                  <label className="field-label" htmlFor="manager-comment" style={{ marginTop: 12 }}>
                    관리자 코멘트
                  </label>
                  <textarea
                    id="manager-comment"
                    rows={2}
                    placeholder="검토 의견을 입력하세요"
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                  />
                  {decideError && <p className="status-block error">{decideError.message}</p>}
                  <div className="button-row" style={{ marginTop: 10 }}>
                    <button type="button" className="primary" disabled={deciding} onClick={() => handleDecision("APPROVED")}>
                      승인
                    </button>
                    <button type="button" className="ghost" disabled={deciding} onClick={() => handleDecision("REJECTED")}>
                      반려
                    </button>
                    <button type="button" className="ghost" disabled={deciding} onClick={() => handleDecision("DEFERRED")}>
                      보류
                    </button>
                  </div>
                </>
              ) : (
                <p style={{ fontSize: 12, color: "var(--faint)", margin: "10px 0 0" }}>
                  이미 {maintenanceRequest.status === "APPROVED" ? "승인" : maintenanceRequest.status === "REJECTED" ? "반려" : "보류"}
                  됨{maintenanceRequest.decidedBy ? ` · ${maintenanceRequest.decidedBy}` : ""}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
