# Intelligent Security Camera — Raspberry Pi 5

A local security camera that detects people and vehicles in real time on a Raspberry Pi 5.
Everything runs on the device: there is no cloud service, account, or subscription. When it
detects something, it saves a snapshot and a video clip, updates a web dashboard, and can send
a Telegram alert.

Built as my bachelor's capstone project at Caucasus University.

## What it does

- Detects people and vehicles (car, motorcycle, bus, truck, bicycle) with a TensorFlow Lite model.
- Runs a lightweight motion filter first, so the neural network only runs when something moves.
- Treats each appearance as one event: it saves a single snapshot and records one clip for the
  duration, instead of writing an image every few seconds.
- Serves a web dashboard over HTTPS with live updates, a snapshot viewer (click to enlarge,
  scroll to zoom, drag to pan), and the recordings list with thumbnails and timestamps.
- Sends Telegram alerts with a photo and accepts commands back through an interactive bot.
- Manages its own disk space and runs as a systemd service that restarts on failure.

## Hardware

| Component | Detail |
|---|---|
| Raspberry Pi 5 | 8 GB |
| Camera | Arducam IMX708 (wide-angle, autofocus) |
| Storage | 64 GB microSD |
| Power | 27 W (5 V / 5 A) USB-C supply |
| OS | Raspberry Pi OS 64-bit (Bookworm) |

A note on power: an undersized supply caused under-voltage shutdowns during early testing. The
5 V/5 A supply fixed it. Continuous detection keeps the CPU busier than an idle Pi, so the supply
matters.

## How it works

The main loop in `main.py` runs this pipeline per frame:

1. **Capture** — `camera.py` grabs a 1280×720 frame from the IMX708 with Picamera2.
2. **Motion filter** — `motion.py` compares the frame to the previous one. If nothing changed,
   the frame is dropped before any inference. This is the main reason the system stays cool.
3. **Detection** — `detector.py` runs the frame through EfficientDet-Lite0 (INT8) with the LiteRT
   runtime, keeps detections above a confidence threshold, and requires a label to appear in two
   consecutive inferences before confirming it. The second check suppresses single-frame false
   positives.
4. **Event handling** — on the first confirmed detection it saves one annotated snapshot, sends a
   Telegram alert, and starts recording. Recording continues until there have been no detections
   for a cooldown period.
5. **Storage** — `storage.py` writes snapshots (JPEG) and clips (AVI), and deletes the oldest
   files once the disk passes 90%.

The web server in `web.py` runs in a background thread and pushes live updates to the browser
using Server-Sent Events.

### Detection model and its limits

The detector uses EfficientDet-Lite0 quantized to INT8 — a small model chosen so inference is
fast on the Pi's CPU. It detects people and vehicles reliably at close to medium range in
reasonable light. It is less reliable on distant or poorly-lit subjects, where confidence falls
below the threshold. That is a property of a model this small, and the threshold is kept where it
is on purpose: lowering it would let in spurious boxes and raise the sustained CPU and thermal
load. Placement and lighting affect accuracy as much as the configuration does.

## Software

| Package | Role |
|---|---|
| Python 3.13 | Runtime |
| ai-edge-litert | TensorFlow Lite (LiteRT) inference on ARM64 |
| EfficientDet-Lite0 INT8 | Detection model (COCO classes) |
| OpenCV | Frame processing, annotation, video writing |
| Picamera2 | Camera capture |
| Flask | Web interface |
| NumPy | Array processing |
| requests | Telegram API calls |

## Performance

Measured on the Raspberry Pi 5 with `benchmark.py` (100 inference frames, 200 motion frames):

| Metric | Result |
|---|---|
| Inference latency | 42.7 ms mean (min 42.2, max 49.3, σ 0.9) |
| Inference throughput | 23.4 FPS |
| Motion filter | 5.3 ms per frame (~190 FPS) |
| CPU temperature under load | 58.7 °C |
| RAM | 588 MB / 8 GB |
| CPU (during benchmark) | ~14% |

The capture loop is capped at 10 FPS, so the ~23 FPS inference ceiling leaves room to spare, and
the motion filter removes most inference work on a static scene. The Pi runs well below its
thermal throttle point (~80 °C).

## Installation

Tested on Raspberry Pi OS 64-bit (Bookworm).

### 1. Clone
```bash
git clone https://github.com/onianinikoloz1643-blip/security-camera-pi.git ~/security_camera
cd ~/security_camera
```

### 2. Virtual environment
```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

### 3. Dependencies
```bash
sudo apt install -y python3-picamera2 python3-opencv
pip install ai-edge-litert flask numpy requests
```

### 4. Detection model
```bash
mkdir -p models
wget -O models/detect.tflite \
  https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite
