import cv2
import time
import logging
import numpy as np
from config import FRAME_WIDTH, FRAME_HEIGHT, FPS

logger = logging.getLogger(__name__)


class MockCamera:
    """
    Simulates a real camera using a static test image.
    Drop-in replacement for Camera() during testing.
    Cycles through the test image repeatedly at the configured FPS.
    """

    def __init__(self):
        self.width         = FRAME_WIDTH
        self.height        = FRAME_HEIGHT
        self.fps           = FPS
        self._frame        = None
        self._is_recording = False
        self._recording_writer = None
        self._recording_path   = None
        self._recording_start  = None

    def start(self):
        """Load the test image as the mock frame source."""
        import os
        from config import BASE_DIR

        # Try test image first, fall back to a generated frame
        test_path = os.path.join(BASE_DIR, 'test_image.jpg')
        if os.path.exists(test_path):
            frame = cv2.imread(test_path)
            self._frame = cv2.resize(frame, (self.width, self.height))
            logger.info(f"MockCamera started — using {test_path}")
        else:
            # Generate a grey frame with text if no image available
            self._frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            self._frame[:] = (50, 50, 50)
            cv2.putText(
                self._frame, "MOCK CAMERA — NO IMAGE",
                (self.width // 4, self.height // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3
            )
            logger.warning("MockCamera — no test image found, using grey frame")

    def stop(self):
        logger.info("MockCamera stopped")

    def capture_frame(self):
        """Return the mock frame with a slight variation to trigger motion."""
        # Add tiny random noise so motion detector doesn't freeze
        noise = np.random.randint(0, 8, self._frame.shape, dtype=np.uint8)
        return cv2.add(self._frame, noise)

    def draw_detections(self, frame, detections):
        """Identical to real Camera — draw boxes and labels."""
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

    def start_recording(self, storage, timestamp=None):
        if not self._is_recording:
            self._recording_writer, self._recording_path, self._recording_start = \
                storage.start_recording(self.width, self.height, self.fps, timestamp=timestamp)
            self._is_recording = True

    def write_frame(self, frame, storage=None):
        if not self._is_recording or not self._recording_writer:
            return

        if storage and self._recording_start:
            if storage.should_split_recording(self._recording_start):
                storage.stop_recording(
                    self._recording_writer, self._recording_path
                )
                self._recording_writer, self._recording_path, self._recording_start = \
                    storage.start_recording(self.width, self.height, self.fps)

        self._recording_writer.write(frame)

    def stop_recording(self, storage):
        if self._is_recording:
            storage.stop_recording(self._recording_writer, self._recording_path)
            self._recording_writer = None
            self._recording_path   = None
            self._recording_start  = None
            self._is_recording     = False

    @property
    def is_recording(self):
        return self._is_recording
