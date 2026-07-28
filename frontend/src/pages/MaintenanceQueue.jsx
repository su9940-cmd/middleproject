import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { LoadingBlock, ErrorBlock, EmptyBlock } from "../components/StatusBlock.jsx";
import { decideMaintenanceRequest, listPendingMaintenanceRequests } from "../api/maintenance.js";

export default function MaintenanceQueue() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [requests, setRequests] = useState([]);
  const [busyId, setBusyId] = useState(null);
  const [actionError, setActionError] = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const pending = await listPendingMaintenanceRequests();
      setRequests(pending);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDecision(request, decision) {
    setBusyId(request.maintenanceRequestId);
    setActionError(null);
    try {
      await decideMaintenanceRequest(request.maintenanceRequestId, { decision, decidedBy: "안전관리자" });
      setRequests((prev) => prev.filter((item) => item.maintenanceRequestId !== request.maintenanceRequestId));
    } catch (err) {
      setActionError(err);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>정비 승인 대기</h1>
        <p>아직 결정되지 않은 모든 설비의 정비 요청 초안입니다.</p>
      </div>

      {loading && <LoadingBlock />}
      {!loading && error && <ErrorBlock error={error} />}
      {!loading && !error && requests.length === 0 && <EmptyBlock label="승인 대기 중인 정비 요청이 없습니다." />}

      {!loading && !error && requests.length > 0 && (
        <div className="alert-list">
          {actionError && <p className="status-block error">{actionError.message}</p>}
          {requests.map((request) => (
            <div key={request.maintenanceRequestId} className="alert-list-item">
              <div className="row-top">
                <Link
                  to={`/machines/${request.machineId}/manager`}
                  className="machine-name"
                  style={{ textDecoration: "none" }}
                >
                  {request.machineId} · {request.machineType}
                </Link>
              </div>
              <p style={{ margin: "8px 0 0", fontWeight: 600, fontSize: 13 }}>{request.title}</p>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--muted)" }}>{request.recommendation}</p>
              <div className="row-meta" style={{ marginTop: 6 }}>
                <span>우선순위 {request.priority}</span>
              </div>
              <div className="button-row" style={{ marginTop: 10, marginBottom: 0 }}>
                <button
                  type="button"
                  className="ghost"
                  disabled={busyId === request.maintenanceRequestId}
                  onClick={() => handleDecision(request, "APPROVED")}
                >
                  승인
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busyId === request.maintenanceRequestId}
                  onClick={() => handleDecision(request, "REJECTED")}
                >
                  반려
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
