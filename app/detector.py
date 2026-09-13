import time

import cv2
import numpy as np
import tritonclient.grpc as grpcclient


COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


class KServeDetector:
    def __init__(self, inference_url: str, model_name: str,
                 input_size: tuple[int, int] = (560, 560),
                 conf_threshold: float = 0.25,
                 token: str | None = None):
        self.inference_url = inference_url.rstrip("/")
        self.model_name = model_name
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.token = token
        self._client = grpcclient.InferenceServerClient(url=inference_url)

    def preprocess(self, image: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
        orig_h, orig_w = image.shape[:2]
        resized = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)
        blob = resized.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis]
        return blob, (orig_w, orig_h)

    def postprocess(self, outputs: dict, orig_size: tuple[int, int]) -> list[dict]:
        orig_w, orig_h = orig_size

        dets = outputs["pred_boxes"].squeeze(0)
        logits = outputs["logits"].squeeze(0)

        scores = _sigmoid(logits)

        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        mask = max_scores > self.conf_threshold
        dets = dets[mask]
        max_scores = max_scores[mask]
        class_ids = class_ids[mask]

        if len(dets) == 0:
            return []

        cx, cy, bw, bh = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3]
        x1 = (cx - bw / 2) * orig_w
        y1 = (cy - bh / 2) * orig_h
        x2 = (cx + bw / 2) * orig_w
        y2 = (cy + bh / 2) * orig_h
        boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

        detections = []
        for i in range(len(boxes_xyxy)):
            cid = int(class_ids[i])
            detections.append({
                "class_id": cid,
                "class_name": COCO_CLASSES[cid] if cid < len(COCO_CLASSES) else str(cid),
                "confidence": round(float(max_scores[i]), 4),
                "bbox": [round(float(v), 1) for v in boxes_xyxy[i]],
            })

        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections

    def detect(self, image: np.ndarray) -> tuple[list[dict], float]:
        blob, orig_size = self.preprocess(image)

        inputs = [grpcclient.InferInput("pixel_values", list(blob.shape), "FP32")]
        inputs[0].set_data_from_numpy(blob)

        outputs = [
            grpcclient.InferRequestedOutput("pred_boxes"),
            grpcclient.InferRequestedOutput("logits"),
        ]

        t0 = time.perf_counter()
        result = self._client.infer(
            model_name=self.model_name,
            inputs=inputs,
            outputs=outputs,
        )
        inference_ms = (time.perf_counter() - t0) * 1000

        output_dict = {
            "pred_boxes": result.as_numpy("pred_boxes"),
            "logits": result.as_numpy("logits"),
        }

        detections = self.postprocess(output_dict, orig_size)
        return detections, inference_ms

    def is_ready(self) -> bool:
        try:
            return self._client.is_model_ready(self.model_name)
        except Exception:
            return False


PALETTE = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
    (255, 0, 255), (0, 255, 255), (128, 255, 0), (255, 128, 0),
    (128, 0, 255), (0, 128, 255), (255, 0, 128), (0, 255, 128),
]


def draw_detections(image: np.ndarray, detections: list[dict],
                    masks: list[np.ndarray] | None = None) -> np.ndarray:
    annotated = image.copy()
    overlay = annotated.copy()

    for i, det in enumerate(detections):
        color = PALETTE[i % len(PALETTE)]

        if masks and i < len(masks):
            overlay[masks[i] > 0] = color

        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        label = f"{det['class_name']} {det['confidence']:.0%}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw, y1), color, -1)
        cv2.putText(annotated, label, (x1, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    if masks:
        cv2.addWeighted(overlay, 0.4, annotated, 0.6, 0, annotated)

    return annotated
