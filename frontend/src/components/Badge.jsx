import { RISK_LEVEL_LABELS } from "../constants/machines.js";

// Step number + color per five_screen_flow_v9.html's riskBadge(): a plain
// numbered circle for 1-3, a warning triangle for EMERGENCY (step 4).
const RISK_STEPS = {
  NORMAL: 1,
  CAUTION: 2,
  WARNING: 3,
  EMERGENCY: 4,
};

const TEXT_LEVELS = new Set(["success", "danger", "chip"]);

export default function Badge({ level, children }) {
  const step = RISK_STEPS[level];
  if (step) {
    const label = RISK_LEVEL_LABELS[level] || level;
    if (level === "EMERGENCY") {
      return (
        <span className="risk-badge-triangle" title={label} aria-label={label}>
          <span className="risk-badge-triangle-shape" />
          <span className="risk-badge-triangle-label">{step}</span>
        </span>
      );
    }
    return (
      <span className={`risk-badge risk-badge-${level}`} title={label} aria-label={label}>
        {step}
      </span>
    );
  }

  const className = TEXT_LEVELS.has(level) ? level : "chip";
  return <span className={`badge ${className}`}>{children ?? level}</span>;
}
