import logging
import numpy as np
import cv2
from ai_edge_litert import interpreter as litert
from config import (
    MODEL_PATH,
    LABEL_PATH,
    DETECTION_THRESHOLD,
    CONSECUTIVE_FRAMES_REQUIRED,
    DETECTION_DEBUG,
    DETECTION_DEBUG_FLOOR,
)

logger = logging.getLogger(__name__)


class ObjectDetector:
    SECURITY_LABELS = {'person', 'car', 'motorcycle', 'bus', 'truck', 'bicycle'}

    def __init__(self):
        self.threshold = DETECTION_THRESHOLD
        self.consecutive_required = CONSECUTIVE_FRAMES_REQUIRED
        self._label_streaks = {}

        with open(LABEL_PATH, 'r') as f:
            self.labels = [line.strip() for line in f.readlines()]

        self.interpreter = litert.Interpreter(model_path=MODEL_PATH)
        self.interpreter.allocate_tensors()

        self.input_details  = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

        self.input_height = self.input_details[0]['shape'][1]
        self.input_width  = self.input_details[0]['shape'][2]

    def preprocess(self, frame):
        resized = cv2.resize(frame, (self.input_width, self.input_height))
        return np.expand_dims(resized, axis=0).astype(np.uint8)

    def detect(self, frame):
        input_data = self.preprocess(frame)

        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()

        boxes   = self.interpreter.get_tensor(self.output_details[0]['index'])[0]
        classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]
        scores  = self.interpreter.get_tensor(self.output_details[2]['index'])[0]
        count   = int(self.interpreter.get_tensor(self.output_details[3]['index'])[0])

        detections = []
        debug_candidates = []  # (label, score) for security labels, pre-threshold
        for i in range(count):
            score = float(scores[i])
            class_idx = int(classes[i])
            if class_idx >= len(self.labels):
                continue
            label = self.labels[class_idx]
            if label not in self.SECURITY_LABELS:
                continue
            if DETECTION_DEBUG and score >= DETECTION_DEBUG_FLOOR:
                debug_candidates.append((label, score))
            if score < self.threshold:
                continue
            detections.append({
                'label': label,
                'score': score,
                'box':   boxes[i].tolist()
            })

        # log raw scores before the threshold (handy for tuning)
        if DETECTION_DEBUG and debug_candidates:
            passed = [f"{l} {s:.2f}" for l, s in debug_candidates if s >= self.threshold]
            below  = [f"{l} {s:.2f}" for l, s in debug_candidates if s < self.threshold]
            logger.info(
                f"RAW thr={self.threshold:.2f} "
                f"passed=[{', '.join(passed)}] below=[{', '.join(below)}]"
            )

        if not detections:
            self._label_streaks = {}
            return []

        if self.consecutive_required <= 1:
            return detections

        current_labels = {d['label'] for d in detections}
        self._label_streaks = {
            label: self._label_streaks.get(label, 0) + 1
            for label in current_labels
        }
        confirmed_labels = {
            label for label, streak in self._label_streaks.items()
            if streak >= self.consecutive_required
        }

        # show what the consecutive-frames filter is holding back
        if DETECTION_DEBUG:
            pending = {
                l: self._label_streaks[l]
                for l in current_labels
                if l not in confirmed_labels
            }
            if pending:
                logger.info(
                    f"FILTER need {self.consecutive_required} in a row — "
                    f"confirmed={sorted(confirmed_labels)} pending={pending}"
                )

        return [d for d in detections if d['label'] in confirmed_labels]
