export function LoadingBlock({ label = "불러오는 중..." }) {
  return <p className="status-block">{label}</p>;
}

export function ErrorBlock({ error, label }) {
  const message = label || error?.message || "요청을 처리하지 못했습니다.";
  return <p className="status-block error">{message}</p>;
}

export function EmptyBlock({ label }) {
  return <p className="status-block">{label}</p>;
}
