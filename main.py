import os
import time
import logging
import threading

from config import (
    RECORDING_COOLDOWN,
    MOTION_ENABLED, WEB_PORT, FPS
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
    last_disk_update    = 0
    motion_skip_count   = 0

    logger.info("Camera loop started")

    while True:
        try:
            frame = camera.capture_frame()
            now   = time.time()

            if not bot.armed:
                if camera.is_recording:
                    camera.stop_recording(storage)
                    push_event('recording_stop', {
                        'total': len(storage.list_recordings())
                    })
                if now - last_disk_update >= 60:
                    stats = storage.get_stats()
                    push_event('disk', {'percent': stats['disk_percent']})
                    last_disk_update = now
                time.sleep(1.0 / FPS)
                continue

            # ── Motion filter ─────────────────────────────────────────
            if MOTION_ENABLED:
                motion_detected, _ = motion.detect(frame)
                if not motion_detected:
                    motion_skip_count += 1
                    if motion_skip_count % 100 == 0:
                        logger.debug(
                            f"No motion — {motion_skip_count} frames skipped"
                        )
                    # Still write frame if recording is active
                    if camera.is_recording:
                        camera.write_frame(frame, storage)
                    time.sleep(1.0 / FPS)
                    continue

                motion_skip_count = 0

            # ── ML Detection ──────────────────────────────────────────
            detections = detector.detect(frame)

            if detections:
                labels = [d['label'] for d in detections]
                scores = [d['score'] for d in detections]
                logger.info(
                    f"Detected: "
                    f"{list(zip(labels, [f'{s:.0%}' for s in scores]))}"
                )

                # SSE detection event (live toast, every frame)
                push_event('detection', {'labels': list(set(labels))})

                # New event: person appeared after an idle gap. Save ONE
                # snapshot and start the clip with a SHARED timestamp (so the
                # clip pairs with its snapshot), then send ONE alert.
                if not camera.is_recording:
                    annotated = camera.draw_detections(frame.copy(), detections)
                    event_ts  = storage.timestamp()

                    filepath = storage.save_snapshot(
                        annotated, detections, timestamp=event_ts
                    )
                    push_event('snapshot', {
                        'filename': os.path.basename(filepath),
                        'total':    len(storage.list_snapshots())
                    })

                    camera.start_recording(storage, timestamp=event_ts)
                    push_event('recording_start', {})

                    # Sent last: the Telegram POST can block, and we don't want
                    # it to delay the snapshot or the start of the recording.
                    notifier.send_detection(annotated, detections)

                last_detection_time = now

            else:
                # Stop recording after cooldown with no detections
                if camera.is_recording:
                    if now - last_detection_time >= RECORDING_COOLDOWN:
                        camera.stop_recording(storage)
                        push_event('recording_stop', {
                            'total': len(storage.list_recordings())
                        })

            # Write frame to active recording
            if camera.is_recording:
                camera.write_frame(frame, storage)

            # ── Disk update — reliable timer ──────────────────────────
            if now - last_disk_update >= 60:
                stats = storage.get_stats()
                push_event('disk', {'percent': stats['disk_percent']})
                last_disk_update = now

            time.sleep(1.0 / FPS)

        except Exception as e:
            logger.error(f"Camera loop error: {e}", exc_info=True)
            time.sleep(2)


def main():
    # Initialize logging
    setup_logging()
    logger.info("=" * 50)
    logger.info("Security camera system starting...")
    logger.info("=" * 50)

    # Validate config before anything else
    try:
        from config import validate_config
        validate_config()
        logger.info("Configuration validated OK")
    except ValueError as e:
        logger.critical(f"Invalid configuration:\n{e}")
        return

    # Initialize all components
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
    logger.info(f"Web interface: https://raspberrypi.local:{WEB_PORT}")

    # Telegram startup message and bot
    notifier.send_message("*Security camera started*")
    bot.start()

    # Start camera
    try:
        camera.start()
    except RuntimeError as e:
        logger.critical(f"Camera start failed: {e}")
        notifier.send_message(f"*Camera failed to start:* {e}")
        return

    logger.info("System ready — detection starting")

    try:
        run_camera_loop(camera, detector, motion, storage, notifier, bot)
    except KeyboardInterrupt:
        logger.info("Shutdown — Ctrl+C")
    except Exception as e:
        logger.critical(f"Critical error: {e}", exc_info=True)
        notifier.send_message(f"*System crashed:* {e}")
    finally:
        logger.info("Shutting down...")
        if camera.is_recording:
            camera.stop_recording(storage)
        camera.stop()
        bot.stop()
        notifier.send_message("*Security camera stopped*")
        logger.info("System stopped cleanly")


if __name__ == '__main__':
    main()
