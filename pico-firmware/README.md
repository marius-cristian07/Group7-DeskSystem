# Pico W movement warning and connection indicator

The connected Pico covers one shared warning area. Its red LED (GP7) and
active-high buzzer input (GP20) pulse together every 250 ms. Connect the
carrier board button on GP10. The current configuration expects high when pressed
and low when released; verify this on the board before relying on cancellation.
A rising edge latches cancellation
even when the button is released during a quiet part of the blink cycle.

## Run a movement test

Flash the firmware as described below. Close any serial monitor using the Pico.
From the repository root, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DESK_PICO_PORT = "COM6"
$env:GROUP_WARNING_REQUIRED_CHANNELS = "pico"
.\.venv\Scripts\python.exe run.py --stable-simulator
```

Use the board's actual USB serial port and the project's configured PostgreSQL
database. Open http://127.0.0.1:5173 and request a group height change. Press
the physical button during the warning. The dashboard should show cancellation
and the simulator should stay at its original height. Repeat the request and
let the default 10 seconds expire. The simulator should reach the target.
The same procedure runs for both directions of scheduled cleaning movements.
The scheduler has its own opt-in setting, `CLEANING_SCHEDULER_ENABLED=1`.

The backend owns the USB port and sends a separate operation ID for every
warning. The first board acknowledgement starts the countdown once the other
configured channels are ready. At the deadline the backend requests a final
button check. A lost link, reset, or missing reply prevents release. One board
handles one warning at a time. Other operations wait within their existing
acknowledgement timeout. Choose `pico,dashboard` to require a visible dashboard
as well. The warning uses USB even when Wi-Fi is unavailable.

## Wi-Fi connection indicator

The Pico W periodically requests `GET /api/health` from the FastAPI backend.
The green LED stays on after a successful HTTP 200 response and blinks until the
first successful check or after a failed check. The endpoint checks whether the
backend is reachable.

## Configure the firmware

Run these commands in PowerShell from the repository root. If
`pico-firmware\wifi_credentials.h` already exists, edit that file directly.

```powershell
Copy-Item .\pico-firmware\wifi_credentials.example.h .\pico-firmware\wifi_credentials.h
ipconfig
```

Enter your 2.4 GHz Wi-Fi name and password in `wifi_credentials.h`. Set
`BACKEND_IP` to the IPv4 address of the computer running FastAPI. Use the address
of its Wi-Fi adapter and enter it without a protocol, port, or path. Git ignores
the filled-in file.

## Start the backend

From the repository root, run the following in PowerShell. Skip the first
command if `.venv` already exists.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn DeskSystemPROJECT.server:app --host 0.0.0.0 --port 8085
```

Keep the terminal open. Visit `http://<BACKEND_IP>:8085/api/health` using the
address you configured. The expected response is `{"status":"ok"}`.

## Build and flash

Open `pico-firmware` in VS Code with the Raspberry Pi Pico extension and build
for **Pico W**. Hold BOOTSEL while plugging the Pico into USB, then copy
`build/pico-firmware.uf2` to the `RPI-RP2` drive. The Pico restarts automatically.

## Test the indicator

1. With the backend running, wait for the green LED to stay on.
2. Stop the backend with Ctrl+C. Wait for the next request to fail and check
   that the LED starts blinking. A request timeout can delay the change.
3. Restart the backend on port 8085. Check that the LED stays on again without
   restarting the Pico.