```
The label file `models/labelmap.txt` (COCO classes) is already in the repository.

### 5. Camera
Add to `/boot/firmware/config.txt`:
```
camera_auto_detect=0
dtoverlay=imx708
```
If the image comes out upside-down or mirrored, set `CAMERA_HFLIP` / `CAMERA_VFLIP` in `config.py`.

### 6. HTTPS certificate
The web interface runs over HTTPS. Generate a self-signed certificate:
```bash
mkdir -p ssl
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
  -keyout ssl/key.pem -out ssl/cert.pem -subj "/CN=raspberrypi.local"
```

### 7. Run
```bash
python main.py
```
On the first run the system creates `auth.txt` with a randomly generated admin password and
prints it to the console once — note it down. Open `https://raspberrypi.local:8080` and log in.

### 8. Telegram (optional)
Create a bot with **@BotFather**, get your numeric chat ID (for example from **@userinfobot**),
and pass them as environment variables so they are never stored in the repository:
```bash
export TELEGRAM_ENABLED=true
export TELEGRAM_BOT_TOKEN='your-token'
export TELEGRAM_CHAT_ID='your-chat-id'
```

## Running as a service

Create `/etc/systemd/system/security-camera.service`:
```ini
[Unit]
Description=Security Camera System
After=network.target

[Service]
User=raspberry
WorkingDirectory=/home/raspberry/security_camera
ExecStart=/home/raspberry/security_camera/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
To enable Telegram for the service, add the credentials with `sudo systemctl edit security-camera`:
```
[Service]
Environment=TELEGRAM_ENABLED=true
Environment=TELEGRAM_BOT_TOKEN=your-token
Environment=TELEGRAM_CHAT_ID=your-chat-id
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now security-camera
```
`Restart=always` brings the service back if it ever exits.

## Web interface

Served at `https://<pi>:8080` behind HTTP basic auth. It shows system status (snapshot and
recording counts, disk usage), the most recent snapshots, and the recordings list with a
thumbnail and timestamp for each clip. Updates arrive live over SSE, so new detections appear
without a reload. Clicking a snapshot opens it full-screen, where you can scroll to zoom and drag
to pan.

## Telegram bot

When enabled, the bot sends an alert with a photo on detection and responds to:

| Command | Action |
|---|---|
| `/status` | Uptime, counts, disk, recording state |
| `/snapshot` | Send the latest snapshot |
| `/disk` | Disk usage |
| `/stop` | Pause detection |
| `/start` | Resume detection |
| `/password <new>` | Change the web password |
| `/help` | List commands |

Alerts have a per-label and a global cooldown so a single event does not flood the chat. Commands
are only accepted from the configured chat ID.

## Configuration

Key settings in `config.py`:

| Setting | Default | Meaning |
|---|---|---|
| `DETECTION_THRESHOLD` | 0.4 | Minimum confidence to count a detection |
| `CONSECUTIVE_FRAMES_REQUIRED` | 2 | Inferences a label must appear in before confirming |
| `MOTION_ENABLED` | True | Skip inference on static frames |
| `RECORDING_COOLDOWN` | 10 | Seconds of no detection before recording stops |
| `MAX_RECORDING_SECONDS` | 300 | Split recordings into five-minute files |
| `STORAGE_MAX_PERCENT` | 90 | Disk usage that triggers cleanup of old files |
| `FPS` | 10 | Capture rate |

`config.py` validates these on startup and refuses to run with invalid values or missing files
(the model or the certificate).

## Project layout

```
main.py              Orchestrator: detection loop, web thread, clean shutdown
config.py            Settings and startup validation
detector.py          EfficientDet-Lite0 inference and confirmation filter
camera.py            Picamera2 capture, annotation, recording
motion.py            Pixel-difference motion filter
storage.py           Snapshots, recordings, disk cleanup, logging
auth.py              Web basic auth (SHA-256, password rules)
web.py               Flask HTTPS dashboard with SSE
telegram_notify.py   Outgoing detection alerts
telegram_bot.py      Interactive command bot
mock_camera.py       Camera stand-in for testing without hardware
test_system.py       Run the full pipeline with the mock camera
benchmark.py         Inference, motion, and system benchmarks
verify_install.py    Checks dependencies, files, model, camera, service
models/labelmap.txt  COCO class labels
```

## Testing without a camera

`test_system.py` runs the whole pipeline against `mock_camera.py`, which feeds a still image (or a
generated frame) instead of the IMX708. It is useful for working on the web interface or detection
logic away from the Pi. `verify_install.py` checks that the dependencies, project files, model,
camera, and service are all in place.

## Stability

The service restarts automatically on failure (`Restart=always`). Logs are written to `logs/` with
rotation (5 MB × 3 files) so they cannot fill the disk, and old snapshots and recordings are
deleted once the disk passes 90%. Shutdown is handled cleanly: the camera is released and any
in-progress recording is finalized.

## License

MIT. Nikoloz Oniani, Caucasus University, 2026.
