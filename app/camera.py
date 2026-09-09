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

    def _capture_loop(self):
        while self._running:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

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
