# Desk dashboard

Select desk checkboxes, enter a target height and choose **Review movement** to see
the exact group before confirming. A warning appears for manual movements and
both phases of a cleaning schedule. Keep the dashboard visible to acknowledge
the warning, or choose **Cancel movement** before dispatch. Group results show
each desk's reported outcome.

## Local setup

Follow [the project setup guide](../SETUP.md) once. Then, from the repository root:

```powershell
python run.py
```

Open **http://127.0.0.1:5173**. This starts the simulator, backend, and React in one terminal. Ctrl+C stops them together. The launcher configures the local addresses and reads the simulator key for the backend.

For frontend-only work with a backend already running, use `npm install` once and `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort` from `frontend/`. Keeping port 5173 matches the backend's allowed browser origins. Use `npm run build` to check the production build. The project setup guide also has the separate service commands for debugging.

The frontend defaults to `http://127.0.0.1:8080`. For manual Vite startup, set
`VITE_API_BASE_URL` in `frontend/.env.local` to the Python backend address and
restart Vite. The launcher sets this address automatically. Simulator credentials
belong on the backend.

For a repeatable group demo, stop any running launcher and run the following
in the PowerShell terminal with your local `DATABASE_URL` configured:

```powershell
$env:GROUP_WARNING_REQUIRED_CHANNELS = 'dashboard'
.\.venv\Scripts\python.exe run.py --stable-simulator
```

Select both desks, enter **1000 mm**, review and confirm. Keep the warning visible
through the countdown. Both desks should report **reached**. The stable simulator
starts desks 4486 and 6743 at 680 mm in temporary storage each time. It disables
simulated users and random faults. Commands and readings still use your configured
PostgreSQL database. For Pico integration, set the channels to `pico,dashboard`.
See [group operations](../docs/group-operations.md).

## Dashboard integration

Import `useDesks` from `src/hooks/useDesks.js` and call it in the dashboard component:

```jsx
const { desks, loading, error, lastUpdated, refresh } = useDesks();
```

`desks` is an array returned directly by `GET /api/desks`. Each desk has `desk_id`, `name`, `position_mm`, `speed_mms`, `status`, `is_anti_collision`, and `last_errors` (an array of `{time_s, errorCode}`). `loading` is true during a request. `error` is a message or `null`. `lastUpdated` is a `Date` for the last successful response or `null`. `refresh()` triggers an immediate request. The hook polls about every five seconds, skips overlapping requests, and clears `desks` and `lastUpdated` if a request fails. It keeps polling after errors, so it recovers when the backend becomes available again.

For a detail request, import `getDesk(deskId)` from `src/api/desks.js`. `getDesks()` and `getHealth()` are also exported there. Each accepts an optional `{ signal }` for cancellation. The API module handles HTTP errors and backend `{ "detail": "..." }` responses.
