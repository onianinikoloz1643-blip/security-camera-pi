import cv2
import logging
import numpy as np
from config import MOTION_THRESHOLD, MOTION_MIN_AREA, MOTION_BLUR

logger = logging.getLogger(__name__)


class MotionDetector:
    """
    Lightweight pixel-difference motion detector.
    Runs before ML inference to avoid wasting CPU on static scenes.
    """

    def __init__(self):
        self.threshold = MOTION_THRESHOLD
        self.min_area  = MOTION_MIN_AREA
        self.blur_size = MOTION_BLUR

        self._prev_frame = None

    def detect(self, frame):
        """Returns (motion_detected: bool, score: float 0.0-1.0)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)

        # First frame — nothing to compare yet
        if self._prev_frame is None:
            self._prev_frame = gray
            return False, 0.0

        # Absolute difference
        delta = cv2.absdiff(self._prev_frame, gray)
        self._prev_frame = gray

        # [diag] a live camera always has a >0 frame delta (sensor noise);
        # an exactly-0 delta means capture keeps returning the same frame (frozen)
        self._diag_count = getattr(self, '_diag_count', 0) + 1
        if self._diag_count % 100 == 0:
            logger.info(f"[diag] frame delta sum={int(delta.sum())}")

        # Threshold
        _, thresh = cv2.threshold(
            delta, self.threshold, 255, cv2.THRESH_BINARY
        )

        # Dilate to fill small gaps
        thresh = cv2.dilate(thresh, None, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Sum area of significant contours
        motion_area = sum(
            cv2.contourArea(c)
            for c in contours
            if cv2.contourArea(c) >= self.min_area
        )

        total_pixels = frame.shape[0] * frame.shape[1]
        score        = min(1.0, motion_area / total_pixels)

        return score > 0, score

    def reset(self):
        """Manually reset the frame buffer."""
        self._prev_frame = None
        logger.debug("Motion detector reset")
