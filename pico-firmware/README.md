# Pico W connection indicator (KAN-18)

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
