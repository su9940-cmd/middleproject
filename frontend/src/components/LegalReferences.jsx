import { useState } from "react";
import { Truncated } from "./ChecklistItem.jsx";

/**
 * Law/KOSHA articles the RAG step retrieved alongside the SOP but that never
 * became their own checklist item (see draft_composer.py's
 * `_collect_supporting_references`) - shown here per-article so a worker can
 * still see which regulation backs the checklist, not just the SOP excerpt.
 *
 * Leads with `plain_summary` (data/laws/*.md front-matter - a one-sentence
 * paraphrase) so a worker isn't stuck parsing actual statute wording; the
 * real article text is still there, just behind a "원문 보기" toggle for
 * anyone who wants the literal wording.
 */
export default function LegalReferences({ references, compact = false }) {
  const [expanded, setExpanded] = useState(false);
  if (!references || references.length === 0) return null;

  if (compact) {
    return (
      <div className="legal-references">
        <p className="section-title">근거</p>
        <button type="button" className="expand-toggle" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "법령·원문 접기" : "법령·원문 전체 보기"}
        </button>
        <div className="tag-row">
          {references.map((reference) => (
            <span className="citation-pill" key={reference.source_key || reference.source_id}>
              {reference.document_type === "sop" ? "SOP" : "법령"}: {reference.legal_reference || reference.title || reference.source_id}
              {reference.section ? ` · ${reference.section}` : ""}
            </span>
          ))}
        </div>
        {expanded && (
          <div className="items" style={{ marginTop: 8 }}>
            {references.map((reference) => (
              <LegalReferenceItem key={`detail-${reference.source_key || reference.source_id}`} reference={reference} />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="legal-references">
      <p className="section-title">관련 법령</p>
      <div className="items">
        {references.map((reference) => (
          <LegalReferenceItem key={reference.source_key || reference.source_id} reference={reference} />
        ))}
      </div>
    </div>
  );
}

function LegalReferenceItem({ reference }) {
  const [expanded, setExpanded] = useState(false);
  const rawText = reference.source_excerpt || reference.content;

  return (
    <div className="item">
      <p className="item-title">{reference.legal_reference || reference.title || reference.source_id}</p>
      {reference.plain_summary ? (
        <>
          <p className="instruction">{reference.plain_summary}</p>
          {rawText && (
            <button type="button" className="expand-toggle" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "원문 접기" : "법령 원문 보기"}
            </button>
          )}
          {expanded && (
            <p className="instruction" style={{ marginTop: 6 }}>
              <Truncated text={rawText} />
            </p>
          )}
        </>
      ) : (
        <p className="instruction">
          <Truncated text={rawText} />
        </p>
      )}
    </div>
  );
}
