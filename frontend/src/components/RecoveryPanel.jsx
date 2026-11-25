import { useRef, useState } from 'react';
import { getJson } from '../api/desks';
import { useSavedResource } from '../hooks/useSavedResource';
import '../recovery.css';

const tabs = ['Needs review', 'Incident history', 'Operation history', 'Review log'];
const routes = { Incident: 'desk-incidents', Operation: 'group-operations', 'Cleaning run': 'cleaning-schedules/runs' };
const words = value => value?.replaceAll('_', ' ') || 'Unknown';
const time = value => value ? new Date(value).toLocaleString() : 'Unknown';
const decisions = ['inspected_ok', 'moved_manually', 'fault_repaired', 'nothing_to_review'];

function OperationEvidence({ op, deskName }) {
  return <>
    <p>{op.reason} · Target {op.target_position_mm} mm · {words(op.state)}</p>
    <p>Started {time(op.created_at)} · {op.finished_at ? 'Finished ' + time(op.finished_at) : 'In progress'}</p>
    <p>{op.blocked_message || op.message}</p>
    <ul>{op.desks.map(d => <li key={d.desk_id}>
      <strong>{deskName(d.desk_id)}</strong> · {words(d.result)} · {d.detail}
      {d.last_position_mm != null && <> · {d.last_position_mm} mm</>}
      {d.last_observed_at && <> · Observed {time(d.last_observed_at)}</>}
      {d.fault_codes?.length > 0 && <> · {d.fault_codes.map(words).join(', ')}</>}
    </li>)}</ul>
  </>;
}

function LinkedOperation({ id, deskName }) {
  const [open, setOpen] = useState(false);
  const { data, error } = useSavedResource(open ? '/api/group-operations/' + encodeURIComponent(id) : null);
  return <details onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Operation {id}</summary>
    {open && (error ? <p role="alert">{error}</p> : data ? <OperationEvidence op={data} deskName={deskName} /> : <p>Loading operation…</p>)}
  </details>;
}

