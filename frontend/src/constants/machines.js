// Mirrors the fixed 4-machine demo set in data/machine_profiles.json and the
// machine_id <-> machine_type mapping enforced by app/models/sensor.py.
export const MACHINES = [
  { machineId: "M-0101", machineType: "REACTOR", displayName: "화학 반응기" },
  { machineId: "M-0102", machineType: "COMPRESSOR", displayName: "산업용 압축기" },
  { machineId: "M-0103", machineType: "STORAGE_TANK", displayName: "인화성 물질 저장탱크" },
  { machineId: "M-0104", machineType: "PUMP", displayName: "원심 펌프" },
];

export function machineById(machineId) {
  return MACHINES.find((machine) => machine.machineId === machineId) || null;
}

// Per machine-type demo readings mirroring the MOCK-* fixtures used for QA.
export const MACHINE_SENSOR_PRESETS = {
  REACTOR: {
    temperature: 30.0,
    pressure: 25.0,
    humidity: 40.0,
    vibration: 1.0,
    speed: 1500.0,
    age: 5,
    service_days: 90,
    gas: 1.0,
    sparks: 0,
    shift: "Day",
    experience: "Senior",
    training: "Yes",
  },
  COMPRESSOR: {
    temperature: 30.0,
    pressure: 35.0,
    humidity: 40.0,
    vibration: 4.0,
    speed: 3000.0,
    age: 5,
    service_days: 90,
    gas: 1.0,
    sparks: 0,
    shift: "Day",
    experience: "Senior",
    training: "Yes",
  },
  STORAGE_TANK: {
    temperature: 45.0,
    pressure: 44.0,
    humidity: 40.0,
    vibration: 1.0,
    speed: 1500.0,
    age: 5,
    service_days: 90,
    gas: 8.5,
    sparks: 2,
    shift: "Day",
    experience: "Senior",
    training: "Yes",
  },
  PUMP: {
    temperature: 30.0,
    pressure: 25.0,
    humidity: 40.0,
    vibration: 6.5,
    speed: 1500.0,
    age: 5,
    service_days: 90,
    gas: 1.0,
    sparks: 0,
    shift: "Day",
    experience: "Senior",
    training: "Yes",
  },
};

// A single baseline reading low enough to stay clear of every machine type's
// EMERGENCY rule (app/nodes/risk_policy.py::EMERGENCY_RULES) - unlike
// MACHINE_SENSOR_PRESETS above (which deliberately sits near a threshold for
// some machines, e.g. PUMP's default vibration already trips EMERGENCY),
// this one is specifically for the "즉시 재측정" auto-recheck experiment,
// where the point is to reliably demonstrate the recovery path.
export const SAFE_RECHECK_PRESET = {
  temperature: 25,
  pressure: 20,
  humidity: 40,
  vibration: 0.8,
  speed: 1200,
  age: 3,
  service_days: 90,
  gas: 1.0,
  sparks: 0,
  shift: "Day",
  experience: "Senior",
  training: "Yes",
};

// A shared "worse operating context" (older machine, more service days,
// night shift, junior worker, no safety training) layered on top of
// SAFE_RECHECK_PRESET to reach CAUTION/WARNING - the trained model is a weak
// Random Forest (roc_auc ~0.72) where nudging a single sensor field barely
// moves its score, so these were found empirically by sweeping combinations
// against the real model until each level landed with a comfortable margin
// from the caution(0.145)/warning(0.29) thresholds. EMERGENCY levels instead
// trip risk_policy.py's per-machine-type EMERGENCY_RULES directly (those
// override the ML score outright), so they only need the one triggering
// field changed from the safe baseline.
const RISKY_OPERATING_CONTEXT = {
  age: 15,
  service_days: 1800,
  shift: "Night",
  experience: "Junior",
  training: "No",
};

// Dashboard의 "센서 입력" 버튼을 누를 때마다 이 중 하나를 무작위로 골라 제출한다.
export const RISK_LEVELS = ["NORMAL", "CAUTION", "WARNING", "EMERGENCY"];

// machineType -> riskLevel -> SAFE_RECHECK_PRESET 위에 덮어씌울 필드.
// 값 조합은 실제 모델/risk_policy에 대해 확인됨 (2026-07-28).
export const RISK_LEVEL_PRESETS = {
  REACTOR: {
    NORMAL: {},
    CAUTION: RISKY_OPERATING_CONTEXT,
    WARNING: { ...RISKY_OPERATING_CONTEXT, temperature: 36, pressure: 30, gas: 3 },
    EMERGENCY: { temperature: 45 },
  },
  COMPRESSOR: {
    NORMAL: {},
    CAUTION: { ...RISKY_OPERATING_CONTEXT, vibration: 3.5, speed: 3000, pressure: 30 },
    WARNING: { ...RISKY_OPERATING_CONTEXT, vibration: 4.5, speed: 3500, pressure: 35 },
    EMERGENCY: { vibration: 5.0 },
  },
  STORAGE_TANK: {
    NORMAL: {},
    CAUTION: { ...RISKY_OPERATING_CONTEXT, gas: 6.0, sparks: 1, pressure: 32 },
    WARNING: { ...RISKY_OPERATING_CONTEXT, gas: 9.5, sparks: 2, pressure: 42 },
    EMERGENCY: { gas: 9.5, sparks: 3 },
  },
  PUMP: {
    NORMAL: {},
    CAUTION: RISKY_OPERATING_CONTEXT,
    WARNING: { ...RISKY_OPERATING_CONTEXT, vibration: 3.0 },
    EMERGENCY: { vibration: 6.0 },
  },
};

export const SHIFT_OPTIONS = ["Day", "Night"];
export const EXPERIENCE_OPTIONS = ["Junior", "Senior"];
export const TRAINING_OPTIONS = ["Yes", "No"];

export const RISK_LEVEL_LABELS = {
  NORMAL: "정상",
  CAUTION: "주의",
  WARNING: "경고",
  EMERGENCY: "긴급",
};

export const ALERT_STATUS_LABELS = {
  NONE: "없음",
  OPEN: "발생",
  IN_PROGRESS: "조치 중",
  WAITING_RECHECK: "재측정 대기",
  MONITORING: "관찰 중",
  RESOLVED: "해소",
  ESCALATED: "관리자 확인 필요",
};

// Display labels for any status a checklist item might already carry
// (historical data may still have PENDING/FAILED from before the team
// narrowed the worker-facing choice to just these two).
export const CHECKLIST_ITEM_STATUS_LABELS = {
  PENDING: "대기",
  COMPLETED: "완료",
  SKIPPED: "보류",
  FAILED: "실패",
};

// The only two statuses a worker can pick (team decision - see p.78 of the
// UI 협의과정 review: PENDING/FAILED removed from the frontend entirely).
// SKIPPED listed first because it's each item's default state.
export const EDITABLE_ITEM_STATUS_OPTIONS = [
  { value: "SKIPPED", label: "보류" },
  { value: "COMPLETED", label: "완료" },
];
