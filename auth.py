import os
import re
import hashlib
import secrets
import logging
from functools import wraps
from flask import request, Response
from config import BASE_DIR

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = os.path.join(BASE_DIR, 'auth.txt')
DEFAULT_USERNAME = 'admin'
# Strong default — user should change this immediately
DEFAULT_PASSWORD = 'Cam@' + secrets.token_hex(4)


def _hash_password(password: str) -> str:
    """SHA-256 password hashing."""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_credentials():
    """Load credentials from file, create with strong default if missing."""
    if not os.path.exists(CREDENTIALS_FILE):
        _save_credentials(DEFAULT_USERNAME, DEFAULT_PASSWORD)
        # Print ONLY to console — never to log file
        # so the plaintext password is never written to disk
        print(
            f"\n{'='*50}\n"
            f"⚠️  FIRST RUN — default credentials created:\n"
            f"    username : {DEFAULT_USERNAME}\n"
            f"    password : {DEFAULT_PASSWORD}\n"
            f"    Change immediately with /password in Telegram!\n"
            f"{'='*50}\n"
        )
        logger.warning(
            "auth.txt created with auto-generated password. "
            "Check console output for credentials. "
            "Change immediately using /password in Telegram."
        )

    with open(CREDENTIALS_FILE, 'r') as f:
        lines = f.read().strip().splitlines()

    creds = {}
    for line in lines:
        if ':' in line:
            user, hashed = line.split(':', 1)
            creds[user.strip()] = hashed.strip()
    return creds


def _save_credentials(username: str, password: str):
    """Save hashed credentials to file."""
    hashed = _hash_password(password)
    with open(CREDENTIALS_FILE, 'w') as f:
        f.write(f"{username}:{hashed}\n")
    os.chmod(CREDENTIALS_FILE, 0o600)


def check_credentials(username: str, password: str) -> bool:
    """Verify username/password pair using constant-time comparison."""
    creds = _load_credentials()
    if username not in creds:
        return False
    return secrets.compare_digest(
        creds[username],
        _hash_password(password)
    )


def is_strong_password(password: str) -> tuple[bool, str]:
    """
    Check password strength.
    Returns (is_strong: bool, reason: str).
    Requirements:
      - At least 8 characters
      - At least one uppercase letter
      - At least one lowercase letter
      - At least one digit
      - At least one special character
    """
    if len(password) < 8:
        return False, "პაროლი მინიმუმ 8 სიმბოლო უნდა იყოს"
    if not re.search(r'[A-Z]', password):
        return False, "პაროლი უნდა შეიცავდეს მინიმუმ ერთ დიდ ასოს"
    if not re.search(r'[a-z]', password):
        return False, "პაროლი უნდა შეიცავდეს მინიმუმ ერთ პატარა ასოს"
    if not re.search(r'\d', password):
        return False, "პაროლი უნდა შეიცავდეს მინიმუმ ერთ ციფრს"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>@_\-]', password):
        return False, "პაროლი უნდა შეიცავდეს მინიმუმ ერთ სპეციალურ სიმბოლოს (!@#$...)"
    return True, "OK"


def change_password(username: str, new_password: str) -> tuple[bool, str]:
    """
    Change password with strength validation.
    Returns (success: bool, message: str).
    """
    strong, reason = is_strong_password(new_password)
    if not strong:
        return False, reason
    _save_credentials(username, new_password)
    logger.info(f"Password changed for user: {username}")
    return True, "პაროლი წარმატებით შეიცვალა"


def require_auth(f):
    """Flask decorator — enforce Basic Auth on route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_credentials(auth.username, auth.password):
            logger.warning(
                f"Access denied — "
                f"IP: {request.remote_addr} "
                f"user: {auth.username if auth else 'unknown'}"
            )
            return Response(
                'Access denied. Please enter your credentials.',
                401,
                {'WWW-Authenticate': 'Basic realm="Security Camera"'}
            )
        return f(*args, **kwargs)
    return decorated