function ReviewForm({ kind, id, acknowledged, onSaved }) {
  const [decision, setDecision] = useState('');
  const [explanation, setExplanation] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef(false);
  async function submit(action) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    const resolving = action === 'resolve';
    const body = resolving ? { decision, explanation: explanation.trim(), resolved_by: name || null } :
      { acknowledged_by: name || null };
    try {
      const result = await getJson('/api/' + routes[kind] + '/' + encodeURIComponent(id) + '/' + action, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      onSaved(resolving ? kind + ' ' + id + ' resolved. Review record #' + result.record_id + '.' :
        'Acknowledgement recorded. This incident still needs review.');
    } catch (failure) {
      setError((resolving ? 'Resolution' : 'Acknowledgement') + ' could not be confirmed. ' + failure.message);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return <form className="review-form" onSubmit={event => { event.preventDefault(); submit('resolve'); }}>
    <fieldset disabled={busy}><legend>Review {kind.toLowerCase()}</legend>
      <label>Reviewer (optional)<input value={name} maxLength={100} onChange={e => setName(e.target.value)} /></label>
      {kind === 'Incident' && (acknowledged ? <p>Acknowledged {time(acknowledged)}</p> :
        <button type="button" onClick={() => submit('acknowledge')}>Acknowledge incident</button>)}
      <label>Decision<select required value={decision} onChange={e => setDecision(e.target.value)}>
        <option value="">Select a decision</option>
        {decisions.map(d => <option key={d} value={d}>{words(d)}</option>)}
      </select></label>
      <label>Resolution explanation<textarea required minLength={10} maxLength={1000} value={explanation}
        onChange={e => setExplanation(e.target.value)} /></label>
      <p>Resolution records your decision after fresh checks. It does not move a desk or repair a physical fault.</p>
      <button disabled={!decision || explanation.trim().length < 10}>Resolve {kind.toLowerCase()}</button>
    </fieldset>
    {error && <p role="alert">{error}</p>}
  </form>;
}

export default function RecoveryPanel({ catalogue, desks, runs, liveError, lastUpdated }) {
  const [tab, setTab] = useState(tabs[0]);
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState('');
  const [selected, setSelected] = useState(null);
  const paths = ['/api/reviews/unresolved', '/api/desk-incidents', '/api/group-operations/history', '/api/reviews/records'];
  const paged = tab === tabs[1] || tab === tabs[2];
  const path = paths[tabs.indexOf(tab)] + (paged ? '?limit=20&offset=' + offset : '');
  const { data, error } = useSavedResource(path, revision);
  const deskName = id => {
    const desk = desks.find(d => d.desk_id === id) || catalogue?.find(d => d.desk_id === id);
    return desk ? desk.name + ' (' + id + ')' : id;
  };
  function saved(text) {
    setMessage(text); setSelected(null); setRevision(n => n + 1);
  }
  const problems = desks.filter(d => d.health !== 'healthy');
  const offline = lastUpdated && !liveError ? catalogue?.filter(d => !desks.some(live => live.desk_id === d.desk_id)) : [];
  function entry(kind, id, title, content, review, acknowledged) {
    const key = kind + id;
    return <article key={key} className="review-entry">
      <button className="review-toggle" aria-expanded={selected === key}
        onClick={() => setSelected(selected === key ? null : key)}>{title}</button>
      {selected === key && <div>{content}
        {review && <ReviewForm kind={kind} id={id} acknowledged={acknowledged} onSaved={saved} />}
      </div>}
    </article>;
  }
  function relatedRun(opId) {
    if (!opId) return null;
    const run = runs?.find(r => [r.raise_operation_id, r.return_operation_id].includes(opId));
    return run && <p>Cleaning run #{run.run_id} · {run.schedule_name} · {words(run.status)}</p>;
  }
  function incident(i) {
    const review = (i.review_state ?? 'needs_review') === 'needs_review';
    return entry('Incident', i.incident_id, deskName(i.desk_id) + ' · ' + words(i.fault_category) +
      ' · ' + (i.cleared_at ? 'Cleared' : 'Last observed active') + ' · ' + (review ? 'Needs review' : 'Resolved'), <>
      <p>Incident #{i.incident_id} · First observed {time(i.first_seen_at)} · Last observed {time(i.last_seen_at)}</p>
      {i.cleared_at && <p>Cleared {time(i.cleared_at)}</p>}
      {i.blocks_starts != null && <p>{i.blocks_starts ? 'Blocks automatic cleaning starts.' : 'Automatic starts are allowed by this incident.'}</p>}
      {i.operation_id ? <><LinkedOperation id={i.operation_id} deskName={deskName} />{relatedRun(i.operation_id)}</> : <p>No linked operation.</p>}
    </>, review, i.acknowledged_at);
  }
  function operation(op) {
    const review = (op.review_state ?? 'needs_review') === 'needs_review';
    return entry('Operation', op.operation_id, words(op.state) + ' · ' + op.desk_ids.map(deskName).join(', ') +
      ' · ' + words(op.review_state ?? 'needs_review'), <>
      <p>{op.operation_id}</p>{relatedRun(op.operation_id)}
      {op.desks ? <OperationEvidence op={op} deskName={deskName} /> : <LinkedOperation id={op.operation_id} deskName={deskName} />}
    </>, review);
  }
  function run(r) {
    return entry('Cleaning run', r.run_id, r.schedule_name + ' · Run #' + r.run_id + ' · Needs review', <>
      <p>{r.desk_ids.map(deskName).join(', ')} · Updated {time(r.updated_at)}</p>
      {runs?.find(item => item.run_id === r.run_id)?.blocked_reason}
      {[r.raise_operation_id, r.return_operation_id].filter(Boolean).map(id => <LinkedOperation key={id} id={id} deskName={deskName} />)}
    </>, true);
  }
  return <section className="recovery" aria-labelledby="recovery-title">
    <h2 id="recovery-title">Faults and recovery</h2>
    <h3>Current desk health</h3>
    {liveError ? <p>Live data unavailable. Current health is unknown.</p> : !lastUpdated ? <p>Checking live desks…</p> :
      problems.length ? <ul>{problems.map(d => <li key={d.desk_id}>{deskName(d.desk_id)} · {d.fault_codes?.length ?
        d.fault_codes.map(words).join(', ') : 'Communication uncertain · ' + d.status}</li>)}</ul> :
      <p>{desks.length ? 'No active faults reported by online desks.' : 'No desks online.'}</p>}
    {offline?.length > 0 && <p>Offline at the latest live check: {offline.map(d => deskName(d.desk_id)).join(', ')}</p>}
    <nav aria-label="Saved evidence">{tabs.map(t => <button key={t} aria-pressed={t === tab}
      onClick={() => { setTab(t); setOffset(0); setSelected(null); setMessage(''); }}>{t}</button>)}</nav>
    {message && <p role="status">{message}</p>}
    {error ? <p role="alert">{error} <button onClick={() => setRevision(n => n + 1)}>Retry</button></p> :
      !data ? <p>Loading saved evidence…</p> : <>
        {tab === tabs[0] && <>
          <p>{data.cleaning_runs.length} cleaning runs · {data.group_operations.length} operations · {data.desk_incidents.length} incidents awaiting review</p>
          {data.blocking_desk_ids.length > 0 && <p>Automatic cleaning blocked for {data.blocking_desk_ids.map(deskName).join(', ')}.</p>}
          {data.cleaning_runs.map(run)}{data.group_operations.map(operation)}{data.desk_incidents.map(incident)}
        </>}
        {tab === tabs[1] && (data.incidents.length ? data.incidents.map(incident) : <p>No saved incidents on this page.</p>)}
        {tab === tabs[2] && (data.operations.length ? data.operations.map(operation) : <p>No saved operations on this page.</p>)}
        {tab === tabs[3] && (data.records.length ? data.records.map(r => <article key={r.record_id} className="review-entry">
          <strong>{words(r.subject_type)} {r.subject_id} · {words(r.action)}</strong>
          <p>{time(r.recorded_at)} · {r.recorded_by || 'Reviewer unspecified'}{r.decision && ' · ' + words(r.decision)}</p>
          <p>{r.explanation}</p>
          {Object.entries(r.desk_checks || {}).map(([id, d]) => <p key={id}>{deskName(id)} · {d.classification} · {d.position_mm} mm · {time(d.checked_at)}</p>)}
        </article>) : <p>No saved reviews.</p>)}
        {paged && <div className="review-pages"><button disabled={!offset} onClick={() => { setSelected(null); setOffset(offset - 20); }}>Previous</button>
          Page {offset / 20 + 1}
          <button disabled={data.next_offset == null} onClick={() => { setSelected(null); setOffset(data.next_offset); }}>Next</button></div>}
      </>}
  </section>;
}
