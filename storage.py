import os
import cv2
import shutil
import logging
import logging.handlers
from datetime import datetime
from config import (
    BASE_DIR, LOG_LEVEL, LOG_MAX_BYTES,
    LOG_BACKUP_COUNT, STORAGE_MAX_PERCENT
)

logger = logging.getLogger(__name__)


def setup_logging():
    """სათანადო logging სისტემის კონფიგურაცია rotation-ით."""
    log_path = os.path.join(BASE_DIR, 'logs', 'system.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        log_path,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    root.addHandler(console)
    root.addHandler(file_handler)
    logger.info("Logging სისტემა გაშვებულია")


class StorageManager:

    def __init__(self):
        self.snapshots_dir  = os.path.join(BASE_DIR, 'snapshots')
        self.recordings_dir = os.path.join(BASE_DIR, 'recordings')
        self.logs_dir       = os.path.join(BASE_DIR, 'logs')

        for d in [self.snapshots_dir, self.recordings_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)

    def _timestamp(self):
        return datetime.now().strftime('%Y%m%d_%H%M%S')

    # ── disk management ───────────────────────────────────────────────

    def get_disk_usage_percent(self):
        """დააბრუნე დისკის გამოყენება პროცენტებში."""
        usage = shutil.disk_usage(BASE_DIR)
        return (usage.used / usage.total) * 100

    def cleanup_old_files(self):
        """
        წაშალე ყველაზე ძველი ფაილები სანამ დისკის
        გამოყენება STORAGE_MAX_PERCENT-ზე დაბლა არ ჩამოვა.
        """
        usage = self.get_disk_usage_percent()
        if usage < STORAGE_MAX_PERCENT:
            return

        logger.warning(
            f"დისკი {usage:.1f}% — ძველი ფაილების წაშლა იწყება"
        )

        # შეაგროვე ყველა ფაილი დროის მიხედვით დალაგებული
        all_files = []
        for directory in [self.recordings_dir, self.snapshots_dir]:
            for f in os.listdir(directory):
                path = os.path.join(directory, f)
                if os.path.isfile(path):
                    all_files.append((os.path.getmtime(path), path))

        all_files.sort()  # ყველაზე ძველი პირველი

        deleted = 0
        for _, path in all_files:
            if self.get_disk_usage_percent() < STORAGE_MAX_PERCENT - 5:
                break
            try:
                os.remove(path)
                deleted += 1
                logger.info(f"წაიშალა: {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"წაშლის შეცდომა {path}: {e}")

        logger.info(f"სულ წაიშალა {deleted} ფაილი")

    # ── snapshots ─────────────────────────────────────────────────────

    def save_snapshot(self, frame, detections):
        """შეინახე სნეფშოტი ანოტირებული ფაილის სახელით."""
        self.cleanup_old_files()
        labels   = '_'.join(sorted(set(d['label'] for d in detections)))
        filename = f"{self._timestamp()}_{labels}.jpg"
        filepath = os.path.join(self.snapshots_dir, filename)
        cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        logger.info(f"სნეფშოტი შენახულია: {filename}")
        return filepath

    # ── recordings ────────────────────────────────────────────────────

    def start_recording(self, frame_width, frame_height, fps=10):
        """დაიწყე ახალი ვიდეოჩანაწერი."""
        self.cleanup_old_files()
        filename = f"{self._timestamp()}_recording.avi"
        filepath = os.path.join(self.recordings_dir, filename)
        fourcc   = cv2.VideoWriter_fourcc(*'XVID')
        writer   = cv2.VideoWriter(
            filepath, fourcc, fps, (frame_width, frame_height)
        )
        logger.info(f"ჩაწერა დაიწყო: {filename}")
        return writer, filepath

    def stop_recording(self, writer, filepath):
        """დაასრულე და შეინახე ვიდეოჩანაწერი."""
        writer.release()
        logger.info(f"ჩაწერა დასრულდა: {os.path.basename(filepath)}")

    # ── listing ───────────────────────────────────────────────────────

    def list_snapshots(self):
        """დააბრუნე სნეფშოტების სია — ახლიდან ძველისკენ."""
        files = [
            f for f in os.listdir(self.snapshots_dir)
            if f.endswith('.jpg')
        ]
        return sorted(files, reverse=True)

    def list_recordings(self):
        """დააბრუნე ჩანაწერების სია — ახლიდან ძველისკენ."""
        files = [
            f for f in os.listdir(self.recordings_dir)
            if f.endswith('.avi')
        ]
        return sorted(files, reverse=True)

    def get_stats(self):
        """დააბრუნე სისტემის სტატისტიკა ვებ-ინტერფეისისთვის."""
        usage    = shutil.disk_usage(BASE_DIR)
        used_gb  = usage.used  / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        return {
            'snapshots':   len(self.list_snapshots()),
            'recordings':  len(self.list_recordings()),
            'disk_used_gb':  round(used_gb,  1),
            'disk_total_gb': round(total_gb, 1),
            'disk_percent':  round(self.get_disk_usage_percent(), 1),
        }
