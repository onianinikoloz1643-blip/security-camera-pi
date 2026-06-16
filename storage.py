import os
import cv2
import shutil
import logging
import logging.handlers
import subprocess
import threading
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

    def timestamp(self):
        """Public timestamp (YYYYMMDD_HHMMSS) so one event can share it
        between its snapshot and its recording."""
        return self._timestamp()

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

    def save_snapshot(self, frame, detections, timestamp=None):
        """Save annotated snapshot with detection labels in filename."""
        self.cleanup_old_files()
        ts       = timestamp or self._timestamp()
        labels   = '_'.join(sorted(set(d['label'] for d in detections)))
        filename = f"{ts}_{labels}.jpg"
        filepath = os.path.join(self.snapshots_dir, filename)
        saved = cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not saved:
            raise RuntimeError(f"Snapshot write failed: {filepath}")
        logger.info(f"Snapshot saved: {filename}")
        return filepath

    # ── Recordings ────────────────────────────────────────────────────

    def start_recording(self, frame_width, frame_height, fps=10, timestamp=None):
        """Start a new video recording. Returns (writer, filepath, start_time)."""
        self.cleanup_old_files()
        ts        = timestamp or self._timestamp()
        filename  = f"{ts}_recording.avi"
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
            # Convert to MP4 in the background so it plays in the browser and
            # in Telegram. Keeps the AVI if ffmpeg is missing or the run fails.
            threading.Thread(
                target=self._transcode_to_mp4,
                args=(filepath,),
                daemon=True
            ).start()
        else:
            logger.warning(
                f"Recording stopped but file is missing: {filepath}"
            )

    def _transcode_to_mp4(self, avi_path):
        """Convert a finished AVI clip to H.264 MP4, then delete the AVI.
        On any failure (including ffmpeg not installed) the AVI is kept."""
        mp4_path = os.path.splitext(avi_path)[0] + '.mp4'
        tmp_path = mp4_path + '.tmp'
        try:
            result = subprocess.run(
                ['ffmpeg', '-y', '-i', avi_path,
                 '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                 '-threads', '2', '-movflags', '+faststart', tmp_path],
                capture_output=True, timeout=600
            )
            if result.returncode == 0 and os.path.exists(tmp_path):
                os.replace(tmp_path, mp4_path)
                os.remove(avi_path)
                logger.info(f"Converted to MP4: {os.path.basename(mp4_path)}")
            else:
                logger.warning(
                    f"MP4 conversion failed for {os.path.basename(avi_path)} "
                    f"— keeping AVI"
                )
                self._remove_quiet(tmp_path)
        except FileNotFoundError:
            logger.warning(
                "ffmpeg not found — keeping AVI. Install with: "
                "sudo apt install ffmpeg"
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"MP4 conversion timed out for {os.path.basename(avi_path)} "
                f"— keeping AVI"
            )
            self._remove_quiet(tmp_path)
        except Exception as e:
            logger.error(f"MP4 conversion error: {e}")
            self._remove_quiet(tmp_path)

    @staticmethod
    def _remove_quiet(path):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

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
            if f.endswith('.mp4') or f.endswith('.avi')
        ]
        return sorted(files, reverse=True)

    def list_recordings_with_thumbs(self):
        """Recordings newest-first, each paired with the event snapshot that
        shares its timestamp prefix (YYYYMMDD_HHMMSS) for use as a thumbnail."""
        snap_by_ts = {}
        for s in self.list_snapshots():
            ts = '_'.join(s.split('_')[:2])
            snap_by_ts.setdefault(ts, s)
        result = []
        for rec in self.list_recordings():
            ts = '_'.join(rec.split('_')[:2])
            result.append({'file': rec, 'thumb': snap_by_ts.get(ts)})
        return result

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
