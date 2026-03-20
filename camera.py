import cv2
import numpy as np
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
        self._recording_start  = None
        self._is_recording     = False

    def start(self):
        """Initialize and start the camera with graceful error handling."""
        try:
            from picamera2 import Picamera2
        except ImportError:
            raise RuntimeError(
                "picamera2 is not installed. "
                "Run: sudo apt install python3-picamera2"
            )

        try:
            self.picam = Picamera2()
        except Exception as e:
            raise RuntimeError(
                f"Camera initialization failed. "
                f"Make sure the camera is connected and "
                f"config.txt is correctly configured.\n"
                f"Detail: {e}"
            )

        try:
            config = self.picam.create_video_configuration(
                main={"format": "RGB888", "size": (self.width, self.height)},
                controls={"FrameRate": self.fps}
            )
            self.picam.configure(config)
            self.picam.start()
            logger.info(
                f"Camera started — {self.width}x{self.height} @ {self.fps}fps"
            )
        except Exception as e:
            self.picam = None
            raise RuntimeError(f"Camera configuration failed: {e}")

    def stop(self):
        """Stop the camera safely."""
        if self.picam:
            try:
                self.picam.stop()
                logger.info("Camera stopped")
            except Exception as e:
                logger.warning(f"Camera stop error: {e}")
            finally:
                self.picam = None

    def capture_frame(self):
        """
        Capture a single frame and return as BGR numpy array.
        numpy is imported at module level for efficiency —
        no repeated import overhead on every frame.
        """
        if not self.picam:
            raise RuntimeError(
                "Camera not started — call start() first"
            )
        try:
            frame_rgb = self.picam.capture_array()
            return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        except Exception as e:
            raise RuntimeError(f"Frame capture error: {e}")

    def draw_detections(self, frame, detections):
        """Draw bounding boxes and confidence labels on frame."""
        h, w = frame.shape[:2]
        for det in detections:
            label = det['label']
            score = det['score']
            ymin, xmin, ymax, xmax = det['box']

            x1, y1 = int(xmin * w), int(ymin * h)
            x2, y2 = int(xmax * w), int(ymax * h)

            # Red for person, blue for vehicles
            color = (0, 0, 255) if label == 'person' else (255, 100, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            text = f"{label} {score:.0%}"
            (tw, th), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )
            # Filled background for label text
            cv2.rectangle(
                frame, (x1, y1 - th - 10), (x1 + tw + 4, y1), color, -1
            )
            cv2.putText(
                frame, text, (x1 + 2, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )
        return frame

    def start_recording(self, storage):
        """Begin video recording via storage manager."""
        if not self._is_recording:
            self._recording_writer, self._recording_path, self._recording_start = \
                storage.start_recording(self.width, self.height, self.fps)
            self._is_recording = True

    def write_frame(self, frame, storage=None):
        """
        Write frame to current recording.
        If storage is provided, checks for max recording length
        and auto-splits into a new file if needed.
        """
        if not self._is_recording or not self._recording_writer:
            return

        # Auto-split if recording exceeds MAX_RECORDING_SECONDS
        if storage and self._recording_start:
            if storage.should_split_recording(self._recording_start):
                logger.info("Max recording length reached — splitting file")
                storage.stop_recording(
                    self._recording_writer, self._recording_path
                )
                self._recording_writer, self._recording_path, \
                    self._recording_start = storage.start_recording(
                        self.width, self.height, self.fps
                    )

        try:
            self._recording_writer.write(frame)
        except Exception as e:
            logger.error(f"Frame write error: {e}")

    def stop_recording(self, storage):
        """Stop current video recording."""
        if self._is_recording:
            storage.stop_recording(
                self._recording_writer, self._recording_path
            )
            self._recording_writer = None
            self._recording_path   = None
            self._recording_start  = None
            self._is_recording     = False

    @property
    def is_recording(self):
        return self._is_recording
