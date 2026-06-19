import os
import json

# ── Paths ─────────────────────────────────────────────────────────────
# Default to the repository root so a normal git clone works out of the box.
BASE_DIR    = os.path.abspath(
    os.getenv('SECURITY_CAMERA_BASE_DIR', os.path.dirname(__file__))
)
MODEL_PATH  = os.path.join(BASE_DIR, 'models', 'detect.tflite')
LABEL_PATH  = os.path.join(BASE_DIR, 'models', 'labelmap.txt')

# ── Camera ────────────────────────────────────────────────────────────
FRAME_WIDTH  = 1280
FRAME_HEIGHT = 720
FPS          = 10
CAMERA_HFLIP = True   # flip horizontally (camera is mounted upside down)
CAMERA_VFLIP = True   # flip vertically

# Camera backend selection. 'auto' detects a working camera (CSI first, then a
# USB/V4L2 webcam); 'csi' or 'usb' force one. Override per-Pi with the
# CAMERA_BACKEND / CAMERA_DEVICE env vars so you never have to edit this file.
CAMERA_BACKEND = os.getenv('CAMERA_BACKEND', 'auto').lower()
CAMERA_DEVICE  = os.getenv('CAMERA_DEVICE')   # None = auto; USB index e.g. '0'

# ── Detection ─────────────────────────────────────────────────────────
DETECTION_THRESHOLD = 0.4   # Min confidence for detection (0.0-1.0)
CONSECUTIVE_FRAMES_REQUIRED = 2  # Require N consecutive frames per label
RECORDING_COOLDOWN  = 10    # seconds to keep recording after the object leaves the frame
PRESENCE_CHECK_INTERVAL = 1.0  # while recording, re-run detection this often even with no motion
SNAPSHOT_INTERVAL   = 3     # Min seconds between snapshots

# ── Detection diagnostics ─────────────────────────────────────────────
DETECTION_DEBUG       = False  # log raw scores before filtering (for tuning)
DETECTION_DEBUG_FLOOR = 0.20   # min score worth logging

# ── Motion filter ─────────────────────────────────────────────────────
MOTION_ENABLED   = True
MOTION_THRESHOLD = 25
MOTION_MIN_AREA  = 500
MOTION_BLUR      = 21

# ── Storage ───────────────────────────────────────────────────────────
STORAGE_MAX_PERCENT   = 90    # Disk usage % before cleanup
MAX_RECORDING_SECONDS = 300   # Max recording length (5 min) before auto-split

# ── Web interface ─────────────────────────────────────────────────────
WEB_HOST = '0.0.0.0'
WEB_PORT = 8080

# ── SSL ───────────────────────────────────────────────────────────────
SSL_ENABLED = True
SSL_CERT    = os.path.join(BASE_DIR, 'ssl', 'cert.pem')
SSL_KEY     = os.path.join(BASE_DIR, 'ssl', 'key.pem')

# ── Telegram ──────────────────────────────────────────────────────────
# The web settings form writes telegram_settings.json (gitignored). Its filled
# fields take precedence; env vars are the fallback. Neither is committed.
def _telegram_overrides():
    try:
        with open(os.path.join(BASE_DIR, 'telegram_settings.json')) as f:
            return json.load(f)
    except Exception:
        return {}

_tg_file = _telegram_overrides()
TELEGRAM_BOT_TOKEN          = (_tg_file.get('bot_token') or os.getenv('TELEGRAM_BOT_TOKEN', '')).strip()
TELEGRAM_CHAT_ID            = str(_tg_file.get('chat_id') or os.getenv('TELEGRAM_CHAT_ID', '')).strip()
_tg_env_enabled             = os.getenv('TELEGRAM_ENABLED', 'false').lower() in ('1', 'true', 'yes', 'on')
# Only truly enable when both credentials exist, so a half-filled form can never
# crash-loop the service on startup (validate_config would otherwise reject it).
TELEGRAM_ENABLED            = (
    bool(_tg_file.get('enabled', _tg_env_enabled))
    and bool(TELEGRAM_BOT_TOKEN) and bool(TELEGRAM_CHAT_ID)
)
TELEGRAM_COOLDOWN           = 30   # Seconds between alerts
TELEGRAM_COOLDOWN_PER_LABEL = 60   # Seconds between alerts for same label

# ── Heartbeat (optional) — outbound ping so a monitor alerts you if the Pi dies ──
HEARTBEAT_URL      = os.getenv('HEARTBEAT_URL', '')
HEARTBEAT_INTERVAL = 300   # seconds between pings

# ── Logging ───────────────────────────────────────────────────────────
LOG_LEVEL        = 'INFO'
LOG_MAX_BYTES    = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


# ── Validation ────────────────────────────────────────────────────────
def validate_config():
    """Validate all config values on startup. Raises ValueError if invalid."""
    errors = []

    if not 0 < DETECTION_THRESHOLD < 1:
        errors.append(
            f"DETECTION_THRESHOLD must be between 0 and 1, "
            f"got {DETECTION_THRESHOLD}"
        )
    if FPS <= 0:
        errors.append(f"FPS must be > 0, got {FPS}")
    if CAMERA_BACKEND not in ('auto', 'csi', 'usb'):
        errors.append(
            f"CAMERA_BACKEND must be 'auto', 'csi' or 'usb', got '{CAMERA_BACKEND}'"
        )
    if FRAME_WIDTH <= 0 or FRAME_HEIGHT <= 0:
        errors.append(
            f"FRAME_WIDTH and FRAME_HEIGHT must be > 0, "
            f"got {FRAME_WIDTH}x{FRAME_HEIGHT}"
        )
    if RECORDING_COOLDOWN < 0:
        errors.append(
            f"RECORDING_COOLDOWN must be >= 0, got {RECORDING_COOLDOWN}"
        )
    if CONSECUTIVE_FRAMES_REQUIRED <= 0:
        errors.append(
            "CONSECUTIVE_FRAMES_REQUIRED must be >= 1, "
            f"got {CONSECUTIVE_FRAMES_REQUIRED}"
        )
    if SNAPSHOT_INTERVAL < 0:
        errors.append(
            f"SNAPSHOT_INTERVAL must be >= 0, got {SNAPSHOT_INTERVAL}"
        )
    if MAX_RECORDING_SECONDS <= 0:
        errors.append(
            f"MAX_RECORDING_SECONDS must be > 0, got {MAX_RECORDING_SECONDS}"
        )
    if not 0 < STORAGE_MAX_PERCENT <= 100:
        errors.append(
            f"STORAGE_MAX_PERCENT must be between 1 and 100, "
            f"got {STORAGE_MAX_PERCENT}"
        )
    if MOTION_BLUR % 2 == 0 or MOTION_BLUR < 1:
        errors.append(
            f"MOTION_BLUR must be a positive odd number, got {MOTION_BLUR}"
        )
    if not os.path.exists(MODEL_PATH):
        errors.append(f"Model file not found: {MODEL_PATH}")
    if not os.path.exists(LABEL_PATH):
        errors.append(f"Label file not found: {LABEL_PATH}")
    if SSL_ENABLED:
        if not os.path.exists(SSL_CERT):
            errors.append(f"SSL cert not found: {SSL_CERT}")
        if not os.path.exists(SSL_KEY):
            errors.append(f"SSL key not found: {SSL_KEY}")
    if TELEGRAM_ENABLED and (not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID):
        errors.append(
            "TELEGRAM_ENABLED is True but BOT_TOKEN or CHAT_ID is empty"
        )

    if errors:
        raise ValueError(
            "Configuration errors found:\n" +
            "\n".join(f"  • {e}" for e in errors)
        )
