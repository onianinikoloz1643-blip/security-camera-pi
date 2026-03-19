import os
import time
import logging
import threading

from config import (
    MODEL_PATH, LABEL_PATH, BASE_DIR,
    FRAME_WIDTH, FRAME_HEIGHT, FPS,
    DETECTION_THRESHOLD, RECORDING_COOLDOWN, SNAPSHOT_INTERVAL,
    MOTION_ENABLED, WEB_HOST, WEB_PORT
)
from storage import StorageManager, setup_logging
from detector import ObjectDetector
from camera import Camera
from motion import MotionDetector
from telegram_notify import TelegramNotifier
from web import start_web, push_event

logger = logging.getLogger(__name__)


def run_camera_loop(camera, detector, motion, storage, notifier):
    """მთავარი ციკლი: გადაღება → მოძრაობა → დეტექტირება → შენახვა."""

    last_detection_time = 0
    last_snapshot_time  = 0
    motion_skip_count   = 0

    logger.info("კამერის ციკლი დაიწყო")

    while True:
        try:
            frame = camera.capture_frame()
            now   = time.time()

            # ── მოძრაობის ფილტრი ─────────────────────────────────────
            if MOTION_ENABLED:
                motion_detected, motion_score = motion.detect(frame)
                if not motion_detected:
                    motion_skip_count += 1
                    # ყოველ 100 გამოტოვებულ კადრზე ერთხელ ჩაწერე
                    if motion_skip_count % 100 == 0:
                        logger.debug(
                            f"მოძრაობა არ არის — {motion_skip_count} კადრი გამოტოვდა"
                        )
                    # თუ ჩაწერა მიმდინარეობს, კადრი მაინც ჩაიწეროს
                    if camera.is_recording:
                        camera.write_frame(frame)
                    time.sleep(1.0 / FPS)
                    continue

                motion_skip_count = 0

            # ── ML დეტექტირება ────────────────────────────────────────
            detections = detector.detect(frame)

            if detections:
                labels = [d['label'] for d in detections]
                scores = [d['score'] for d in detections]
                logger.info(
                    f"დეტექტირება: {list(zip(labels, [f'{s:.0%}' for s in scores]))}"
                )

                annotated = camera.draw_detections(frame.copy(), detections)

                # სნეფშოტი (rate limited)
                if now - last_snapshot_time >= SNAPSHOT_INTERVAL:
                    filepath = storage.save_snapshot(annotated, detections)
                    filename = os.path.basename(filepath)

                    # SSE — snapshot event
                    push_event('snapshot', {
                        'filename': filename,
                        'total':    len(storage.list_snapshots())
                    })
                    last_snapshot_time = now

                # SSE — detection event
                push_event('detection', {'labels': list(set(labels))})

                # Telegram შეტყობინება
                notifier.send_detection(annotated, detections)

                # ჩაწერის დაწყება
                if not camera.is_recording:
                    camera.start_recording(storage)
                    push_event('recording_start', {})

                last_detection_time = now

            else:
                # cooldown-ის შემდეგ ჩაწერის შეწყვეტა
                if camera.is_recording:
                    if now - last_detection_time >= RECORDING_COOLDOWN:
                        camera.stop_recording(storage)
                        push_event('recording_stop', {
                            'total': len(storage.list_recordings())
                        })

            # კადრის ჩაწერა
            if camera.is_recording:
                camera.write_frame(frame)

            # SSE — disk update (ყოველ 60 წამში)
            if int(now) % 60 == 0:
                stats = storage.get_stats()
                push_event('disk', {'percent': stats['disk_percent']})

            time.sleep(1.0 / FPS)

        except Exception as e:
            logger.error(f"კამერის ციკლის შეცდომა: {e}", exc_info=True)
            time.sleep(2)


def main():
    # Logging-ის ინიციალიზაცია
    setup_logging()
    logger.info("=" * 50)
    logger.info("უსაფრთხოების კამერის სისტემა იტვირთება...")
    logger.info("=" * 50)

    # კომპონენტების ინიციალიზაცია
    try:
        storage  = StorageManager()
        detector = ObjectDetector(MODEL_PATH, LABEL_PATH, DETECTION_THRESHOLD)
        camera   = Camera(FRAME_WIDTH, FRAME_HEIGHT, FPS)
        motion   = MotionDetector()
        notifier = TelegramNotifier()
    except Exception as e:
        logger.critical(f"ინიციალიზაციის შეცდომა: {e}", exc_info=True)
        return

    # ვებ-სერვერი ფონურ ნაკადში
    web_thread = threading.Thread(
        target=start_web,
        args=(storage,),
        daemon=True
    )
    web_thread.start()
    logger.info(f"ვებ-ინტერფეისი: http://raspberrypi.local:{WEB_PORT}")

    # Telegram — გაშვების შეტყობინება
    notifier.send_message("✅ *უსაფრთხოების კამერა გაეშვა*")

    # კამერის გაშვება
    try:
        camera.start()
    except Exception as e:
        logger.critical(f"კამერის გაშვების შეცდომა: {e}", exc_info=True)
        notifier.send_message("❌ *კამერის გაშვება ვერ მოხერხდა*")
        return

    logger.info("სისტემა მზადაა — დეტექტირება იწყება")

    try:
        run_camera_loop(camera, detector, motion, storage, notifier)
    except KeyboardInterrupt:
        logger.info("გამორთვა — Ctrl+C")
    except Exception as e:
        logger.critical(f"კრიტიკული შეცდომა: {e}", exc_info=True)
        notifier.send_message(f"❌ *სისტემა ავარიულად გამოირთო:* {e}")
    finally:
        logger.info("სისტემა ითიშება...")
        if camera.is_recording:
            camera.stop_recording(storage)
        camera.stop()
        notifier.send_message("🔴 *უსაფრთხოების კამერა გამოირთო*")
        logger.info("სისტემა გამოირთო")


if __name__ == '__main__':
    main()
