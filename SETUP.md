# Run the project locally

Use PowerShell from the repository root. Install Python 3.11 or newer, Node.js 22.12 or newer, and Git first.

## First-time setup

```powershell
git submodule update --init --recursive
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend install
```

On macOS/Linux, the virtual environment interpreter is `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

PostgreSQL is needed only for the CLI commands that save data (`sync` and `move`). Configure it separately using [database/SETUP.md](database/SETUP.md). The web app reads live simulator data and does not need a database.

## Start and stop

```powershell
python run.py
```

Open **http://127.0.0.1:5173**. Keep this one terminal open. Press **Ctrl+C** once to stop all three services; allow a few seconds for the simulator to save its state.

The launcher:

- Starts the simulator on 8000, the Python backend on 8080, and React on 5173, waiting for each to be ready.
- Uses `.venv` automatically when present, so you do not need to activate it.
- Reads the first key from `wifi2ble-box-simulator/config/api_keys.json`, unless `DESK_API_KEY` is already set.
- Gives the simulator key only to the backend and hides it in the combined terminal log.
- Stops the other services if one exits unexpectedly.
- Leaves PostgreSQL running as your existing local service.

Stop any servers you previously started by hand before running the launcher. It reports an occupied port instead of starting on a different one.

## Check it works

1. Open the React page. It should show available desks and an update time.
2. Wait a few seconds. The update time should advance as the page refreshes.
3. Open `http://127.0.0.1:8080/api/health`; it should return `{"status":"ok"}`.
4. Open `http://127.0.0.1:8080/api/desks`; it should return an array of desks.

The number of available desks can change because the simulator temporarily powers desks off. A desk disappearing during the backend's list request can still produce a 502 response; the frontend retries automatically. That API behavior is unchanged by this refactor.

## Configuration

The launcher uses the three local ports above and supplies the matching addresses itself. The manual startup commands below still support environment overrides.

- `DESK_API_BASE_URL`: simulator address used by Python; default `http://127.0.0.1:8000`.
- `DESK_API_KEY`: simulator key used by Python. The launcher reads the local key automatically.
- `DATABASE_URL`: PostgreSQL connection used by CLI `sync` and `move`.
- `VITE_API_BASE_URL`: backend address used by React when starting Vite manually; default `http://127.0.0.1:8080`.

Python does not automatically load the root `.env` file. The root `.env.example` documents server-side values. Vite loads `frontend/.env.local` when used manually; copy `frontend/.env.example` if you need a different backend address. Every `VITE_` value can appear in browser code, so it must never contain the simulator key or a database password.

Use `127.0.0.1` for local requests. On the development Windows machine, `localhost` added roughly two seconds per Python simulator request.

## Existing CLI commands

The commands are unchanged:

```powershell
$env:DESK_API_KEY = (Get-Content wifi2ble-box-simulator/config/api_keys.json -Raw | ConvertFrom-Json)[0]
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py show

# Set your own credentials before running commands that save data.
$env:DATABASE_URL = 'postgresql://USERNAME:PASSWORD@127.0.0.1:5432/group7_desksystem'
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py sync
.\.venv\Scripts\python.exe DeskSystemPROJECT/DeskSystemPROJECT.py move DESK_ID 1000
```

Run these optional commands from another terminal while the app is running. The app itself needs only the launcher terminal. See [the workflow guide](docs/sprint2-workflow.md) for results and exit codes.

## Manual startup for debugging

If you need to stop and restart one service independently, run these in separate terminals instead of using the launcher.

Simulator, from its own directory:

```powershell
cd wifi2ble-box-simulator
python simulator/main.py --port 8000
```

Backend, from the repository root:

```powershell
$env:DESK_API_KEY = (Get-Content wifi2ble-box-simulator/config/api_keys.json -Raw | ConvertFrom-Json)[0]
.\.venv\Scripts\python.exe -m uvicorn DeskSystemPROJECT.server:app --host 127.0.0.1 --port 8080
```

React, from the repository root:

```powershell
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

This mode also lets you check frontend recovery: stop only the backend, wait for the connection error, then restart it. The frontend should recover without a page reload.

For simulator HTTPS or other simulator options, see [its README](wifi2ble-box-simulator/README.md). For example, from its directory:

```powershell
python simulator/main.py --port 8443 --https --certfile config/cert.pem --keyfile config/key.pem
```

## Troubleshooting

- **Missing packages:** repeat the first-time install commands. Dependencies are installed once, not on every launch.
- **Port busy:** stop the corresponding old server with Ctrl+C and retry. The launcher does not stop servers it did not start.
- **Missing key:** check that the simulator submodule and its `config/api_keys.json` exist. An explicitly set `DESK_API_KEY` must be valid for that simulator.
- **502 from the backend:** check the simulator log; it may be unavailable or a desk may have powered off during the request.
- **503 from a manually started backend:** set `DESK_API_KEY` in that terminal and restart the backend.
- **Simulator flags seem ignored:** saved values in `wifi2ble-box-simulator/data/desks_state.json` override some simulator startup options, including power-off chance.

