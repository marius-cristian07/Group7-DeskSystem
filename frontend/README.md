# React frontend (Sprint 3, S3-3)

The temporary view shows live desk names, heights, and statuses. S3-4 will replace it with the dashboard.

## Local setup

Follow [the project setup guide](../SETUP.md) once. Then, from the repository root:

```powershell
python run.py
```

Open **http://127.0.0.1:5173**. This starts the simulator, backend, and React in one terminal. Ctrl+C stops them together. The launcher configures the local addresses and reads the simulator key for the backend.

For frontend-only work with a backend already running, use `npm install` once and `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort` from `frontend/`. Keeping port 5173 matches the backend's allowed browser origins. Use `npm run build` to check the production build. The project setup guide also has the separate service commands for debugging.

The frontend defaults to `http://127.0.0.1:8080`. When starting Vite manually, you can copy `frontend/.env.example` to `frontend/.env.local` and change `VITE_API_BASE_URL` (for example, `http://127.0.0.1:8081`); restart Vite afterward. The launcher supplies its own matching local address. This value is included in browser code, so it must contain only the Python backend address. Never put the simulator key or simulator URL in any `VITE_` variable. The browser calls only `/api/desks`, `/api/desks/{desk_id}`, and `/api/health` on the Python backend.

## Dashboard integration

Import `useDesks` from `src/hooks/useDesks.js` and call it in the dashboard component:

```jsx
const { desks, loading, error, lastUpdated, refresh } = useDesks();
```

`desks` is an array returned directly by `GET /api/desks`. Each desk has `desk_id`, `name`, `position_mm`, `speed_mms`, `status`, `is_anti_collision`, and `last_errors` (an array of `{time_s, errorCode}`). `loading` is true during a request. `error` is a message or `null`. `lastUpdated` is a `Date` for the last successful response or `null`. `refresh()` triggers an immediate request. The hook polls about every five seconds, skips overlapping requests, and clears `desks` and `lastUpdated` if a request fails. It keeps polling after errors, so it recovers when the backend becomes available again.

For a detail request, import `getDesk(deskId)` from `src/api/desks.js`. `getDesks()` and `getHealth()` are also exported there. Each accepts an optional `{ signal }` for cancellation. The API module handles HTTP errors and backend `{ "detail": "..." }` responses.
