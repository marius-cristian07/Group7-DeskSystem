export const RUN_LABELS = {
  scheduled: 'Scheduled', raising: 'Raising', returning: 'Returning', completed: 'Completed',
  cancelled: 'Cancelled', blocked: 'Blocked',
  cleaning: 'Cleaning window', needs_review: 'Needs review', resolved: 'Resolved',
};

const validTime = (value) => /^([01]\d|2[0-3]):[0-5]\d$/.test(value);

export function windowDescription(start, end) {
  if (!validTime(start) || !validTime(end)) return 'Choose a daily start and return time.';
  if (start === end) return 'Start and return times must differ; a 24-hour window is not supported.';
  // times use hh:mm so this comparison also detects overnight windows
  return end < start
    ? `Overnight: starts at ${start}; returns at ${end} the following day.`
    : `Starts at ${start}; returns at ${end} the same day.`;
}

export function validateSchedule(form, limits) {
  const errors = {};
  if (!form.name.trim()) errors.name = 'Enter a schedule name.';
  if (!form.desk_ids.length) errors.desk_ids = 'Select at least one desk.';
  for (const field of ['cleaning_height_mm', 'return_height_mm']) {
    const height = Number(form[field]);
    if (!Number.isInteger(height) || height < limits.min || height > limits.max) {
      errors[field] = `Enter a whole number between ${limits.min} and ${limits.max} mm.`;
    }
  }
  if (!validTime(form.start_time)) errors.start_time = 'Enter a valid start time.';
  if (!validTime(form.end_time)) errors.end_time = 'Enter a valid return time.';
  if (validTime(form.start_time) && form.start_time === form.end_time) {
    errors.end_time = 'Return time must differ from start time.';
  }
  return errors;
}

// the backend works out the next occurrence and we only format it
export function formatOccurrence(value, timezone) {
  if (!value) return 'None planned';
  return new Date(value).toLocaleString(undefined, { timeZone: timezone });
}

// number inputs still give us text so convert heights before saving
export function schedulePayload(form) {
  return {
    ...form, name: form.name.trim(),
    cleaning_height_mm: Number(form.cleaning_height_mm),
    return_height_mm: Number(form.return_height_mm),
  };
}

export function runProblems(run) {
  // check every desk in both movements rather than only the run status
  const results = (run.operations || []).flatMap((operation) => operation.desks || []);
  return results.filter((result) => !['pending', 'moving', 'reached'].includes(result.result));
}

export function runLabel(run) {
  // the run says raising or returning while its group may still be warning
  const operationId = run.status === 'returning' ? run.return_operation_id : run.raise_operation_id;
  const current = (run.operations || []).find(operation => operation.operation_id === operationId);
  if (['raising', 'returning'].includes(run.status) && ['pending_warning', 'countdown'].includes(current?.state)) {
    return `Warning before ${run.status === 'returning' ? 'returning' : 'raising'}`;
  }
  return RUN_LABELS[run.status] || `Unknown state: ${run.status}`;
}
