import io
import os
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from app.detector import KServeDetector, draw_detections
from app.segmenter import KServeSegmenter
from app.camera import RTSPCamera

INFERENCE_URL = os.getenv("INFERENCE_URL", "https://rf-detr-john.apps.example.com")
MODEL_NAME = os.getenv("MODEL_NAME", "rf-detr")
SAM2_URL = os.getenv("SAM2_URL", "https://sam2-john.apps.example.com")
SAM2_MODEL_NAME = os.getenv("SAM2_MODEL_NAME", "sam2")
RTSP_URL = os.getenv("RTSP_URL", "rtsp://172.16.199.10:554/stream1")
INPUT_SIZE = int(os.getenv("INPUT_SIZE", "640"))
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.25"))
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"

detector: KServeDetector | None = None
segmenter: KServeSegmenter | None = None
camera: RTSPCamera | None = None


def _get_sa_token() -> str | None:
    try:
        with open(SA_TOKEN_PATH) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _detect_and_segment(frame: np.ndarray) -> tuple[list[dict], list[np.ndarray] | None, float]:
    detections, det_ms = detector.detect(frame)
    masks = None
    seg_ms = 0.0
    if detections and segmenter and segmenter.is_ready():
        boxes = [d["bbox"] for d in detections]
        masks, seg_ms = segmenter.segment(frame, boxes)
    return detections, masks, det_ms + seg_ms


@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector, segmenter, camera

    token = _get_sa_token()
    detector = KServeDetector(
        inference_url=INFERENCE_URL,
        model_name=MODEL_NAME,
        input_size=(INPUT_SIZE, INPUT_SIZE),
        conf_threshold=CONF_THRESHOLD,
        token=token,
    )
    segmenter = KServeSegmenter(
        inference_url=SAM2_URL,
        model_name=SAM2_MODEL_NAME,
        token=token,
    )

    camera = RTSPCamera(RTSP_URL)
    camera.start()

    yield

    camera.stop()


app = FastAPI(title="Vision AI", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "detector_ready": detector.is_ready() if detector else False,
        "segmenter_ready": segmenter.is_ready() if segmenter else False,
        "camera_connected": camera.connected if camera else False,
        "inference_url": INFERENCE_URL,
        "model_name": MODEL_NAME,
        "sam2_url": SAM2_URL,
        "rtsp_url": RTSP_URL,
    }


@app.post("/detect")
async def detect_image(file: UploadFile):
    if detector is None:
        raise HTTPException(status_code=503, detail="Detector not configured")

    contents = await file.read()
    image = np.array(Image.open(io.BytesIO(contents)).convert("RGB"))
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    detections, masks, total_ms = _detect_and_segment(image)

    return {
        "detections": detections,
        "inference_ms": round(total_ms, 1),
        "image_size": [image.shape[1], image.shape[0]],
        "segmentation": masks is not None,
    }


@app.get("/detect/camera")
def detect_camera():
    if detector is None:
        raise HTTPException(status_code=503, detail="Detector not configured")
    if camera is None or not camera.connected:
        raise HTTPException(status_code=503, detail="Camera not connected")

    frame = camera.get_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    detections, masks, total_ms = _detect_and_segment(frame)

    return {
        "detections": detections,
        "inference_ms": round(total_ms, 1),
        "image_size": [frame.shape[1], frame.shape[0]],
        "segmentation": masks is not None,
    }


@app.get("/snapshot")
def snapshot(annotate: bool = True):
    if camera is None or not camera.connected:
        raise HTTPException(status_code=503, detail="Camera not connected")

    frame = camera.get_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    if annotate and detector is not None:
        detections, masks, _ = _detect_and_segment(frame)
        frame = draw_detections(frame, detections, masks)

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return StreamingResponse(io.BytesIO(jpeg.tobytes()), media_type="image/jpeg")


@app.get("/stream")
def mjpeg_stream(annotate: bool = True):
    if camera is None or not camera.connected:
        raise HTTPException(status_code=503, detail="Camera not connected")

    def generate():
        while True:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            if annotate and detector is not None:
                detections, masks, _ = _detect_and_segment(frame)
                frame = draw_detections(frame, detections, masks)

            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )
            time.sleep(0.033)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
