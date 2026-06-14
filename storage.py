import os
import cv2
import shutil
import logging
import logging.handlers
from datetime import datetime
from config import (
    BASE_DIR, LOG_LEVEL, LOG_MAX_BYTES,
    LOG_BACKUP_COUNT, STORAGE_MAX_PERCENT,
    MAX_RECORDING_SECONDS
)

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure rotating file + console logging."""
    log_path = os.path.join(BASE_DIR, 'logs', 'system.log')
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

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
    logger.info("Logging system started")


class StorageManager:

    def __init__(self):
        self.snapshots_dir  = os.path.join(BASE_DIR, 'snapshots')
        self.recordings_dir = os.path.join(BASE_DIR, 'recordings')
        self.logs_dir       = os.path.join(BASE_DIR, 'logs')
        self._active_recordings = set()

        for d in [self.snapshots_dir, self.recordings_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)

    def _timestamp(self):
        return datetime.now().strftime('%Y%m%d_%H%M%S')

    # ── Disk management ───────────────────────────────────────────────

    def get_disk_usage_percent(self):
        usage = shutil.disk_usage(BASE_DIR)
        return (usage.used / usage.total) * 100

    def cleanup_old_files(self):
        """Delete oldest files until disk usage is below threshold."""
        usage = self.get_disk_usage_percent()
        if usage < STORAGE_MAX_PERCENT:
            return

        logger.warning(f"Disk at {usage:.1f}% — cleaning up old files")

        all_files = []
        for directory in [self.recordings_dir, self.snapshots_dir]:
            for f in os.listdir(directory):
                path = os.path.join(directory, f)
                if os.path.isfile(path) and path not in self._active_recordings:
                    all_files.append((os.path.getmtime(path), path))

        all_files.sort()  # oldest first

        deleted = 0
        for _, path in all_files:
            if self.get_disk_usage_percent() < STORAGE_MAX_PERCENT - 5:
                break
            try:
                os.remove(path)
                deleted += 1
                logger.info(f"Deleted: {os.path.basename(path)}")
            except Exception as e:
                logger.error(f"Delete error {path}: {e}")

        if self.get_disk_usage_percent() >= STORAGE_MAX_PERCENT:
            logger.warning(
                "Cleanup finished but disk is still above threshold. "
                "Manual cleanup may be required."
            )
        logger.info(f"Cleanup complete — {deleted} files deleted")

    # ── Snapshots ─────────────────────────────────────────────────────

    def save_snapshot(self, frame, detections):
        """Save annotated snapshot with detection labels in filename."""
        self.cleanup_old_files()
        labels   = '_'.join(sorted(set(d['label'] for d in detections)))
        filename = f"{self._timestamp()}_{labels}.jpg"
        filepath = os.path.join(self.snapshots_dir, filename)
        saved = cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not saved:
            raise RuntimeError(f"Snapshot write failed: {filepath}")
        logger.info(f"Snapshot saved: {filename}")
        return filepath

    # ── Recordings ────────────────────────────────────────────────────

    def start_recording(self, frame_width, frame_height, fps=10):
        """Start a new video recording. Returns (writer, filepath, start_time)."""
        self.cleanup_old_files()
        filename  = f"{self._timestamp()}_recording.avi"
        filepath  = os.path.join(self.recordings_dir, filename)
        fourcc    = cv2.VideoWriter_fourcc(*'XVID')
        writer    = cv2.VideoWriter(
            filepath, fourcc, fps, (frame_width, frame_height)
        )
        if not writer.isOpened():
            writer.release()
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            raise RuntimeError(f"Recording writer could not open: {filepath}")
        start_time = datetime.now()
        self._active_recordings.add(filepath)
        logger.info(f"Recording started: {filename}")
        return writer, filepath, start_time

    def stop_recording(self, writer, filepath):
        """Stop and finalise a video recording."""
        if writer is None or filepath is None:
            return

        try:
            writer.release()
        finally:
            self._active_recordings.discard(filepath)

        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 ** 2)
            logger.info(
                f"Recording stopped: {os.path.basename(filepath)} "
                f"({size_mb:.1f} MB)"
            )
        else:
            logger.warning(
                f"Recording stopped but file is missing: {filepath}"
            )

    def should_split_recording(self, start_time):
        """
        Returns True if the current recording has exceeded
        MAX_RECORDING_SECONDS and should be split into a new file.
        """
        elapsed = (datetime.now() - start_time).total_seconds()
        return elapsed >= MAX_RECORDING_SECONDS

    # ── Listing ───────────────────────────────────────────────────────

    def list_snapshots(self):
        files = [
            f for f in os.listdir(self.snapshots_dir)
            if f.endswith('.jpg')
        ]
        return sorted(files, reverse=True)

    def list_recordings(self):
        files = [
            f for f in os.listdir(self.recordings_dir)
            if f.endswith('.avi')
        ]
        return sorted(files, reverse=True)

    def get_stats(self):
        """Return system stats for web interface and Telegram bot."""
        usage    = shutil.disk_usage(BASE_DIR)
        used_gb  = usage.used  / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        return {
            'snapshots':     len(self.list_snapshots()),
            'recordings':    len(self.list_recordings()),
            'disk_used_gb':  round(used_gb,  1),
            'disk_total_gb': round(total_gb, 1),
            'disk_percent':  round(self.get_disk_usage_percent(), 1),
        }
