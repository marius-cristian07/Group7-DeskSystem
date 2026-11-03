# React frontend (Sprint 3, S3-3)

The temporary view shows live desk names, heights, and statuses. S3-4 will replace it with the dashboard.

## Local setup

From the repository root, use three terminals in this order:

1. Start the simulator on port 8000: `cd wifi2ble-box-simulator` then `python simulator/main.py --port 8000`.
2. Start the Python backend on port 8080. Install Python packages once with `python -m pip install -r requirements.txt`. Set `DESK_API_KEY` in **this backend terminal** to a key from `wifi2ble-box-simulator/config/api_keys.json`, then run `python -m uvicorn DeskSystemPROJECT.server:app --host 127.0.0.1 --port 8080` from the repository root. For PowerShell, set the variables with `$env:DESK_API_KEY = (Get-Content wifi2ble-box-simulator/config/api_keys.json -Raw | ConvertFrom-Json)[0]` and `$env:DESK_API_BASE_URL = 'http://127.0.0.1:8000'`. The backend defaults to `http://localhost:8000` if `DESK_API_BASE_URL` is unset. On Windows, that hostname can add about two seconds to each simulator request, so the loopback IP is recommended for local development. The backend does not load `.env` automatically.
3. Start React: `cd frontend`, `npm install`, then `npm run dev`. Open the address printed by Vite, normally `http://localhost:5173`.

The frontend defaults to `http://127.0.0.1:8080`. To use a different backend address, copy `frontend/.env.example` to `frontend/.env.local` and change `VITE_API_BASE_URL` (for example, `http://127.0.0.1:8081`); restart Vite afterward. This value is included in browser code, so it must contain only the Python backend address. Never put the simulator key or simulator URL in any `VITE_` variable. The browser calls only `/api/desks`, `/api/desks/{desk_id}`, and `/api/health` on the Python backend.

## Dashboard integration

Import `useDesks` from `src/hooks/useDesks.js` and call it in the dashboard component:

```jsx
const { desks, loading, error, lastUpdated, refresh } = useDesks();
```

`desks` is an array returned directly by `GET /api/desks`. Each desk has `desk_id`, `name`, `position_mm`, `speed_mms`, `status`, `is_anti_collision`, and `last_errors` (an array of `{time_s, errorCode}`). `loading` is true during a request. `error` is a message or `null`. `lastUpdated` is a `Date` for the last successful response or `null`. `refresh()` triggers an immediate request. The hook polls about every five seconds, skips overlapping requests, and clears `desks` and `lastUpdated` if a request fails. It keeps polling after errors, so it recovers when the backend becomes available again.

For a detail request, import `getDesk(deskId)` from `src/api/desks.js`. `getDesks()` and `getHealth()` are also exported there. Each accepts an optional `{ signal }` for cancellation. The API module handles HTTP errors and backend `{ "detail": "..." }` responses.
