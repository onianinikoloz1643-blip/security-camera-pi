import os
import time
import logging
import threading

from config import (
    RECORDING_COOLDOWN, PRESENCE_CHECK_INTERVAL,
    MOTION_ENABLED, WEB_PORT, FPS
)
from storage import StorageManager, setup_logging
from detector import ObjectDetector
from camera import Camera
from motion import MotionDetector
from telegram_notify import TelegramNotifier
from telegram_bot import TelegramBot
from web import start_web, push_event
from heartbeat import start_heartbeat

logger = logging.getLogger(__name__)


def run_camera_loop(camera, detector, motion, storage, notifier, bot):
    """Main loop: capture → motion → detect → store."""

    last_activity_time  = 0
    last_presence_check = 0
    last_disk_update    = 0

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

            # ── Motion filter: gate the expensive detection ───────────
            motion_detected = True
            if MOTION_ENABLED:
                motion_detected, _ = motion.detect(frame)

            # run detection on motion; while recording, also re-check every so
            # often even with no motion, so a person who stops moving but stays
            # in frame keeps the clip alive until they actually leave
            check_presence = (
                camera.is_recording
                and now - last_presence_check >= PRESENCE_CHECK_INTERVAL
            )
            if motion_detected or check_presence:
                detections = detector.detect(frame)
                last_presence_check = now
            else:
                detections = []

            # motion or a detection keeps the clip alive
            if motion_detected or detections:
                last_activity_time = now

            if detections:
                labels = [d['label'] for d in detections]
                scores = [d['score'] for d in detections]
                logger.info(
                    f"Detected: "
                    f"{list(zip(labels, [f'{s:.0%}' for s in scores]))}"
                )
                push_event('detection', {'labels': list(set(labels))})

                # new object in view: one snapshot + one alert + start the clip
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

                    # send last, the Telegram upload can block for a moment
                    notifier.send_detection(annotated, detections)

            # stop once nothing has moved for the cooldown
            if camera.is_recording and now - last_activity_time >= RECORDING_COOLDOWN:
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
    start_heartbeat()

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
