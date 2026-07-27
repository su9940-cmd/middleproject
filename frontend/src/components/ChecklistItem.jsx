import { useState } from "react";
import Badge from "./Badge.jsx";
import { CHECKLIST_ITEM_STATUS_LABELS, EDITABLE_ITEM_STATUS_OPTIONS } from "../constants/machines.js";

const PRIORITY_LABELS = { HIGH: "높음", MEDIUM: "중간", LOW: "낮음" };
const TRUNCATE_AT = 220;

/**
 * Long text with a "더 보기"/"접기" toggle. `action_draft_node`'s no-LLM
 * fallback (`_FallbackLLMClient` - no API key configured in this demo)
 * dumps a whole SOP markdown file as one item's instruction text, so this
 * is a real, common case, not an edge case.
 */
export function Truncated({ text }) {
  const [expanded, setExpanded] = useState(false);
  if (!text) return null;
  if (text.length <= TRUNCATE_AT) return <span>{text}</span>;
  return (
    <span>
      {expanded ? text : `${text.slice(0, TRUNCATE_AT)}…`}
      <button type="button" className="expand-toggle" onClick={() => setExpanded((v) => !v)}>
        {expanded ? "접기" : "더 보기"}
      </button>
    </span>
  );
}

/** "SOP: reactor_safety_manual 5절 · 산안법: 산업안전보건기준에 관한 규칙 제241조" -
 * a compact reference labelled by source type, not the source text itself
 * (the item's own instruction already carries that). */
function citationLabel(citations) {
  const sop = citations
    .filter((c) => c.document_type === "sop")
    .map((c) => (c.section ? `${c.source_id} ${c.section}` : c.source_id));
  const law = citations
    .filter((c) => c.document_type !== "sop")
    .map((c) => c.legal_reference || c.source_id);

  const parts = [];
  if (sop.length > 0) parts.push(`SOP: ${sop.join(", ")}`);
  if (law.length > 0) parts.push(`산안법: ${law.join(", ")}`);
  return parts.join(" · ");
}

/**
 * One checklist item.
 *
 * Editable mode (worker screen): status is binary (보류/완료 only - PENDING/FAILED
 * are never worker-selectable). A note is always editable and becomes
 * mandatory the moment status is SKIPPED (red border, blocks submit
 * upstream).
 *
 * "근거" is a static, always-visible reference tag - not a click-to-expand
 * detail panel. Earlier drafts hid it behind a toggle and re-quoted the
 * source excerpt inside it, which duplicated the item's own instruction
 * text; risk_logic_flow.mp4 (the team's reference recording) always shows
 * just the compact citation instead, no extra click needed.
 */
export default function ChecklistItem({ item, status, note, onStatusChange, onNoteChange, readOnly }) {
  const citations = item.citations || [];
  const noteMissing = !readOnly && status === "SKIPPED" && !(note || "").trim();

  return (
    <div className="item">
      <div className="row">
        <div style={{ flex: 1 }}>
          <p className="item-title">{item.title}</p>
          <p className="instruction">
            <Truncated text={item.instruction} />
          </p>
          <div className="tag-row">
            {item.priority && <Badge level="chip">우선순위 {PRIORITY_LABELS[item.priority] || item.priority}</Badge>}
            {item.required && <Badge level="chip">필수</Badge>}
            {item.previously_failed && <Badge level="danger">이전 실패 이력</Badge>}
          </div>
          {citations.length > 0 && <span className="citation-pill">근거: {citationLabel(citations)}</span>}
        </div>
        {readOnly ? (
          status && (
            <Badge level={status === "COMPLETED" ? "success" : status === "FAILED" ? "danger" : "chip"}>
              {CHECKLIST_ITEM_STATUS_LABELS[status] || status}
            </Badge>
          )
        ) : (
          <select
            className="status-select"
            value={status}
            onChange={(event) => onStatusChange(item.checklist_item_id, event.target.value)}
          >
            {EDITABLE_ITEM_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )}
      </div>

      {readOnly ? (
        note && <p className="fill note-field">{note}</p>
      ) : (
        <textarea
          className={`note-field${noteMissing ? " invalid" : ""}`}
          rows={1}
          value={note || ""}
          onChange={(event) => onNoteChange(item.checklist_item_id, event.target.value)}
          placeholder={status === "SKIPPED" ? "보류 사유를 반드시 입력하세요 (필수)" : "이 항목에 대한 메모 (선택)"}
        />
      )}
    </div>
  );
}
