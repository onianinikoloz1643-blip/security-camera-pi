import cv2
import logging
from config import FRAME_WIDTH, FRAME_HEIGHT, FPS

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self):
        self.width  = FRAME_WIDTH
        self.height = FRAME_HEIGHT
        self.fps    = FPS
        self.picam  = None
        self._recording_writer = None
        self._recording_path   = None
        self._is_recording     = False

    def start(self):
        """Initialize and start the camera with graceful error handling."""
        try:
            from picamera2 import Picamera2
        except ImportError:
            raise RuntimeError(
                "picamera2 არ არის დაინსტალირებული. "
                "გაუშვი: sudo apt install python3-picamera2"
            )

        try:
            self.picam = Picamera2()
        except Exception as e:
            raise RuntimeError(
                f"კამერის ინიციალიზაცია ვერ მოხერხდა. "
                f"დარწმუნდი რომ კამერა მიერთებულია და "
                f"config.txt სწორად არის კონფიგურირებული.\n"
                f"დეტალი: {e}"
            )

        try:
            config = self.picam.create_video_configuration(
                main={"format": "RGB888", "size": (self.width, self.height)},
                controls={"FrameRate": self.fps}
            )
            self.picam.configure(config)
            self.picam.start()
            logger.info(
                f"კამერა გაეშვა — {self.width}x{self.height} @ {self.fps}fps"
            )
        except Exception as e:
            self.picam = None
            raise RuntimeError(
                f"კამერის კონფიგურაცია ვერ მოხერხდა: {e}"
            )

    def stop(self):
        """Stop the camera safely."""
        if self.picam:
            try:
                self.picam.stop()
                logger.info("კამერა გამოირთო")
            except Exception as e:
                logger.warning(f"კამერის გამორთვის შეცდომა: {e}")
            finally:
                self.picam = None

    def capture_frame(self):
        """Capture a single frame and return as BGR numpy array."""
        if not self.picam:
            raise RuntimeError(
                "კამერა არ არის გაშვებული — გამოიძახე start() პირველ რიგში"
            )
        try:
            import numpy as np
            frame_rgb = self.picam.capture_array()
            return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        except Exception as e:
            raise RuntimeError(f"კადრის გადაღების შეცდომა: {e}")

    def draw_detections(self, frame, detections):
        """Draw bounding boxes and labels on frame."""
        h, w = frame.shape[:2]
        for det in detections:
            label = det['label']
            score = det['score']
            ymin, xmin, ymax, xmax = det['box']

            x1, y1 = int(xmin * w), int(ymin * h)
            x2, y2 = int(xmax * w), int(ymax * h)

            color = (0, 0, 255) if label == 'person' else (255, 100, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            text = f"{label} {score:.0%}"
            (tw, th), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )
            cv2.rectangle(
                frame, (x1, y1 - th - 10), (x1 + tw + 4, y1), color, -1
            )
            cv2.putText(
                frame, text, (x1 + 2, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )
        return frame

    def start_recording(self, storage):
        """Begin video recording."""
        if not self._is_recording:
            self._recording_writer, self._recording_path = \
                storage.start_recording(self.width, self.height, self.fps)
            self._is_recording = True

    def write_frame(self, frame):
        """Write a frame to the current recording."""
        if self._is_recording and self._recording_writer:
            try:
                self._recording_writer.write(frame)
            except Exception as e:
                logger.error(f"კადრის ჩაწერის შეცდომა: {e}")

    def stop_recording(self, storage):
        """Stop current video recording."""
        if self._is_recording:
            storage.stop_recording(self._recording_writer, self._recording_path)
            self._recording_writer = None
            self._recording_path   = None
            self._is_recording     = False

    @property
    def is_recording(self):
        return self._is_recording
