import time

import cv2
import httpx
import numpy as np


class KServeSegmenter:
    def __init__(self, inference_url: str, model_name: str,
                 token: str | None = None):
        self.inference_url = inference_url.rstrip("/")
        self.model_name = model_name
        self.token = token
        self._client = httpx.Client(verify=False, timeout=30.0)

    def segment(self, image: np.ndarray, boxes: list[list[float]]) -> tuple[list[np.ndarray], float]:
        if not boxes:
            return [], 0.0

        h, w = image.shape[:2]
        resized = cv2.resize(image, (1024, 1024), interpolation=cv2.INTER_LINEAR)
        img_blob = resized.astype(np.float32) / 255.0
        img_blob = img_blob.transpose(2, 0, 1)[np.newaxis]

        box_array = np.array(boxes, dtype=np.float32)
        box_array[:, [0, 2]] *= 1024.0 / w
        box_array[:, [1, 3]] *= 1024.0 / h

        payload = {
            "inputs": [
                {
                    "name": "image",
                    "shape": list(img_blob.shape),
                    "datatype": "FP32",
                    "data": img_blob.flatten().tolist(),
                },
                {
                    "name": "boxes",
                    "shape": list(box_array.shape),
                    "datatype": "FP32",
                    "data": box_array.flatten().tolist(),
                },
            ]
        }

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        url = f"{self.inference_url}/v2/models/{self.model_name}/infer"

        t0 = time.perf_counter()
        resp = self._client.post(url, json=payload, headers=headers)
        seg_ms = (time.perf_counter() - t0) * 1000

        resp.raise_for_status()
        result = resp.json()

        mask_output = result["outputs"][0]
        mask_data = np.array(mask_output["data"], dtype=np.float32).reshape(mask_output["shape"])

        masks = []
        for i in range(mask_data.shape[0]):
            mask = mask_data[i, 0]
            mask = (mask > 0.0).astype(np.uint8)
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            masks.append(mask)

        return masks, seg_ms

    def is_ready(self) -> bool:
        try:
            url = f"{self.inference_url}/v2/models/{self.model_name}/ready"
            headers = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            resp = self._client.get(url, headers=headers)
            return resp.status_code == 200
        except Exception:
            return False
