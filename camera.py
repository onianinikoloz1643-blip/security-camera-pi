import cv2
import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Camera:
    def __init__(self, width=1280, height=720, fps=10):
        self.width = width
        self.height = height
        self.fps = fps
        self.picam = None
        self._recording_writer = None
        self._recording_path = None
        self._is_recording = False

    def start(self):
        """Initialize and start the camera."""
        from picamera2 import Picamera2
        self.picam = Picamera2()
        config = self.picam.create_video_configuration(
            main={"format": "RGB888", "size": (self.width, self.height)},
            controls={"FrameRate": self.fps}
        )
        self.picam.configure(config)
        self.picam.start()
        logger.info("Camera started")

    def stop(self):
        """Stop the camera."""
        if self.picam:
            self.picam.stop()
            logger.info("Camera stopped")

    def capture_frame(self):
        """Capture a single frame and return as BGR numpy array."""
        if not self.picam:
            raise RuntimeError("Camera not started")
        # Picamera2 gives RGB, convert to BGR for OpenCV
        frame_rgb = self.picam.capture_array()
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        return frame_bgr

    def draw_detections(self, frame, detections):
        """Draw bounding boxes and labels on frame."""
        h, w = frame.shape[:2]
        for det in detections:
            label = det['label']
            score = det['score']
            ymin, xmin, ymax, xmax = det['box']

            # Convert normalized coords to pixels
            x1, y1 = int(xmin * w), int(ymin * h)
            x2, y2 = int(xmax * w), int(ymax * h)

            # Color: red for person, blue for vehicles
            color = (0, 0, 255) if label == 'person' else (255, 100, 0)

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            text = f"{label} {score:.0%}"
            cv2.putText(frame, text, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return frame

    def start_recording(self, storage):
        """Begin video recording via storage manager."""
        if not self._is_recording:
            self._recording_writer, self._recording_path = storage.start_recording(
                self.width, self.height, self.fps
            )
            self._is_recording = True

    def write_frame(self, frame):
        """Write a frame to the current recording."""
        if self._is_recording and self._recording_writer:
            self._recording_writer.write(frame)

    def stop_recording(self, storage):
        """Stop current video recording."""
        if self._is_recording:
            storage.stop_recording(self._recording_writer, self._recording_path)
            self._recording_writer = None
            self._recording_path = None
            self._is_recording = False

    @property
    def is_recording(self):
        return self._is_recording
