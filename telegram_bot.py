import os
import time
import logging
import threading
import requests
from datetime import datetime
from config import (
    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID, BASE_DIR
)

logger = logging.getLogger(__name__)

COMMANDS = """
🤖 *ბოტის ბრძანებები:*

/status — სისტემის სტატუსი
/snapshot — ბოლო სნეფშოტი
/disk — დისკის გამოყენება
/stop — სისტემის გაჩერება
/start — სისტემის გაშვება
/password <ახალი_პაროლი> — პაროლის შეცვლა
/help — ბრძანებების სია
"""


class TelegramBot:
    """
    Interactive Telegram bot — listens for commands
    and controls the security camera system remotely.
    """

    def __init__(self, storage, camera, motion):
        self.enabled  = TELEGRAM_ENABLED
        self.token    = TELEGRAM_BOT_TOKEN
        self.chat_id  = TELEGRAM_CHAT_ID
        self.storage  = storage
        self.camera   = camera
        self.motion   = motion

        self._running       = False
        self._armed         = True
        self._start_time    = datetime.now()
        self._last_update   = 0
        self._last_text     = ''
        self._poll_interval = 2

        if self.enabled and (not self.token or not self.chat_id):
            logger.warning(
                "Telegram bot enabled but BOT_TOKEN or CHAT_ID missing — disabled"
            )
            self.enabled = False

    # ── Polling ───────────────────────────────────────────────────────

    def start(self):
        """Start the bot polling loop in a background thread."""
        if not self.enabled:
            return
        self._running = True
        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()
        logger.info("Telegram bot started — listening for commands")

    def stop(self):
        """Stop the polling loop."""
        self._running = False

    def _poll_loop(self):
        """Long-poll Telegram for new messages."""
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except requests.exceptions.ConnectionError:
                logger.warning("Telegram bot — connection error, retrying...")
                time.sleep(10)
            except Exception as e:
                logger.error(f"Telegram bot poll error: {e}")
                time.sleep(5)
            time.sleep(self._poll_interval)

    def _get_updates(self):
        """Fetch new updates from Telegram."""
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        response = requests.get(
            url,
            params={
                'offset':  self._last_update + 1,
                'timeout': 10
            },
            timeout=15
        )
        data = response.json()
        if not data.get('ok'):
            return []
        updates = data.get('result', [])
        if updates:
            self._last_update = updates[-1]['update_id']
        return updates

    def _handle_update(self, update):
        """Route incoming message to the correct command handler."""
        message = update.get('message', {})
        chat_id = str(message.get('chat', {}).get('id', ''))
        text    = message.get('text', '').strip()

        # Only respond to authorized chat
        if chat_id != str(self.chat_id):
            logger.warning(f"Unauthorized access attempt from chat_id: {chat_id}")
            return

        self._last_text = text
        cmd = text.split()[0].lower() if text else ''

        logger.info(f"Bot command received: {cmd}")

        handlers = {
            '/start':    self._cmd_start,
            '/stop':     self._cmd_stop,
            '/status':   self._cmd_status,
            '/snapshot': self._cmd_snapshot,
            '/disk':     self._cmd_disk,
            '/help':     self._cmd_help,
            '/password': self._cmd_password,
        }

        handler = handlers.get(cmd)
        if handler:
            handler()
        elif text:
            self._send(
                "❓ უცნობი ბრძანება. გამოიყენე /help ბრძანებების სანახავად."
            )

    # ── Command implementations ───────────────────────────────────────

    def _cmd_help(self):
        self._send(COMMANDS)

    def _cmd_status(self):
        uptime  = datetime.now() - self._start_time
        hours   = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        stats   = self.storage.get_stats()
        armed   = "✅ ჩართული" if self._armed else "⏸ გაჩერებული"

        msg = (
            f"📊 *სისტემის სტატუსი*\n\n"
            f"🔒 სტატუსი: {armed}\n"
            f"⏱ მუშაობის დრო: {hours}სთ {minutes}წთ\n"
            f"📸 სნეფშოტები: {stats['snapshots']}\n"
            f"🎥 ჩანაწერები: {stats['recordings']}\n"
            f"💾 დისკი: {stats['disk_percent']}% "
            f"({stats['disk_used_gb']}/{stats['disk_total_gb']} გბ)\n"
            f"🎬 ჩაწერა: {'🔴 მიმდინარეობს' if self.camera.is_recording else '⏹ არ მიმდინარეობს'}"
        )
        self._send(msg)

    def _cmd_snapshot(self):
        """Send the most recent saved snapshot."""
        snapshots = self.storage.list_snapshots()
        if not snapshots:
            self._send("📭 სნეფშოტები ჯერ არ არის.")
            return

        latest   = snapshots[0]
        filepath = os.path.join(self.storage.snapshots_dir, latest)

        try:
            with open(filepath, 'rb') as f:
                img_bytes = f.read()

            parts    = latest.replace('.jpg', '').split('_')
            label    = parts[2] if len(parts) > 2 else 'უცნობი'
            t        = parts[1] if len(parts) > 1 else ''
            time_str = f"{t[:2]}:{t[2:4]}:{t[4:6]}" if len(t) >= 6 else ''
            caption  = f"📸 *ბოლო სნეფშოტი*\n🏷 {label}\n🕐 {time_str}"

            url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
            requests.post(
                url,
                data={
                    'chat_id':    self.chat_id,
                    'caption':    caption,
                    'parse_mode': 'Markdown'
                },
                files={'photo': ('snapshot.jpg', img_bytes, 'image/jpeg')},
                timeout=15
            )
        except Exception as e:
            logger.error(f"Snapshot send error: {e}")
            self._send(f"❌ სნეფშოტის გაგზავნა ვერ მოხერხდა: {e}")

    def _cmd_disk(self):
        stats       = self.storage.get_stats()
        pct         = stats['disk_percent']
        icon        = "🔴" if pct > 85 else "🟡" if pct > 70 else "🟢"
        bar_filled  = int(pct / 10)
        bar         = "█" * bar_filled + "░" * (10 - bar_filled)

        msg = (
            f"💾 *დისკის სტატუსი*\n\n"
            f"{icon} გამოყენება: {pct}%\n"
            f"`{bar}` {pct}%\n"
            f"გამოყენებულია: {stats['disk_used_gb']} გბ\n"
            f"სულ: {stats['disk_total_gb']} გბ\n\n"
            f"📸 სნეფშოტები: {stats['snapshots']}\n"
            f"🎥 ჩანაწერები: {stats['recordings']}"
        )
        self._send(msg)

    def _cmd_stop(self):
        """Disarm — pause detection."""
        if not self._armed:
            self._send("⏸ სისტემა უკვე გაჩერებულია.")
            return
        self._armed = False
        self.motion.reset()
        self._send(
            "⏸ *დეტექტირება გაჩერებულია*\n"
            "გასაგრძელებლად გამოიყენე /start"
        )
        logger.info("System disarmed via Telegram")

    def _cmd_start(self):
        """Rearm — resume detection."""
        if self._armed:
            self._send("✅ სისტემა უკვე ჩართულია.")
            return
        self._armed = True
        self.motion.reset()
        self._send("✅ *დეტექტირება განახლდა*")
        logger.info("System rearmed via Telegram")

    def _cmd_password(self):
        """Change the web interface password."""
        from auth import change_password
        parts = self._last_text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            self._send(
                "⚠️ გამოყენება: `/password ახალი_პაროლი`\n\n"
                "მოთხოვნები:\n"
                "• მინიმუმ 8 სიმბოლო\n"
                "• მინიმუმ ერთი დიდი ასო\n"
                "• მინიმუმ ერთი პატარა ასო\n"
                "• მინიმუმ ერთი ციფრი\n"
                "• მინიმუმ ერთი სპეციალური სიმბოლო"
            )
            return

        new_password = parts[1].strip()
        success, message = change_password('admin', new_password)

        if success:
            self._send(f"✅ *{message}*\nახალი პაროლი ძალაშია.")
            logger.info("Password changed via Telegram bot")
        else:
            self._send(f"❌ *შეცდომა:* {message}")

    @property
    def armed(self):
        return self._armed

    # ── Helpers ───────────────────────────────────────────────────────

    def _send(self, text):
        """Send a text message to the authorized chat."""
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
            logger.error(f"Telegram send error: {e}")

