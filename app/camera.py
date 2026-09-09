import threading
import time

import cv2
import numpy as np


class RTSPCamera:
    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _build_gst_pipeline(self) -> str:
        return (
            f"rtspsrc location={self.rtsp_url} latency=100 drop-on-latency=true ! "
            "rtph264depay ! h264parse ! avdec_h264 ! "
            "videoconvert ! video/x-raw,format=BGR ! "
            "appsink drop=true max-buffers=1 sync=false"
        )

    def _capture_loop(self):
        while self._running:
            pipeline = self._build_gst_pipeline()
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

            if not cap.isOpened():
                self._connected = False
                cap.release()
                time.sleep(5)
                continue

            self._connected = True
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self._connected = False
                    break
                with self._lock:
                    self._frame = frame

            cap.release()
            if self._running:
                time.sleep(2)
