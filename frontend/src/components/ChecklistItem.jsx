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

/** The no-LLM fallback sets an item's title to (a possibly truncated prefix
 * of) its own instruction text - showing both renders the same sentence
 * twice in a row. Only render the title when it actually adds something the
 * instruction doesn't already say. */
function isRedundantTitle(title, instruction) {
  if (!title || !instruction) return false;
  return instruction.trim().startsWith(title.replace(/…$/, "").trim());
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
 * "근거" always shows the compact SOP/법령 reference (e.g. "SOP: ... 5절 ·
 * 산안법: 제241조") - the item's own instruction already carries the SOP
 * wording, so there's nothing to expand there. When a law citation is
 * attached, the tag is a button: pressing it reveals that law's
 * plain-language summary, so the reference stays scannable by default and
 * the actual legal content is one click away, not shown twice at once.
 */
export default function ChecklistItem({ item, status, note, onStatusChange, onNoteChange, readOnly }) {
  const [lawExpanded, setLawExpanded] = useState(false);
  const citations = item.citations || [];
  const lawCitations = citations.filter((c) => c.document_type !== "sop");
  const noteMissing = !readOnly && status === "SKIPPED" && !(note || "").trim();

  return (
    <div className="item">
      <div className="row">
        <div style={{ flex: 1 }}>
          {!isRedundantTitle(item.title, item.instruction) && <p className="item-title">{item.title}</p>}
          <p className="instruction">
            <Truncated text={item.instruction} />
          </p>
          <div className="tag-row">
            {item.priority && <Badge level="chip">우선순위 {PRIORITY_LABELS[item.priority] || item.priority}</Badge>}
            {item.required && <Badge level="chip">필수</Badge>}
            {item.previously_failed && <Badge level="danger">이전 실패 이력</Badge>}
          </div>
          {citations.length > 0 &&
            (lawCitations.length > 0 ? (
              <button type="button" className="citation-pill" onClick={() => setLawExpanded((v) => !v)}>
                근거: {citationLabel(citations)} {lawExpanded ? "▲" : "▼"}
              </button>
            ) : (
              <span className="citation-pill">근거: {citationLabel(citations)}</span>
            ))}
          {lawExpanded &&
            lawCitations.map((citation, index) => (
              <p key={`${citation.source_id}-${index}`} className="law-summary">
                {citation.legal_reference || citation.source_id}: {citation.plain_summary || "요약이 없습니다."}
              </p>
            ))}
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
