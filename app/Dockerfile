# Stage 1: Build OpenCV with GStreamer support
FROM registry.access.redhat.com/ubi9/python-312 AS opencv-builder

USER 0

RUN dnf install -y --nodocs \
        cmake gcc gcc-c++ make \
        gstreamer1-devel gstreamer1-plugins-base-devel \
        python3.12-devel \
    && dnf clean all

RUN pip install --no-cache-dir numpy

ARG OPENCV_VERSION=4.10.0
RUN curl -sL https://github.com/opencv/opencv/archive/refs/tags/${OPENCV_VERSION}.tar.gz | tar xz \
    && cd opencv-${OPENCV_VERSION} && mkdir build && cd build \
    && cmake \
        -D CMAKE_BUILD_TYPE=RELEASE \
        -D CMAKE_INSTALL_PREFIX=/usr/local \
        -D WITH_GSTREAMER=ON \
        -D WITH_FFMPEG=OFF \
        -D WITH_V4L=OFF \
        -D WITH_GTK=OFF \
        -D WITH_QT=OFF \
        -D BUILD_opencv_python3=ON \
        -D BUILD_opencv_java=OFF \
        -D BUILD_TESTS=OFF \
        -D BUILD_PERF_TESTS=OFF \
        -D BUILD_EXAMPLES=OFF \
        -D BUILD_opencv_apps=OFF \
        -D PYTHON3_EXECUTABLE=/usr/bin/python3.12 \
        -D PYTHON3_INCLUDE_DIR=/usr/include/python3.12 \
        -D PYTHON3_LIBRARY=/usr/lib64/libpython3.12.so \
        .. \
    && make -j"$(nproc)" \
    && make install

# Stage 2: Production runtime
FROM registry.access.redhat.com/ubi9/python-312

USER 0

# GStreamer runtime (RTSP capture)
RUN dnf install -y --nodocs \
        gstreamer1 \
        gstreamer1-plugins-base \
        gstreamer1-plugins-good \
        gstreamer1-plugins-bad-free \
    && dnf clean all

# Copy OpenCV built with GStreamer from builder stage
COPY --from=opencv-builder /usr/local/lib/python3.12/site-packages/cv2 \
     /opt/app-root/lib/python3.12/site-packages/cv2
COPY --from=opencv-builder /usr/local/lib64/libopencv_*.so* /usr/local/lib64/
RUN echo '/usr/local/lib64' > /etc/ld.so.conf.d/opencv.conf && ldconfig

WORKDIR /opt/app-root/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

USER 1001

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
