import io
import os
import threading
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image

from app.detector import KServeDetector, draw_detections
from app.camera import RTSPCamera

MODEL_NAME = os.getenv("MODEL_NAME", "model")
RTSP_URL = os.getenv("RTSP_URL", "rtsp://172.16.199.110/stream1")
INPUT_SIZE = int(os.getenv("INPUT_SIZE", "640"))
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", "0.25"))
UNDISTORT_K1 = float(os.getenv("UNDISTORT_K1", "0"))
_excluded_env = os.getenv("EXCLUDED_CLASSES", "")
EXCLUDED_CLASSES = {c.strip() for c in _excluded_env.split(",") if c.strip()} if _excluded_env else set()

# Multi-model: "yolo26=host:port,yolo26-seg=host:port"
# Falls back to single INFERENCE_URL if not set
INFERENCE_ENDPOINTS_ENV = os.getenv("INFERENCE_ENDPOINTS", "")
INFERENCE_URL = os.getenv("INFERENCE_URL", "yolo26-grpc.john.svc.cluster.local:8001")

camera: RTSPCamera | None = None
_detectors: dict[str, KServeDetector] = {}
_default_model: str | None = None
_model_detections: dict[str, list[dict]] = {}
_inference_lock = threading.Lock()
_inference_threads: list[threading.Thread] = []
_inference_running = False


def _inference_loop(model_name: str, detector: KServeDetector):
    while _inference_running:
        if camera is None or not camera.connected:
            time.sleep(0.5)
            continue

        frame = camera.get_frame()
        if frame is None:
            time.sleep(0.1)
            continue

        try:
            detections, _ = detector.detect(frame)
            with _inference_lock:
                _model_detections[model_name] = detections
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    global camera, _default_model, _inference_threads, _inference_running

    endpoints = {}
    if INFERENCE_ENDPOINTS_ENV:
        for entry in INFERENCE_ENDPOINTS_ENV.split(","):
            entry = entry.strip()
            if "=" in entry:
                name, url = entry.split("=", 1)
                endpoints[name.strip()] = url.strip()

    if not endpoints:
        endpoints["default"] = INFERENCE_URL

    for name, url in endpoints.items():
        _detectors[name] = KServeDetector(
            inference_url=url,
            model_name=MODEL_NAME,
            input_size=(INPUT_SIZE, INPUT_SIZE),
            conf_threshold=CONF_THRESHOLD,
            excluded_classes=EXCLUDED_CLASSES,
        )
        _model_detections[name] = []

    _default_model = next(iter(_detectors))

    camera = RTSPCamera(RTSP_URL, undistort_k1=UNDISTORT_K1)
    camera.start()

    _inference_running = True
    for name, detector in _detectors.items():
        t = threading.Thread(target=_inference_loop, args=(name, detector), daemon=True)
        t.start()
        _inference_threads.append(t)

    yield

    _inference_running = False
    for t in _inference_threads:
        t.join(timeout=5)
    camera.stop()


app = FastAPI(title="Vision AI", lifespan=lifespan)


def _get_detector(model: str | None = None) -> tuple[str, KServeDetector]:
    name = model if model and model in _detectors else _default_model
    if name is None or name not in _detectors:
        raise HTTPException(status_code=404, detail="No detector configured")
    return name, _detectors[name]


@app.get("/health")
def health():
    return {
        "status": "ok",
        "camera_connected": camera.connected if camera else False,
        "inference_running": _inference_running,
        "models": list(_detectors.keys()),
    }


@app.get("/models")
def list_models():
    return {"models": list(_detectors.keys()), "default": _default_model}


@app.post("/detect")
async def detect_image(file: UploadFile, model: str = None):
    name, detector = _get_detector(model)

    contents = await file.read()
    image = np.array(Image.open(io.BytesIO(contents)).convert("RGB"))
    image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    detections, det_ms = detector.detect(image)

    return {
        "model": name,
        "detections": detections,
        "inference_ms": round(det_ms, 1),
        "image_size": [image.shape[1], image.shape[0]],
    }


@app.get("/detect/camera")
def detect_camera(model: str = None):
    name, detector = _get_detector(model)
    if camera is None or not camera.connected:
        raise HTTPException(status_code=503, detail="Camera not connected")

    frame = camera.get_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    detections, det_ms = detector.detect(frame)

    return {
        "model": name,
        "detections": detections,
        "inference_ms": round(det_ms, 1),
        "image_size": [frame.shape[1], frame.shape[0]],
    }


@app.get("/snapshot")
def snapshot(annotate: bool = True, model: str = None):
    if camera is None or not camera.connected:
        raise HTTPException(status_code=503, detail="Camera not connected")

    frame = camera.get_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    if annotate:
        name, _ = _get_detector(model)
        with _inference_lock:
            detections = list(_model_detections.get(name, []))
        if detections:
            frame = draw_detections(frame, detections, None)

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return StreamingResponse(io.BytesIO(jpeg.tobytes()), media_type="image/jpeg")


@app.get("/stream")
def mjpeg_stream(annotate: bool = True, model: str = None):
    if camera is None or not camera.connected:
        raise HTTPException(status_code=503, detail="Camera not connected")

    name, _ = _get_detector(model)

    def generate():
        while True:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            if annotate:
                with _inference_lock:
                    detections = list(_model_detections.get(name, []))
                if detections:
                    frame = draw_detections(frame, detections, None)

            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg.tobytes()
                + b"\r\n"
            )

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")
