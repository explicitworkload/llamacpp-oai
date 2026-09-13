import time

import cv2
import numpy as np
import tritonclient.grpc as grpcclient


class KServeSegmenter:
    def __init__(self, inference_url: str, model_name: str,
                 token: str | None = None):
        self.inference_url = inference_url.rstrip("/")
        self.model_name = model_name
        self.token = token
        self._client = grpcclient.InferenceServerClient(url=inference_url)

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

        inputs = [
            grpcclient.InferInput("image", list(img_blob.shape), "FP32"),
            grpcclient.InferInput("boxes", list(box_array.shape), "FP32"),
        ]
        inputs[0].set_data_from_numpy(img_blob)
        inputs[1].set_data_from_numpy(box_array)

        t0 = time.perf_counter()
        result = self._client.infer(model_name=self.model_name, inputs=inputs)
        seg_ms = (time.perf_counter() - t0) * 1000

        mask_data = result.as_numpy(result.get_output("masks")["name"])

        masks = []
        for i in range(mask_data.shape[0]):
            mask = mask_data[i, 0]
            mask = (mask > 0.0).astype(np.uint8)
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            masks.append(mask)

        return masks, seg_ms

    def is_ready(self) -> bool:
        try:
            return self._client.is_model_ready(self.model_name)
        except Exception:
            return False
