import os

# ── გზები ────────────────────────────────────────────────────────────
BASE_DIR    = os.path.expanduser('~/security_camera')
MODEL_PATH  = os.path.join(BASE_DIR, 'models', 'detect.tflite')
LABEL_PATH  = os.path.join(BASE_DIR, 'models', 'labelmap.txt')

# ── კამერა ───────────────────────────────────────────────────────────
FRAME_WIDTH  = 1280
FRAME_HEIGHT = 720
FPS          = 10

# ── დეტექტირება ──────────────────────────────────────────────────────
DETECTION_THRESHOLD = 0.4   # მინიმალური სიზუსტე დეტექტირებისთვის
RECORDING_COOLDOWN  = 10    # წამი ბოლო დეტექტირების შემდეგ ჩაწერის გასაგრძელებლად
SNAPSHOT_INTERVAL   = 3     # მინიმალური წამი სნეფშოტებს შორის

# ── მოძრაობის ფილტრი ─────────────────────────────────────────────────
MOTION_ENABLED   = True  # False — ყველა კადრზე გაუშვი ML
MOTION_THRESHOLD = 25    # პიქსელის სიკაშკაშის ცვლილება (0-255)
MOTION_MIN_AREA  = 500   # მინიმალური კონტური პიქსელებში
MOTION_BLUR      = 21    # გაუსის ბლური (კენტი რიცხვი)

# ── შენახვა ───────────────────────────────────────────────────────────
STORAGE_MAX_PERCENT = 90  # დისკის გამოყენების ზღვარი (%),
                          # რის შემდეგაც ძველი ფაილები წაიშლება

# ── ვებ-ინტერფეისი ────────────────────────────────────────────────────
WEB_HOST = '0.0.0.0'
WEB_PORT = 8080

# ── Telegram ──────────────────────────────────────────────────────────
TELEGRAM_ENABLED = False        # True — ჩართე შეტყობინებები
TELEGRAM_BOT_TOKEN = ''         # შეიყვანე შენი Bot Token
TELEGRAM_CHAT_ID   = ''         # შეიყვანე შენი Chat ID
TELEGRAM_COOLDOWN  = 30         # წამი შეტყობინებებს შორის

# ── Logging ───────────────────────────────────────────────────────────
LOG_LEVEL    = 'INFO'           # DEBUG, INFO, WARNING, ERROR
LOG_MAX_BYTES  = 5 * 1024 * 1024  # 5 მბ მაქსიმალური ლოგ ფაილი
LOG_BACKUP_COUNT = 3              # ლოგ ფაილების რაოდენობა rotation-ისთვის
