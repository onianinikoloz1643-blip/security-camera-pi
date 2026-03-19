import numpy as np
import cv2
from ai_edge_litert import interpreter as litert
from config import MODEL_PATH, LABEL_PATH, DETECTION_THRESHOLD


class ObjectDetector:
    SECURITY_LABELS = {'person', 'car', 'motorcycle', 'bus', 'truck', 'bicycle'}

    def __init__(self):
        self.threshold = DETECTION_THRESHOLD

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
        for i in range(count):
            score = float(scores[i])
            if score < self.threshold:
                continue
            class_idx = int(classes[i])
            if class_idx >= len(self.labels):
                continue
            label = self.labels[class_idx]
            if label not in self.SECURITY_LABELS:
                continue
            detections.append({
                'label': label,
                'score': score,
                'box':   boxes[i].tolist()
            })

        return detections
