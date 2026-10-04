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


class KServeDetector:
    def __init__(self, inference_url: str, model_name: str,
                 input_size: tuple[int, int] = (640, 640),
                 conf_threshold: float = 0.25,
                 excluded_classes: set[str] | None = None,
                 token: str | None = None):
        self.inference_url = inference_url.rstrip("/")
        self.model_name = model_name
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.excluded_classes = excluded_classes or set()
        self.token = token
        self._client = grpcclient.InferenceServerClient(url=inference_url)
        self._has_seg = None

    def preprocess(self, image: np.ndarray) -> tuple[np.ndarray, tuple[int, int]]:
        orig_h, orig_w = image.shape[:2]
        resized = cv2.resize(image, self.input_size, interpolation=cv2.INTER_LINEAR)
        blob = resized.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis]
        return blob, (orig_w, orig_h)

    def postprocess(self, outputs: dict, orig_size: tuple[int, int]) -> tuple[list[dict], list[np.ndarray] | None]:
        orig_w, orig_h = orig_size
        inp_w, inp_h = self.input_size

        output = outputs["output0"].squeeze(0)
        has_seg = "output1" in outputs and output.shape[-1] > 6

        scores = output[:, 4]
        class_ids = output[:, 5].astype(int)
        boxes = output[:, :4]
        mask_coeffs = output[:, 6:] if has_seg else None

        conf_mask = scores > self.conf_threshold
        boxes = boxes[conf_mask]
        scores = scores[conf_mask]
        class_ids = class_ids[conf_mask]
        if mask_coeffs is not None:
            mask_coeffs = mask_coeffs[conf_mask]

        if len(boxes) == 0:
            return [], None

        x1 = boxes[:, 0] * orig_w / inp_w
        y1 = boxes[:, 1] * orig_h / inp_h
        x2 = boxes[:, 2] * orig_w / inp_w
        y2 = boxes[:, 3] * orig_h / inp_h
        boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

        # Compute segmentation masks
        seg_masks = None
        if has_seg and mask_coeffs is not None:
            protos = outputs["output1"].squeeze(0)  # [32, 160, 160]
            raw_masks = mask_coeffs @ protos.reshape(protos.shape[0], -1)  # [N, 160*160]
            raw_masks = 1.0 / (1.0 + np.exp(-raw_masks))  # sigmoid
            raw_masks = raw_masks.reshape(-1, protos.shape[1], protos.shape[2])  # [N, 160, 160]

            seg_masks = []
            for i in range(len(raw_masks)):
                m = cv2.resize(raw_masks[i], (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
                bx1, by1, bx2, by2 = [int(v) for v in boxes_xyxy[i]]
                cropped = np.zeros_like(m, dtype=np.uint8)
                cropped[by1:by2, bx1:bx2] = (m[by1:by2, bx1:bx2] > 0.5).astype(np.uint8)
                seg_masks.append(cropped)

        detections = []
        keep_indices = []
        for i in range(len(boxes_xyxy)):
            cid = int(class_ids[i])
            name = COCO_CLASSES[cid] if cid < len(COCO_CLASSES) else str(cid)
            if self.excluded_classes and name in self.excluded_classes:
                continue
            keep_indices.append(i)
            detections.append({
                "class_id": cid,
                "class_name": name,
                "confidence": round(float(scores[i]), 4),
                "bbox": [round(float(v), 1) for v in boxes_xyxy[i]],
            })

        if seg_masks is not None:
            seg_masks = [seg_masks[i] for i in keep_indices]

        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections, seg_masks

    def detect(self, image: np.ndarray) -> tuple[list[dict], list[np.ndarray] | None, float]:
        blob, orig_size = self.preprocess(image)

        inputs = [grpcclient.InferInput("images", list(blob.shape), "FP32")]
        inputs[0].set_data_from_numpy(blob)

        outputs = [grpcclient.InferRequestedOutput("output0")]
        if self._has_seg is not False:
            outputs.append(grpcclient.InferRequestedOutput("output1"))

        t0 = time.perf_counter()
        try:
            result = self._client.infer(
                model_name=self.model_name,
                inputs=inputs,
                outputs=outputs,
            )
        except Exception:
            if self._has_seg is None:
                outputs = [grpcclient.InferRequestedOutput("output0")]
                result = self._client.infer(
                    model_name=self.model_name,
                    inputs=inputs,
                    outputs=outputs,
                )
                self._has_seg = False
            else:
                raise
        inference_ms = (time.perf_counter() - t0) * 1000

        output_dict = {"output0": result.as_numpy("output0")}
        if self._has_seg is not False:
            try:
                output_dict["output1"] = result.as_numpy("output1")
                self._has_seg = True
            except Exception:
                self._has_seg = False

        detections, masks = self.postprocess(output_dict, orig_size)
        return detections, masks, inference_ms

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
