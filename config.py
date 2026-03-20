import os

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR    = os.path.expanduser('~/security_camera')
MODEL_PATH  = os.path.join(BASE_DIR, 'models', 'detect.tflite')
LABEL_PATH  = os.path.join(BASE_DIR, 'models', 'labelmap.txt')

# ── Camera ────────────────────────────────────────────────────────────
FRAME_WIDTH  = 1280
FRAME_HEIGHT = 720
FPS          = 10

# ── Detection ─────────────────────────────────────────────────────────
DETECTION_THRESHOLD = 0.4   # Min confidence for detection (0.0-1.0)
RECORDING_COOLDOWN  = 10    # Seconds to keep recording after last detection
SNAPSHOT_INTERVAL   = 3     # Min seconds between snapshots

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
TELEGRAM_ENABLED            = False
TELEGRAM_BOT_TOKEN          = ''
TELEGRAM_CHAT_ID            = ''
TELEGRAM_COOLDOWN           = 30   # Seconds between alerts
TELEGRAM_COOLDOWN_PER_LABEL = 60   # Seconds between alerts for same label

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
    if FRAME_WIDTH <= 0 or FRAME_HEIGHT <= 0:
        errors.append(
            f"FRAME_WIDTH and FRAME_HEIGHT must be > 0, "
            f"got {FRAME_WIDTH}x{FRAME_HEIGHT}"
        )
    if RECORDING_COOLDOWN < 0:
        errors.append(
            f"RECORDING_COOLDOWN must be >= 0, got {RECORDING_COOLDOWN}"
        )
    if SNAPSHOT_INTERVAL < 0:
        errors.append(
            f"SNAPSHOT_INTERVAL must be >= 0, got {SNAPSHOT_INTERVAL}"
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
