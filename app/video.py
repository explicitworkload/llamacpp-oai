import threading
import time

import cv2
import numpy as np


class VideoPlayer:
    def __init__(self, path: str):
        self.path = path
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._fps: float = 30.0
        self._total_frames: int = 0
        self._resolution: tuple[int, int] = (0, 0)

    @property
    def active(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def resolution(self) -> tuple[int, int]:
        return self._resolution

    def start(self):
        if self._running:
            return
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            cap.release()
            raise ValueError("Cannot open video file")
        self._fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._resolution = (w, h)
        cap.release()

        self._running = True
        self._thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_frame(self) -> np.ndarray | None:
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def _playback_loop(self):
        interval = 1.0 / self._fps
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            self._running = False
            return

        while self._running:
            t0 = time.monotonic()
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            with self._lock:
                self._frame = frame
            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
