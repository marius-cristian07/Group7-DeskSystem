# Group7-DeskSystem

Smart Office Desk Coordination: a Python backend, a React frontend, and the WiFi2BLE desk simulator.

After the [first-time setup](SETUP.md), start the local app from the repository root:

```powershell
python run.py
```

Open **http://127.0.0.1:5173**. The launcher runs all three services in this terminal; press **Ctrl+C** to stop them. It reads the local simulator key for the backend and uses the fast loopback addresses automatically. PostgreSQL continues running as your existing local service.

- [Setup, startup, and troubleshooting](SETUP.md)
- [Frontend data interface for S3-4](frontend/README.md)
- [PostgreSQL setup](database/SETUP.md)
- [CLI show, sync, and move commands](docs/sprint2-workflow.md)
- [Backend API contract](docs/backend-api-contract.md)
- [Simulator + database demo](docs/simulator-database-demo.md)
- [Desk data contract and examples](docs/desk-data-contract.md)

## Code layout

- `run.py`: starts and stops the local services.
- `DeskSystemPROJECT/config.py`: shared local addresses and environment settings.
- `DeskSystemPROJECT/server.py`: HTTP routes and frontend response formatting.
- `DeskSystemPROJECT/UI/`: command parsing and terminal output.
- `DeskSystemPROJECT/Domain/`: the existing show, sync, and move workflows.
- `DeskSystemPROJECT/Data/`: simulator requests and PostgreSQL persistence.
- `frontend/src/api/` and `frontend/src/hooks/`: frontend requests and refresh state.
- `wifi2ble-box-simulator/`: external simulator submodule.

## Checks

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s DeskSystemPROJECT/Tests
npm --prefix frontend run build
```

The default Python tests use fake network and database dependencies; they do not move desks or write to your database.

For the optional launcher integration check, stop the local app first, then run:

```powershell
$env:DESK_RUN_LIVE_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest DeskSystemPROJECT.Tests.test_live_integration -v
Remove-Item Env:DESK_RUN_LIVE_TESTS
```

This check starts the real services on their usual ports with temporary simulator data, changes a test desk height, and verifies shutdown. It leaves your simulator data and PostgreSQL alone.
