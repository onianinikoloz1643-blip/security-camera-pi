import time
import logging
import requests
import cv2
from config import (
    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID, TELEGRAM_COOLDOWN,
    TELEGRAM_COOLDOWN_PER_LABEL
)

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends one-way detection alerts and snapshots to Telegram.
    Includes global cooldown and per-label cooldown to prevent spam.
    """

    def __init__(self):
        self.enabled  = TELEGRAM_ENABLED
        self.token    = TELEGRAM_BOT_TOKEN
        self.chat_id  = TELEGRAM_CHAT_ID

        self._last_sent_time   = 0
        self._last_label_times = {}  # label -> last sent timestamp

        if self.enabled and (not self.token or not self.chat_id):
            logger.warning(
                "Telegram enabled but BOT_TOKEN or CHAT_ID missing — disabled"
            )
            self.enabled = False

    def _global_cooldown_ok(self):
        return time.time() - self._last_sent_time >= TELEGRAM_COOLDOWN

    def _label_cooldown_ok(self, label):
        last = self._last_label_times.get(label, 0)
        return time.time() - last >= TELEGRAM_COOLDOWN_PER_LABEL

    def send_detection(self, frame, detections):
        """
        Send snapshot and detection summary to Telegram.
        Respects both global and per-label cooldowns.
        """
        if not self.enabled:
            return
        if not self._global_cooldown_ok():
            return

        # Filter to only labels whose per-label cooldown has passed
        new_detections = [
            d for d in detections
            if self._label_cooldown_ok(d['label'])
        ]
        if not new_detections:
            return

        try:
            # Build caption
            label_ka = {
                'person':     'ადამიანი',
                'car':        'მანქანა',
                'truck':      'სატვირთო',
                'bus':        'ავტობუსი',
                'motorcycle': 'მოტოციკლი',
                'bicycle':    'ველოსიპედი',
            }

            counts = {}
            for d in new_detections:
                counts[d['label']] = counts.get(d['label'], 0) + 1

            parts = [
                f"{label_ka.get(l, l)}: {c}"
                for l, c in counts.items()
            ]

            text = (
                f"🚨 *დეტექტირება*\n"
                f"📋 {', '.join(parts)}\n"
                f"🎯 სიზუსტე: "
                f"{max(d['score'] for d in new_detections):.0%}"
            )

            # Encode frame to JPEG in memory
            _, img_encoded = cv2.imencode(
                '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            img_bytes = img_encoded.tobytes()

            url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
            response = requests.post(
                url,
                data={
                    'chat_id':    self.chat_id,
                    'caption':    text,
                    'parse_mode': 'Markdown'
                },
                files={'photo': ('detection.jpg', img_bytes, 'image/jpeg')},
                timeout=10
            )

            if response.status_code == 200:
                now = time.time()
                self._last_sent_time = now
                for d in new_detections:
                    self._last_label_times[d['label']] = now
                logger.info(
                    f"Telegram alert sent — "
                    f"{list(counts.keys())}"
                )
            else:
                logger.warning(
                    f"Telegram error: {response.status_code} — "
                    f"{response.text}"
                )

        except requests.exceptions.Timeout:
            logger.warning("Telegram timeout — alert not sent")
        except requests.exceptions.ConnectionError:
            logger.warning("Telegram connection error — internet available?")
        except Exception as e:
            logger.error(f"Telegram unexpected error: {e}")

    def send_message(self, text):
        """Send a plain text message."""
        if not self.enabled:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(
                url,
                data={
                    'chat_id':    self.chat_id,
                    'text':       text,
                    'parse_mode': 'Markdown'
                },
                timeout=10
            )
        except Exception as e:
            logger.error(f"Telegram message error: {e}")

