import requests
import logging
import time
import cv2
import os
from config import (
    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID, TELEGRAM_COOLDOWN
)

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    აგზავნის შეტყობინებებს და სნეფშოტებს Telegram-ში
    ობიექტების დეტექტირებისას.
    """

    def __init__(self):
        self.enabled          = TELEGRAM_ENABLED
        self.token            = TELEGRAM_BOT_TOKEN
        self.chat_id          = TELEGRAM_CHAT_ID
        self.cooldown         = TELEGRAM_COOLDOWN
        self._last_sent_time  = 0

        if self.enabled and (not self.token or not self.chat_id):
            logger.warning(
                "Telegram ჩართულია, მაგრამ BOT_TOKEN ან CHAT_ID არ არის შევსებული. "
                "გამორთულია."
            )
            self.enabled = False

    def _cooldown_ok(self):
        """შეამოწმე cooldown პერიოდი."""
        return time.time() - self._last_sent_time >= self.cooldown

    def send_detection(self, frame, detections):
        """
        გაუგზავნე სნეფშოტი და დეტექტირების შედეგები Telegram-ში.
        cooldown პერიოდში გამოძახება იგნორირდება.
        """
        if not self.enabled:
            return
        if not self._cooldown_ok():
            return

        try:
            # აღწერის ტექსტის შედგენა
            labels  = [d['label'] for d in detections]
            counts  = {}
            for l in labels:
                counts[l] = counts.get(l, 0) + 1

            parts = []
            label_ka = {
                'person':     'ადამიანი',
                'car':        'მანქანა',
                'truck':      'სატვირთო',
                'bus':        'ავტობუსი',
                'motorcycle': 'მოტოციკლი',
                'bicycle':    'ველოსიპედი',
            }
            for label, count in counts.items():
                ka = label_ka.get(label, label)
                parts.append(f"{ka}: {count}")

            text = (
                f"🚨 *დეტექტირება*\n"
                f"📋 {', '.join(parts)}\n"
                f"🎯 სიზუსტე: {max(d['score'] for d in detections):.0%}"
            )

            # კადრის JPEG-ად კოდირება მეხსიერებაში
            _, img_encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            img_bytes = img_encoded.tobytes()

            # სნეფშოტის გაგზავნა
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
                self._last_sent_time = time.time()
                logger.info("Telegram შეტყობინება გაიგზავნა")
            else:
                logger.warning(
                    f"Telegram შეცდომა: {response.status_code} — {response.text}"
                )

        except requests.exceptions.Timeout:
            logger.warning("Telegram timeout — შეტყობინება ვერ გაიგზავნა")
        except requests.exceptions.ConnectionError:
            logger.warning("Telegram კავშირის შეცდომა — ინტერნეტი ხელმისაწვდომია?")
        except Exception as e:
            logger.error(f"Telegram მოულოდნელი შეცდომა: {e}")

    def send_message(self, text):
        """გაუგზავნე მარტივი ტექსტური შეტყობინება."""
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
            logger.error(f"Telegram შეტყობინების შეცდომა: {e}")
