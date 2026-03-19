import os
import time
import logging
import threading

from config import (
    BASE_DIR, RECORDING_COOLDOWN, SNAPSHOT_INTERVAL,
    MOTION_ENABLED, WEB_PORT
)
from storage import StorageManager, setup_logging
from detector import ObjectDetector
from camera import Camera
from motion import MotionDetector
from telegram_notify import TelegramNotifier
from telegram_bot import TelegramBot
from web import start_web, push_event

logger = logging.getLogger(__name__)


def run_camera_loop(camera, detector, motion, storage, notifier, bot):
    """Main loop: capture → motion → detect → store."""

    last_detection_time = 0
    last_snapshot_time  = 0
    motion_skip_count   = 0

    logger.info("Camera loop started")

    while True:
        try:
            frame = camera.capture_frame()
            now   = time.time()

            # ── Motion filter ─────────────────────────────────────────
            if MOTION_ENABLED:
                motion_detected, motion_score = motion.detect(frame)
                if not motion_detected:
                    motion_skip_count += 1
                    if motion_skip_count % 100 == 0:
                        logger.debug(
                            f"No motion — {motion_skip_count} frames skipped"
                        )
                    if camera.is_recording:
                        camera.write_frame(frame)
                    time.sleep(1.0 / 10)
                    continue

                motion_skip_count = 0

            # ── ML Detection ──────────────────────────────────────────
            if not bot.armed:
                time.sleep(1.0 / 10)
                continue

            detections = detector.detect(frame)

            if detections:
                labels = [d['label'] for d in detections]
                scores = [d['score'] for d in detections]
                logger.info(
                    f"Detected: {list(zip(labels, [f'{s:.0%}' for s in scores]))}"
                )

                annotated = camera.draw_detections(frame.copy(), detections)

                # Snapshot (rate limited)
                if now - last_snapshot_time >= SNAPSHOT_INTERVAL:
                    filepath = storage.save_snapshot(annotated, detections)
                    filename = os.path.basename(filepath)
                    push_event('snapshot', {
                        'filename': filename,
                        'total':    len(storage.list_snapshots())
                    })
                    last_snapshot_time = now

                # SSE detection event
                push_event('detection', {'labels': list(set(labels))})

                # Telegram alert
                notifier.send_detection(annotated, detections)

                # Start recording if not already
                if not camera.is_recording:
                    camera.start_recording(storage)
                    push_event('recording_start', {})

                last_detection_time = now

            else:
                # Stop recording after cooldown
                if camera.is_recording:
                    if now - last_detection_time >= RECORDING_COOLDOWN:
                        camera.stop_recording(storage)
                        push_event('recording_stop', {
                            'total': len(storage.list_recordings())
                        })

            # Write frame to active recording
            if camera.is_recording:
                camera.write_frame(frame)

            # SSE disk update every 60 seconds
            if int(now) % 60 == 0:
                stats = storage.get_stats()
                push_event('disk', {'percent': stats['disk_percent']})

            time.sleep(1.0 / 10)

        except Exception as e:
            logger.error(f"Camera loop error: {e}", exc_info=True)
            time.sleep(2)


def main():
    # Initialize logging
    setup_logging()
    logger.info("=" * 50)
    logger.info("Security camera system starting...")
    logger.info("=" * 50)

    # Initialize components
    try:
        storage  = StorageManager()
        detector = ObjectDetector()
        camera   = Camera()
        motion   = MotionDetector()
        notifier = TelegramNotifier()
        bot      = TelegramBot(storage, camera, motion)
    except Exception as e:
        logger.critical(f"Initialization error: {e}", exc_info=True)
        return

    # Start web server in background thread
    web_thread = threading.Thread(
        target=start_web,
        args=(storage,),
        daemon=True
    )
    web_thread.start()
    logger.info(f"Web interface: http://raspberrypi.local:{WEB_PORT}")

    # Telegram startup message and bot
    notifier.send_message("✅ *Security camera started*")
    bot.start()

    # Start camera
    try:
        camera.start()
    except RuntimeError as e:
        logger.critical(f"Camera start failed: {e}")
        notifier.send_message(f"❌ *Camera failed to start:* {e}")
        return

    logger.info("System ready — detection starting")

    try:
        run_camera_loop(camera, detector, motion, storage, notifier, bot)
    except KeyboardInterrupt:
        logger.info("Shutdown — Ctrl+C")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        notifier.send_message(f"❌ *System crashed:* {e}")
    finally:
        logger.info("Shutting down...")
        if camera.is_recording:
            camera.stop_recording(storage)
        camera.stop()
        bot.stop()
        notifier.send_message("🔴 *Security camera stopped*")
        logger.info("System stopped cleanly")


if __name__ == '__main__':
    main()
