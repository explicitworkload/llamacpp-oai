import threading
import time

import cv2
import numpy as np


class RTSPCamera:
    def __init__(self, rtsp_url: str, undistort_k1: float = 0.0):
        self.rtsp_url = rtsp_url
        self._undistort_k1 = undistort_k1
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._connected = False
        self._map1: np.ndarray | None = None
        self._map2: np.ndarray | None = None
        self._map_size: tuple[int, int] | None = None

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

    def _init_undistort_maps(self, h: int, w: int):
        fx = fy = float(w)
        cx, cy = w / 2.0, h / 2.0
        camera_matrix = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)
        dist_coeffs = np.array([self._undistort_k1, 0, 0, 0, 0], dtype=np.float64)
        new_camera_matrix, _ = cv2.getOptimalNewCameraMatrix(
            camera_matrix, dist_coeffs, (w, h), 0
        )
        self._map1, self._map2 = cv2.initUndistortRectifyMap(
            camera_matrix, dist_coeffs, None, new_camera_matrix, (w, h), cv2.CV_16SC2
        )
        self._map_size = (h, w)

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
                if self._undistort_k1 != 0:
                    if self._map1 is None or self._map_size != (frame.shape[0], frame.shape[1]):
                        self._init_undistort_maps(frame.shape[0], frame.shape[1])
                    frame = cv2.remap(frame, self._map1, self._map2, cv2.INTER_LINEAR)
                with self._lock:
                    self._frame = frame

            cap.release()
            if self._running:
                time.sleep(2)
