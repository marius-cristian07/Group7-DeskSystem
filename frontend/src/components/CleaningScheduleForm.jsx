import { useId, useRef, useState } from 'react';
import { schedulePayload, validateSchedule, windowDescription } from '../utils/cleaningSchedule';

export default function CleaningScheduleForm({ schedule, desks, timezone, limits, busy, unavailable, onSave, onClose }) {
  const prefix = useId();
  const errorSummary = useRef(null);
  // copy existing values when editing and use defaults when creating
  const [form, setForm] = useState(() => schedule ? {
    name: schedule.name, desk_ids: [...schedule.desk_ids],
    cleaning_height_mm: String(schedule.cleaning_height_mm),
    return_height_mm: String(schedule.return_height_mm), start_time: schedule.start_time.slice(0, 5),
    end_time: schedule.end_time.slice(0, 5), timezone: schedule.timezone, is_enabled: schedule.is_enabled,
  } : {
    name: '', desk_ids: [], cleaning_height_mm: '', return_height_mm: '',
    start_time: '18:00', end_time: '20:00', timezone, is_enabled: true,
  });
  const [errors, setErrors] = useState({});
  const [backendError, setBackendError] = useState(null);
  const change = (field, value) => setForm((previous) => ({ ...previous, [field]: value }));

  // keep selected desks visible even if they are offline
  const selectedDesks = [...desks];
  for (const id of form.desk_ids) {
    if (!selectedDesks.some((desk) => desk.desk_id === id)) {
      selectedDesks.push({ desk_id: id, name: `Unavailable desk (${id})` });
    }
  }

  async function submit(event) {
    event.preventDefault();
    const nextErrors = validateSchedule(form, limits);
    setErrors(nextErrors);
    setBackendError(null);
    if (Object.keys(nextErrors).length) {
      // focus the message after react has displayed it
      requestAnimationFrame(() => errorSummary.current?.focus());
      return;
    }
    try {
      await onSave(schedule?.schedule_id, schedulePayload(form));
    } catch (error) {
      setBackendError(error.message);
      // focus the message after react has displayed it
      requestAnimationFrame(() => errorSummary.current?.focus());
    }
  }

  // keep the label and error message connected to their input
  const field = (name, label, type, extra = {}) => (
    <div className="cleaning-field">
      <label htmlFor={`${prefix}-${name}`}>{label}</label>
      <input id={`${prefix}-${name}`} type={type} value={form[name]}
        onChange={(event) => change(name, event.target.value)}
        aria-invalid={Boolean(errors[name])} aria-describedby={errors[name] ? `${prefix}-${name}-error` : undefined}
        {...extra} />
      {errors[name] && <span className="cleaning-error" id={`${prefix}-${name}-error`}>{errors[name]}</span>}
    </div>
  );
  return (
    <section className="cleaning-panel" aria-labelledby={`${prefix}-title`}>
      <h3 id={`${prefix}-title`}>{schedule ? 'Edit cleaning schedule' : 'New cleaning schedule'}</h3>
      <p>All daily times use <strong>{form.timezone}</strong>. Heights use millimetres.</p>
      <p>Changes apply to future occurrences. Editing is refused while a run is active or needs review. Disabling future occurrences keeps the current run’s authorized return.</p>
      <form onSubmit={submit} noValidate>
        {(Object.keys(errors).length > 0 || backendError) && (
          <div className="notice notice--error" role="alert" tabIndex={-1} ref={errorSummary}>
            {backendError || 'Please correct the highlighted fields.'}
          </div>
        )}
        <fieldset disabled={busy || unavailable} className="cleaning-fields">
          <legend>Schedule configuration</legend>
          {field('name', 'Schedule name', 'text', { required: true })}
          <fieldset className="cleaning-desk-picker" aria-describedby={`${prefix}-desks-help`}>
            <legend>Participating desks</legend>
            <p id={`${prefix}-desks-help`}>Select at least one desk. The backend checks availability and schedule conflicts.</p>
            {!selectedDesks.length && <p>No desks are available. Retry the desk connection before creating a schedule.</p>}
            {selectedDesks.map((desk) => (
              <label key={desk.desk_id}>
                <input type="checkbox" checked={form.desk_ids.includes(desk.desk_id)}
                  onChange={(event) => change('desk_ids', event.target.checked
                    ? [...form.desk_ids, desk.desk_id] : form.desk_ids.filter((id) => id !== desk.desk_id))} />
                {desk.name} <small>({desk.desk_id})</small>
              </label>
            ))}
            {errors.desk_ids && <p className="cleaning-error">{errors.desk_ids}</p>}
          </fieldset>
          <p className="cleaning-help">Allowed height range: {limits.min}–{limits.max} mm, enforced by the backend.</p>
          <div className="cleaning-columns">
            {field('cleaning_height_mm', 'Cleaning height (mm)', 'number', { min: limits.min, max: limits.max, step: 1, required: true })}
            {field('return_height_mm', 'Sitting return height (mm)', 'number', { min: limits.min, max: limits.max, step: 1, required: true })}
            {field('start_time', 'Daily start time', 'time', { required: true, step: 60 })}
            {field('end_time', 'Daily end / return time', 'time', { required: true, step: 60 })}
          </div>
          <p>{windowDescription(form.start_time, form.end_time)} Times follow {form.timezone}, including daylight-saving changes.</p>
          <label><input type="checkbox" checked={form.is_enabled} onChange={(event) => change('is_enabled', event.target.checked)} /> Enable future occurrences</label>
        </fieldset>
        <div className="cleaning-actions">
          <button type="submit" disabled={busy || unavailable}>{busy ? 'Saving…' : 'Save schedule'}</button>
          <button type="button" disabled={busy} onClick={onClose}>Close form</button>
        </div>
      </form>
    </section>
  );
}
