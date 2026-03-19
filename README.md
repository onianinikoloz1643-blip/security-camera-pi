# 🎥 Intelligent Security Camera — Raspberry Pi 5

Real-time object detection security camera system built on Raspberry Pi 5.
Detects people and vehicles locally using TensorFlow Lite — no cloud, no subscriptions.

## Features

- Real-time detection of people and vehicles (0.05s inference per frame)
- Motion filter — skips ML inference on static scenes, saving 60-70% CPU
- Event-triggered snapshot and video recording
- Local web interface with live SSE updates (port 8080)
- Telegram notifications with snapshot on detection
- Automatic disk management — cleans oldest files when storage hits 90%
- systemd service — auto-starts on boot, recovers from crashes

## Hardware

| Component | Specification |
|-----------|--------------|
| Raspberry Pi 5 | 8GB RAM |
| Camera | Arducam IMX708 — 12MP, 102° FOV, HDR |
| Storage | 64GB MicroSD (Class 10 / A2) |
| OS | Raspberry Pi OS 64-bit Bookworm |

## Software Stack

| Technology | Role |
|-----------|------|
| Python 3.13 | Main language |
| ai-edge-litert 2.1.3 | TFLite runtime for ARM64 |
| EfficientDet Lite0 INT8 | Object detection model (COCO) |
| OpenCV 4.10 | Frame processing and annotation |
| Picamera2 | Camera capture |
| Flask 3.1.1 | Web interface |
| NumPy 2.2.4 | Vectorised post-processing |

## Project Structure
```
security_camera/
├── main.py              # System orchestrator
├── config.py            # All configuration parameters
├── detector.py          # TFLite inference engine
├── camera.py            # Frame capture and annotation
├── motion.py            # Motion filter (pixel diff)
├── storage.py           # Snapshot/recording/disk management
├── telegram_notify.py   # Telegram alerts
├── web.py               # Flask web interface with SSE
└── models/
    └── labelmap.txt     # COCO class labels
```

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/noniani4-cloud/security-camera-pi.git
cd security-camera-pi
```

### 2. Create virtual environment
```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
sudo apt install -y python3-pip python3-venv libcamera-dev python3-libcamera \
  python3-kms++ libopencv-dev python3-opencv python3-picamera2 ffmpeg
pip install ai-edge-litert flask numpy requests
```

### 4. Download the model
```bash
mkdir -p models
wget -O models/detect.tflite \
  https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite
```

### 5. Configure the camera (Raspberry Pi 5)
Edit `/boot/firmware/config.txt`:
```
camera_auto_detect=0
dtoverlay=imx708
```

### 6. Configure settings
Edit `config.py` to set your preferences:
```python
DETECTION_THRESHOLD = 0.4   # Detection confidence threshold
MOTION_ENABLED      = True  # Enable motion pre-filter
TELEGRAM_ENABLED    = False # Set True and add token for alerts
TELEGRAM_BOT_TOKEN  = ''    # Your Telegram bot token
TELEGRAM_CHAT_ID    = ''    # Your Telegram chat ID
```

### 7. Run
```bash
python main.py
```

Open browser: `http://raspberrypi.local:8080`

## Auto-start on Boot
```bash
sudo nano /etc/systemd/system/security-camera.service
```
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
```bash
sudo systemctl enable security-camera
sudo systemctl start security-camera
```

## Performance

| Metric | Result |
|--------|--------|
| Inference time | ~0.05s per frame |
| Throughput | ~10 FPS |
| CPU (idle) | ~15% |
| Detection classes | person, car, truck, bus, motorcycle, bicycle |

## License

MIT License — Nikoloz Oniani, Caucasus University 2026
