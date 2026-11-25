import { useState } from 'react';
import { saveCleaningSchedule, disableCleaningSchedule } from '../api/cleaning';
import { formatOccurrence, windowDescription } from '../utils/cleaningSchedule';
import CleaningScheduleForm from './CleaningScheduleForm';
import CleaningRunHistory from './CleaningRunHistory';
import '../cleaning.css';

export default function CleaningSchedules({ desks, desksUnavailable, feed }) {
  const { data, loading, error, refresh } = feed;
  // null closes the form and new opens it without an existing schedule
  const [editor, setEditor] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  const [message, setMessage] = useState(null);

  async function save(id, payload) {
    setBusy(true);
    setMessage(null);
    setActionError(null);
    try {
      await saveCleaningSchedule(id, payload);
      setEditor(null);
      setMessage('Schedule saved for future occurrences. A run already started is unchanged.');
      refresh();
    } finally {
      // let save errors reach the form so the manager can correct them
      setBusy(false);
    }
  }

  async function disable(schedule) {
    setBusy(true);
    setActionError(null);
    setMessage(null);
    try {
      await disableCleaningSchedule(schedule.schedule_id);
      setMessage('Future occurrences disabled. A run already started keeps its authorized return.');
      refresh();
    } catch (failure) {
      setActionError(failure.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="cleaning" aria-labelledby="cleaning-title">
      <div className="cleaning-heading">
        <div><h2 id="cleaning-title">Cleaning schedules</h2><p>Configure daily cleaning heights and sitting return times.</p></div>
        <div className="cleaning-actions">
          <button type="button" disabled={busy || loading} onClick={refresh}>Refresh schedules</button>
          <button type="button" disabled={!data || Boolean(error) || busy || Boolean(editor)} onClick={() => setEditor({ new: true })}>New schedule</button>
        </div>
      </div>
      {error && <div className="notice notice--error" role="alert">{error}{data && <p>Showing old data. Refresh to confirm current progress. Changes are paused until reconnection.</p>}</div>}
      {loading && !data && <p role="status">Loading cleaning schedules…</p>}
      {actionError && <p className="notice notice--error" role="alert">{actionError}</p>}
      {message && <p className="notice" role="status">{message}</p>}
      {data && <>
        {!data.scheduler_enabled && <p className="notice" role="status">Automatic cleaning is paused on the server. You can manage schedules; planned times will not trigger movement until the scheduler is enabled.</p>}
        <p>Facility timezone: <strong>{data.timezone}</strong>. Monitoring refreshes every five seconds.</p>
        {desksUnavailable && <p className="notice notice--error" role="alert">Desk data is unavailable. Restore the desk connection to change desk selections and save schedules.</p>}
        {editor && <CleaningScheduleForm key={editor.new ? 'new' : editor.schedule_id} schedule={editor.new ? null : editor}
          desks={desks} timezone={data.timezone} limits={data.height_limits_mm} busy={busy}
          unavailable={Boolean(error) || desksUnavailable} onSave={save} onClose={() => setEditor(null)} />}
        {!data.schedules.length && <p className="notice">No schedules yet. Create a schedule to choose desks and daily cleaning times.</p>}
        <div className="cleaning-schedule-list">
          {data.schedules.map((schedule) => (
            <article className="cleaning-panel" key={schedule.schedule_id}>
              <div className="cleaning-heading"><h3>{schedule.name}</h3><span className={`badge badge--${schedule.is_enabled ? 'idle' : 'error'}`}>{schedule.is_enabled ? 'Enabled' : 'Disabled'}</span></div>
              <p>Desks: {schedule.desk_ids.map((id) => `${desks.find((desk) => desk.desk_id === id)?.name || 'Unavailable desk'} (${id})`).join(', ')}</p>
              <p>Cleaning: <strong>{schedule.cleaning_height_mm} mm</strong> · Sitting return: <strong>{schedule.return_height_mm} mm</strong></p>
              <p>Daily {schedule.start_time.slice(0, 5)}–{schedule.end_time.slice(0, 5)} ({schedule.timezone}). {windowDescription(schedule.start_time.slice(0, 5), schedule.end_time.slice(0, 5))}</p>
              <p>Next planned occurrence: <strong>{formatOccurrence(schedule.next_occurrence?.start_at, schedule.timezone)}</strong></p>
              <div className="cleaning-actions">
                <button type="button" disabled={busy || Boolean(error) || Boolean(editor)} onClick={() => { setMessage(null); setEditor(schedule); }}>Edit {schedule.name}</button>
                {schedule.is_enabled && <button type="button" disabled={busy || Boolean(error) || Boolean(editor)} onClick={() => disable(schedule)}>Disable future occurrences</button>}
              </div>
            </article>
          ))}
        </div>
        <CleaningRunHistory runs={data.runs} timezone={data.timezone} stale={Boolean(error)} />
      </>}
    </section>
  );
}
