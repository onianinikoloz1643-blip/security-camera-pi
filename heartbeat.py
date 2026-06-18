import time
import logging
import threading
import requests
from config import HEARTBEAT_URL, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)


def start_heartbeat():
    """Ping a monitor URL on an interval so an external service can alert you
    when the Pi goes offline (power loss, crash, network loss). Does nothing if
    HEARTBEAT_URL is not set."""
    if not HEARTBEAT_URL:
        return

    def _loop():
        logger.info("Heartbeat started")
        while True:
            try:
                requests.get(HEARTBEAT_URL, timeout=10)
            except Exception as e:
                logger.warning(f"Heartbeat ping failed: {e}")
            time.sleep(HEARTBEAT_INTERVAL)

    threading.Thread(target=_loop, daemon=True).start()
