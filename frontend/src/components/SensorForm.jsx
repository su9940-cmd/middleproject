import { useState } from "react";
import {
  NORMAL_SENSOR_PRESET,
  EMERGENCY_SENSOR_PRESETS,
  SHIFT_OPTIONS,
  EXPERIENCE_OPTIONS,
  TRAINING_OPTIONS,
} from "../constants/machines.js";
import { ingestSensorReading } from "../api/sensors.js";

const NUMBER_FIELDS = [
  { key: "temperature", label: "온도" },
  { key: "pressure", label: "압력" },
  { key: "humidity", label: "습도" },
  { key: "vibration", label: "진동" },
  { key: "speed", label: "속도" },
  { key: "age", label: "설비 나이", integer: true },
  { key: "service_days", label: "가동 경과일", integer: true },
  { key: "gas", label: "가스" },
  { key: "sparks", label: "스파크", integer: true },
];

function buildReadingId(machineId) {
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").split(".")[0];
  return `RD-${machineId.replace(/-/g, "")}-${timestamp}`;
}

export default function SensorForm({ machine, measurementMode = "PERIODIC", onSubmitted }) {
  const [values, setValues] = useState(NORMAL_SENSOR_PRESET);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  function updateField(key, rawValue) {
    setValues((prev) => ({ ...prev, [key]: rawValue }));
  }

  function applyPreset(preset) {
    setValues(preset);
    setError(null);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        reading_id: buildReadingId(machine.machineId),
        machine_id: machine.machineId,
        machine_type: machine.machineType,
        measured_at: new Date().toISOString(),
        measurement_mode: measurementMode,
        temperature: Number(values.temperature),
        pressure: Number(values.pressure),
        humidity: Number(values.humidity),
        vibration: Number(values.vibration),
        speed: Number(values.speed),
        age: parseInt(values.age, 10),
        service_days: parseInt(values.service_days, 10),
        gas: Number(values.gas),
        sparks: parseInt(values.sparks, 10),
        shift: values.shift,
        experience: values.experience,
        training: values.training,
      };
      const result = await ingestSensorReading(payload);
      onSubmitted?.(result);
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="button-row">
        <button type="button" className="ghost" onClick={() => applyPreset(NORMAL_SENSOR_PRESET)}>
          정상 값 채우기
        </button>
        <button
          type="button"
          className="ghost"
          onClick={() => applyPreset(EMERGENCY_SENSOR_PRESETS[machine.machineType])}
        >
          긴급 값 채우기
        </button>
      </div>

      <div className="field-grid">
        {NUMBER_FIELDS.map((field) => (
          <div className="field" key={field.key}>
            <label className="field-label" htmlFor={`${machine.machineId}-${field.key}`}>
              {field.label}
            </label>
            <input
              id={`${machine.machineId}-${field.key}`}
              type="number"
              step={field.integer ? 1 : "any"}
              value={values[field.key]}
              onChange={(event) => updateField(field.key, event.target.value)}
              required
            />
          </div>
        ))}
        <div className="field">
          <label className="field-label" htmlFor={`${machine.machineId}-shift`}>
            근무조
          </label>
          <select
            id={`${machine.machineId}-shift`}
            value={values.shift}
            onChange={(event) => updateField("shift", event.target.value)}
          >
            {SHIFT_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor={`${machine.machineId}-experience`}>
            숙련도
          </label>
          <select
            id={`${machine.machineId}-experience`}
            value={values.experience}
            onChange={(event) => updateField("experience", event.target.value)}
          >
            {EXPERIENCE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor={`${machine.machineId}-training`}>
            안전교육 이수
          </label>
          <select
            id={`${machine.machineId}-training`}
            value={values.training}
            onChange={(event) => updateField("training", event.target.value)}
          >
            {TRAINING_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && <p className="status-block error">{error.message}</p>}

      <button type="submit" className="primary" disabled={submitting}>
        {submitting ? "전송 중..." : "센서 값 제출"}
      </button>
    </form>
  );
}
