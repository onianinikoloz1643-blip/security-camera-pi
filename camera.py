import cv2
import logging
from config import (
    FRAME_WIDTH, FRAME_HEIGHT, FPS,
    CAMERA_HFLIP, CAMERA_VFLIP, CAMERA_BACKEND,
)

logger = logging.getLogger(__name__)


# ── Camera backends ───────────────────────────────────────────────────
# Each backend exposes: open() -> bool, read() -> BGR ndarray | None, close().
# A backend only counts as "working" once open() has captured a real frame.

class Picamera2Source:
    """CSI camera via Picamera2 / libcamera (Raspberry Pi camera modules)."""

    name = "CSI (Picamera2)"

    def __init__(self, width, height, fps):
        self.width  = width
        self.height = height
        self.fps    = fps
        self.device = "CSI port"
        self._picam = None

    def open(self):
        try:
            from picamera2 import Picamera2
            from libcamera import Transform
        except ImportError:
            # A missing library is an environment problem worth surfacing, not a
            # "no camera here" — re-raise so start() reports it instead of silently
            # falling through.
            raise RuntimeError(
                "picamera2 is not installed. "
                "Run: sudo apt install python3-picamera2"
            )

        try:
            self._picam = Picamera2()
            config = self._picam.create_video_configuration(
                main={"format": "RGB888", "size": (self.width, self.height)},
                controls={"FrameRate": self.fps},
                transform=Transform(hflip=CAMERA_HFLIP, vflip=CAMERA_VFLIP),
            )
            self._picam.configure(config)
            self._picam.start()
        except Exception as e:
            logger.warning(f"CSI camera did not initialize: {e}")
            self.close()
            return False

        # A clean start() is not proof of a live feed — require a real frame.
        frame = self.read()
        if frame is None:
            logger.warning("CSI camera started but returned no frame")
            self.close()
            return False

        # adopt the true frame size so recordings match what we capture
        self.height, self.width = frame.shape[:2]
        return True

    def read(self):
        if not self._picam:
            return None
        try:
            frame_rgb = self._picam.capture_array()
            return cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"CSI frame capture error: {e}")
            return None

    def close(self):
        if self._picam:
            try:
                self._picam.stop()
            except Exception:
                pass
            try:
                self._picam.close()
            except Exception:
                pass
            self._picam = None


# ── Public facade ─────────────────────────────────────────────────────

class Camera:
    """Selects a working camera backend at start(), then exposes a stable
    interface (capture_frame -> BGR, recording helpers) to the rest of the
    system, independent of which camera is actually connected."""

    def __init__(self):
        self.width   = FRAME_WIDTH
        self.height  = FRAME_HEIGHT
        self.fps     = FPS
        self._source = None

        self._recording_writer = None
        self._recording_path   = None
        self._recording_start  = None
        self._is_recording     = False

    def start(self):
        """Probe for a working camera and start it.
        Raises RuntimeError (handled by main.py) if none is available."""
        backend = (CAMERA_BACKEND or 'auto').lower()

        if backend in ('auto', 'csi'):
            source = Picamera2Source(FRAME_WIDTH, FRAME_HEIGHT, FPS)
            if source.open():
                self._use(source)
                return
            raise RuntimeError(
                "No working camera found (checked: CSI via Picamera2). "
                "Make sure a camera is connected and enabled in "
                "/boot/firmware/config.txt (camera_auto_detect=1, or the "
                "correct dtoverlay), then reboot."
            )

        # The USB ('usb') backend is added in a later stage.
        raise RuntimeError(
            f"CAMERA_BACKEND='{backend}' is not supported yet; use 'auto' or 'csi'."
        )

    def _use(self, source):
        self._source = source
        # adopt the backend's actual frame size; keep the configured FPS as the
        # recording/sampling rate (the capture loop paces itself at FPS)
        self.width  = source.width
        self.height = source.height
        logger.info(
            f"Camera: {source.name} on {source.device} — "
            f"{self.width}x{self.height} @ {self.fps}fps"
        )

    def stop(self):
        """Stop the camera safely."""
        if self._source:
            self._source.close()
            self._source = None
            logger.info("Camera stopped")

    def capture_frame(self):
        """Capture a single frame and return it as a BGR numpy array."""
        if not self._source:
            raise RuntimeError("Camera not started — call start() first")
        frame = self._source.read()
        if frame is None:
            raise RuntimeError("Frame capture returned no data")
        return frame

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

    def start_recording(self, storage, timestamp=None):
        """Begin video recording via storage manager."""
        if not self._is_recording:
            self._recording_writer, self._recording_path, self._recording_start = \
                storage.start_recording(self.width, self.height, self.fps, timestamp=timestamp)
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
