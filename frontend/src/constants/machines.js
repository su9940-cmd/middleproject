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
