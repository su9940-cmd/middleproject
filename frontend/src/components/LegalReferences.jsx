import { Truncated } from "./ChecklistItem.jsx";

/**
 * Law/KOSHA articles the RAG step retrieved alongside the SOP but that never
 * became their own checklist item (see draft_composer.py's
 * `_collect_supporting_references`) - shown here per-article so a worker can
 * still see which regulation backs the checklist, not just the SOP excerpt.
 */
export default function LegalReferences({ references }) {
  if (!references || references.length === 0) return null;

  return (
    <div className="legal-references">
      <p className="section-title">관련 법령</p>
      <div className="items">
        {references.map((reference) => (
          <div className="item" key={reference.source_key || reference.source_id}>
            <p className="item-title">{reference.legal_reference || reference.title || reference.source_id}</p>
            <p className="instruction">
              <Truncated text={reference.source_excerpt || reference.content} />
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
