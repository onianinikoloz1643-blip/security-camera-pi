"""
Full system test without a real camera.
Uses MockCamera to simulate live feed from test_image.jpg.
Run: python test_system.py
Open browser: https://raspberrypi.local:8080
Stop: Ctrl+C
"""
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
from motion import MotionDetector
from telegram_notify import TelegramNotifier
from telegram_bot import TelegramBot
from web import start_web, push_event
from mock_camera import MockCamera


logger = logging.getLogger(__name__)


def run_camera_loop(camera, detector, motion, storage, notifier, bot):
    last_detection_time = 0
    last_disk_update    = 0
    motion_skip_count   = 0

    logger.info("Test loop started — using MockCamera")

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

            if MOTION_ENABLED:
                motion_detected, _ = motion.detect(frame)
                if not motion_detected:
                    motion_skip_count += 1
                    if camera.is_recording:
                        camera.write_frame(frame, storage)
                    time.sleep(1.0 / FPS)
                    continue
                motion_skip_count = 0

            detections = detector.detect(frame)

            if detections:
                labels = [d['label'] for d in detections]
                scores = [d['score'] for d in detections]
                logger.info(
                    f"Detected: {list(zip(labels, [f'{s:.0%}' for s in scores]))}"
                )

                push_event('detection', {'labels': list(set(labels))})

                if not camera.is_recording:
                    annotated = camera.draw_detections(frame.copy(), detections)

                    filepath = storage.save_snapshot(annotated, detections)
                    push_event('snapshot', {
                        'filename': os.path.basename(filepath),
                        'total':    len(storage.list_snapshots())
                    })

                    notifier.send_detection(annotated, detections)

                    camera.start_recording(storage)
                    push_event('recording_start', {})

                last_detection_time = now

            else:
                if camera.is_recording:
                    if now - last_detection_time >= RECORDING_COOLDOWN:
                        camera.stop_recording(storage)
                        push_event('recording_stop', {
                            'total': len(storage.list_recordings())
                        })

            if camera.is_recording:
                camera.write_frame(frame, storage)

            if now - last_disk_update >= 60:
                stats = storage.get_stats()
                push_event('disk', {'percent': stats['disk_percent']})
                last_disk_update = now

            time.sleep(1.0 / FPS)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error(f"Loop error: {e}", exc_info=True)
            time.sleep(2)


def main():
    setup_logging()
    logger.info("=" * 50)
    logger.info("SYSTEM TEST — MockCamera mode")
    logger.info("=" * 50)

    storage  = StorageManager()
    detector = ObjectDetector()
    camera   = MockCamera()
    motion   = MotionDetector()
    notifier = TelegramNotifier()
    bot      = TelegramBot(storage, camera, motion)

    web_thread = threading.Thread(
        target=start_web, args=(storage,), daemon=True
    )
    web_thread.start()
    logger.info(f"Web interface: https://raspberrypi.local:{WEB_PORT}")
    logger.info("Open your browser and log in with your credentials")

    bot.start()
    camera.start()

    logger.info("Running — press Ctrl+C to stop")

    try:
        run_camera_loop(camera, detector, motion, storage, notifier, bot)
    except KeyboardInterrupt:
        logger.info("Stopping test...")
    finally:
        if camera.is_recording:
            camera.stop_recording(storage)
        camera.stop()
        bot.stop()
        logger.info("Test stopped cleanly")


if __name__ == '__main__':
    main()

