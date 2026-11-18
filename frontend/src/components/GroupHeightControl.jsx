import { useRef, useState } from 'react';
import { createGroup } from '../api/groupOperations';
import { isValidHeight, MIN_HEIGHT_MM, MAX_HEIGHT_MM } from '../utils/height';

export default function GroupHeightControl({ selected, names, available, ready, onSelect, locked, onLock }) {
  const [height, setHeight] = useState('');
  const [review, setReview] = useState(null);
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);
  const sending = useRef(false);
  const unavailable = selected.filter(id => !available.includes(id));
  const valid = ready && selected.length > 0 && !unavailable.length && isValidHeight(Number(height));

  function finishReview() {
    setReview(null);
    onLock(false);
  }

  async function send() {
    if (!review || !valid || sending.current) return;
    sending.current = true;
    setPending(true);
    try {
      await createGroup(review.ids, review.height);
      setMessage('Group request created. Follow its progress on this dashboard.');
      onSelect([]);
    } catch (error) {
      setMessage(error.status && error.status < 500 ? error.message :
        `Request outcome uncertain. Check group movements before trying again. ${error.message}`);
    } finally {
      sending.current = false;
      setPending(false);
      finishReview();
    }
  }

  function beginReview(event) {
    event.preventDefault();
    if (!valid) return;
    setMessage('');
    setReview({ ids: [...selected], height: Number(height) });
    onLock(true);
  }

  function identity(id) {
    return names[id] ? `${names[id]} (${id})` : id;
  }

  return (
    <section className="group-control" aria-labelledby="group-title">
      <div className="group-row">
        <h2 id="group-title">Group height control</h2>
        <div className="group-actions">
          <button disabled={locked || !ready || !available.length} onClick={() => onSelect(available)}>Select all available</button>
          <button disabled={locked || !selected.length} onClick={() => onSelect([])}>Clear selection</button>
        </div>
      </div>
      <p><strong>{selected.length} selected</strong>{selected.length > 0 && <> · {selected.map(identity).join(', ')}</>}</p>
      {unavailable.length > 0 && <p role="status">Unavailable: {unavailable.map(identity).join(', ')}. Update your selection.</p>}
      {review ? (
        <div className="group-review">
          <h3>Confirm group movement</h3>
          <p>Move {review.ids.map(identity).join(', ')} to <strong>{review.height} mm</strong>?</p>
          <div className="group-actions">
            <button className="primary" disabled={pending || !valid} onClick={send}>
              {pending ? 'Submitting…' : 'Confirm movement'}
            </button>
            <button disabled={pending} onClick={finishReview}>Back to selection</button>
          </div>
        </div>
      ) : (
        <form onSubmit={beginReview} className="group-actions">
          <label htmlFor="group-height">Target height (mm)</label>
          <input id="group-height" type="number" min={MIN_HEIGHT_MM} max={MAX_HEIGHT_MM}
            placeholder={`${MIN_HEIGHT_MM}–${MAX_HEIGHT_MM}`} step="1" required
            value={height} onChange={event => setHeight(event.target.value)} />
          <button className="primary" disabled={!valid}>Review movement</button>
        </form>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
