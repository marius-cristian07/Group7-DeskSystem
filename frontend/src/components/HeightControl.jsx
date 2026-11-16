// Created by : Edris Fiazi
// Created on : 15.11.2026
// Purpose    : KAN-24 Select a desk and request a target height through the dashboard



import { useRef, useState } from 'react';
import { requestDeskHeight } from '../api/desks';

export default function HeightControl({ desk }) {
  const [height, setHeight] = useState('');
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const inFlight = useRef(false);

  async function submit(event) {
    event.preventDefault();
    if (inFlight.current) return;
    const target = Number(height);
    if (!height.trim() || !Number.isInteger(target) || target < 680 || target > 1320) {
      setFeedback({ error: true, text: 'Enter a number between 680 and 1320 mm.' });
      return;
    }
    inFlight.current = true;
    setPending(true);
    setFeedback(null);
    try {
      const result = await requestDeskHeight(desk.desk_id, target);
      const text = result.status === 'accepted'
        ? `Request accepted for ${desk.name}: ${result.accepted_position_mm ?? target} mm. The desk moves gradually; watch the current height above.`
        : result.error || (result.status === 'failed'
          ? 'The desk rejected the request.'
          : 'Acceptance could not be confirmed. Check the current height before another request.');
      setFeedback({ error: result.status !== 'accepted', text,
        warnings: [result.recording_error, result.follow_up_error].filter(Boolean) });
    } catch (error) {
      setFeedback({ error: true, text: error.message });
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <section className="height-control" aria-labelledby="height-control-title">
      <h3 id="height-control-title">Adjust desk height</h3>
      <form onSubmit={submit}>
        <label htmlFor="target-height">Target height (mm)</label>
        <p id="height-help">Enter a number between 680 and 1320 mm for {desk.name}. The current height: {desk.position_mm} mm.</p>
        <div className="height-control__fields">
          <input id="target-height" type="number" min="680" max="1320" step="1" required
            value={height} onChange={(event) => setHeight(event.target.value)}
            aria-describedby="height-help" disabled={pending} />
          <button type="submit" disabled={pending}>{pending ? 'Sending�' : 'Set height'}</button>
        </div>
      </form>
      {pending && <p role="status">Sending height request�</p>}
      {feedback && <div role={feedback.error ? 'alert' : 'status'}>
        <p>{feedback.text}</p>
        {feedback.warnings?.map((warning) => <p key={warning}>{warning}</p>)}
      </div>}
    </section>
  );
}
