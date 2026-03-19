import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


class MotionDetector:
    """
    Lightweight pixel-difference motion detector.
    Runs before ML inference to avoid wasting CPU on static scenes.
    """

    def __init__(self, threshold=25, min_area=500, blur_size=21):
        """
        threshold  — pixel brightness change to count as motion (0-255)
        min_area   — minimum contour area in pixels to trigger motion
        blur_size  — gaussian blur kernel size (must be odd)
        """
        self.threshold = threshold
        self.min_area  = min_area
        self.blur_size = blur_size
        self._prev_frame = None

    def detect(self, frame):
        """
        Returns True if meaningful motion is detected vs previous frame.
        Also returns a motion score (0.0 - 1.0) for logging/tuning.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)

        if self._prev_frame is None:
            self._prev_frame = gray
            return False, 0.0

        # Absolute difference between current and previous frame
        delta = cv2.absdiff(self._prev_frame, gray)
        self._prev_frame = gray

        # Threshold the delta
        _, thresh = cv2.threshold(delta, self.threshold, 255, cv2.THRESH_BINARY)

        # Dilate to fill gaps
        thresh = cv2.dilate(thresh, None, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Check if any contour is large enough
        motion_pixels = 0
        for contour in contours:
            if cv2.contourArea(contour) >= self.min_area:
                motion_pixels += cv2.contourArea(contour)

        total_pixels = frame.shape[0] * frame.shape[1]
        score = min(1.0, motion_pixels / total_pixels)

        motion_detected = score > 0
        return motion_detected, score

    def reset(self):
        """Reset the previous frame buffer."""
        self._prev_frame = None
