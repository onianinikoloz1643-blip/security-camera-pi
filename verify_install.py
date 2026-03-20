"""
Installation verification script.
Checks that all dependencies, files and hardware are correctly set up.
Run: python verify_install.py
"""
import os
import sys

BASE_DIR = os.path.expanduser('~/security_camera')
PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []


def check(name, condition, fix=None, warning=False):
    """Record a check result."""
    icon = WARN if warning and not condition else (PASS if condition else FAIL)
    results.append((icon, name, fix if not condition else None))
    print(f"  {icon}  {name}")
    if not condition and fix:
        print(f"       Fix: {fix}")
    return condition


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)


# ── Python version ────────────────────────────────────────────────────
section("Python Environment")
check(
    f"Python 3.10+ (running {sys.version.split()[0]})",
    sys.version_info >= (3, 10),
    "Upgrade Python to 3.10 or later"
)
check(
    "Running inside virtualenv",
    hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    ),
    "Activate venv: source venv/bin/activate"
)

# ── Python packages ───────────────────────────────────────────────────
section("Python Packages")

packages = [
    ("ai_edge_litert", "ai-edge-litert", "pip install ai-edge-litert"),
    ("cv2",            "OpenCV",         "sudo apt install python3-opencv"),
    ("flask",          "Flask",          "pip install flask"),
    ("numpy",          "NumPy",          "pip install numpy"),
    ("requests",       "requests",       "pip install requests"),
    ("picamera2",      "Picamera2",      "sudo apt install python3-picamera2"),
]

for module, name, fix in packages:
    try:
        __import__(module)
        check(f"{name} installed", True)
    except ImportError:
        check(f"{name} installed", False, fix)

# ── Project files ─────────────────────────────────────────────────────
section("Project Files")

required_files = [
    ("main.py",            "Main application"),
    ("config.py",          "Configuration"),
    ("detector.py",        "Object detector"),
    ("camera.py",          "Camera module"),
    ("motion.py",          "Motion detector"),
    ("storage.py",         "Storage manager"),
    ("auth.py",            "Authentication"),
    ("web.py",             "Web interface"),
    ("telegram_notify.py", "Telegram notifier"),
    ("telegram_bot.py",    "Telegram bot"),
    ("mock_camera.py",     "Mock camera (testing)"),
    ("test_system.py",     "System test"),
    ("benchmark.py",       "Benchmarking"),
]

for filename, description in required_files:
    path = os.path.join(BASE_DIR, filename)
    check(
        f"{description} ({filename})",
        os.path.exists(path),
        f"File missing: {path}"
    )

# ── Model files ───────────────────────────────────────────────────────
section("ML Model")

model_path = os.path.join(BASE_DIR, 'models', 'detect.tflite')
label_path = os.path.join(BASE_DIR, 'models', 'labelmap.txt')

model_exists = check(
    "TFLite model (detect.tflite)",
    os.path.exists(model_path),
    "wget -O models/detect.tflite "
    "https://storage.googleapis.com/mediapipe-tasks/"
    "object_detector/efficientdet_lite0_uint8.tflite"
)

if model_exists:
    size_mb = os.path.getsize(model_path) / (1024 * 1024)
    check(
        f"Model size reasonable ({size_mb:.1f}MB, expected ~4.4MB)",
        3 < size_mb < 10,
        "Re-download the model — file may be corrupted"
    )

check(
    "Label map (labelmap.txt)",
    os.path.exists(label_path),
    "Re-create labelmap.txt — see README"
)

if os.path.exists(label_path):
    with open(label_path) as f:
        labels = [l.strip() for l in f.readlines()]
    check(
        f"Label map has entries ({len(labels)} labels)",
        len(labels) >= 80,
        "labelmap.txt appears incomplete — re-create it"
    )
    for required in ['person', 'car', 'truck', 'bus']:
        check(
            f"Security label '{required}' present",
            required in labels,
            f"Add '{required}' to labelmap.txt"
        )

# ── SSL ───────────────────────────────────────────────────────────────
section("SSL / HTTPS")

ssl_cert = os.path.join(BASE_DIR, 'ssl', 'cert.pem')
ssl_key  = os.path.join(BASE_DIR, 'ssl', 'key.pem')

check(
    "SSL certificate (cert.pem)",
    os.path.exists(ssl_cert),
    "openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem "
    "-out ssl/cert.pem -days 365 -nodes -subj '/CN=raspberrypi.local'"
)
check(
    "SSL private key (key.pem)",
    os.path.exists(ssl_key),
    "Re-generate SSL certificate (see above)"
)

if os.path.exists(ssl_key):
    import stat
    mode = oct(stat.S_IMODE(os.stat(ssl_key).st_mode))
    check(
        f"SSL key permissions secure ({mode})",
        mode == '0o600',
        f"chmod 600 ssl/key.pem",
        warning=True
    )

# ── Config validation ─────────────────────────────────────────────────
section("Configuration")

try:
    from config import validate_config
    validate_config()
    check("Config values valid", True)
except ValueError as e:
    check("Config values valid", False, str(e))
except Exception as e:
    check("Config importable", False, str(e))

# ── Camera ────────────────────────────────────────────────────────────
section("Camera Hardware")

try:
    import subprocess
    result = subprocess.run(
        ['rpicam-still', '--list-cameras'],
        capture_output=True, text=True, timeout=10
    )
    output = result.stdout + result.stderr
    camera_found = 'imx708' in output.lower()
    check(
        "IMX708 camera detected",
        camera_found,
        "Check physical connection and config.txt "
        "(camera_auto_detect=0, dtoverlay=imx708)"
    )
except FileNotFoundError:
    check(
        "rpicam-still available",
        False,
        "sudo apt install rpicam-apps"
    )
except subprocess.TimeoutExpired:
    check("Camera detection (timeout)", False, "Try: rpicam-still --list-cameras")

# ── Systemd service ───────────────────────────────────────────────────
section("Systemd Service")

service_path = '/etc/systemd/system/security-camera.service'
service_exists = check(
    "systemd service file exists",
    os.path.exists(service_path),
    "See README for service setup instructions"
)

if service_exists:
    result = os.popen('systemctl is-enabled security-camera 2>/dev/null').read().strip()
    check(
        f"Service enabled on boot ({result})",
        result == 'enabled',
        "sudo systemctl enable security-camera"
    )

# ── Summary ───────────────────────────────────────────────────────────
passed  = sum(1 for icon, _, _ in results if icon == PASS)
warned  = sum(1 for icon, _, _ in results if icon == WARN)
failed  = sum(1 for icon, _, _ in results if icon == FAIL)
total   = len(results)

print(f"\n{'='*50}")
print(f"  SUMMARY: {passed}/{total} passed  |  "
      f"{warned} warnings  |  {failed} failed")
print('='*50)

if failed == 0 and warned == 0:
    print("  🎉 All checks passed — system is ready!")
elif failed == 0:
    print("  ✅ All critical checks passed — review warnings above")
else:
    print("  ❌ Some checks failed — fix the issues above before running")

print()
